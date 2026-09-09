"""The JSON fields a consumer needs to tell rows and runs apart, always present.

WHY THIS FILE EXISTS. Two fields were conditional, and neither was a bug while
nothing consumed them. `run_index` appeared only when `--runs > 1`; `invocation`
is written only when the CLI threads a run identity through. The first is a real
gap in every single-run payload, the second a latent one at the formatter
boundary. Both become bugs the moment something reads them, and the tests below
are what stop that regressing.

WHAT THE CELL KEY CANNOT DO, which is the whole case for `run_index`. Nothing
de-duplicates temperatures or system prompts - only the model list is deduped,
at `_resolve_dynamic_groups`. So `--temperatures 0,0` is two cells carrying one
`(model, temperature, system)` triple, at a single run, with two different
costs. Without `run_index` a consumer joining on that triple drops a row or
matches arbitrarily, and reports a difference that is really a collision.

WHY `invocation.command` AND NOT A SHAPE HEURISTIC. A batch payload and a
compare payload share every row key and every top-level key but `methodology`,
which is compare-only - and a `.txt`-sourced batch mints `p1, p2, p3` from
`_parse_txt`, byte-identical to compare's synthetic ids. `invocation.command`
is the only field that answers "which command wrote this", so it has to be
there on every path that writes a payload, not just the one a test happened to
cover.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli_modelarium.cli import main as cli_main
from cli_modelarium.providers.base import BaseProvider, CompletionResult, OnChunk


class _FixedProvider(BaseProvider):
    """Deterministic result, so only payload shape varies."""

    def __init__(self) -> None:
        self.name = "fake"

    async def stream(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if False:
            yield ""
        raise NotImplementedError

    async def complete(
        self,
        prompt: str,
        model: str,
        temperature: float,
        system_prompt: str | None = None,
        *,
        on_chunk: OnChunk | None = None,
    ) -> CompletionResult:
        if on_chunk is not None:
            on_chunk("an answer")
        return CompletionResult(
            output="an answer",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.000123,
            latency_ms=42.0,
            ttft_ms=12.0,
            model=model,
            provider="fake",
            temperature=temperature,
        )


@pytest.fixture
def fixed_provider(monkeypatch: pytest.MonkeyPatch) -> _FixedProvider:
    fake = _FixedProvider()
    monkeypatch.setattr("cli_modelarium.cli._get_provider_instance", lambda name, **_k: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-NOT_A_REAL_KEY_test_fixture_00")
    return fake


def _suite(tmp_path: Path) -> Path:
    path = tmp_path / "suite.json"
    path.write_text(json.dumps([{"id": "one", "prompt": "a prompt"}]), encoding="utf-8")
    return path


def _run_to_stdout(*args: str) -> dict:
    result = CliRunner().invoke(cli_main, [*args, "--output-format", "json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def _run_to_file(target: Path, *args: str) -> dict:
    result = CliRunner().invoke(cli_main, [*args, "--output", str(target)])
    assert result.exit_code == 0, result.output
    return json.loads(target.read_text(encoding="utf-8"))


# ===== run_index =====


class TestRunIndexIsAlwaysPresent:
    def test_single_run_rows_carry_run_index_zero(
        self, fixed_provider: _FixedProvider
    ) -> None:
        payload = _run_to_stdout("compare", "--models", "gpt-5.5", "a prompt")
        assert payload["total_runs"] == 1
        assert [r["run_index"] for r in payload["results"]] == [0]

    def test_single_run_file_output_carries_it_too(
        self, fixed_provider: _FixedProvider, tmp_path: Path
    ) -> None:
        # The file writer is a different call path from stdout. Pinning only
        # one of them is how a field goes missing from the half nobody checked.
        payload = _run_to_file(
            tmp_path / "out.json", "compare", "--models", "gpt-5.5", "a prompt"
        )
        assert [r["run_index"] for r in payload["results"]] == [0]

    def test_batch_rows_carry_it(
        self, fixed_provider: _FixedProvider, tmp_path: Path
    ) -> None:
        payload = _run_to_stdout("batch", str(_suite(tmp_path)), "--models", "gpt-5.5")
        assert [r["run_index"] for r in payload["results"]] == [0]

    def test_multi_run_numbering_is_unchanged(
        self, fixed_provider: _FixedProvider
    ) -> None:
        # The point of the change is to EXTEND the field to one run, not to
        # renumber the case that already worked. Submission order is
        # model-major - each model's runs are consecutive - so two models over
        # three runs is 0,1,2,0,1,2 and stays that way.
        payload = _run_to_stdout(
            "compare", "--models", "gpt-5.5,gpt-5.6-terra", "--runs", "3", "a prompt"
        )
        assert payload["total_runs"] == 3
        assert [r["run_index"] for r in payload["results"]] == [0, 1, 2, 0, 1, 2]
        # Each model owns a full 0..2 sweep, which is what `stats_by_cell`
        # aggregates over.
        by_model: dict[str, list[int]] = {}
        for r in payload["results"]:
            by_model.setdefault(r["model"], []).append(r["run_index"])
        assert all(v == [0, 1, 2] for v in by_model.values())


class TestTheCellKeyCollides:
    """The collision itself, pinned - and what does and does not resolve it.

    `run_index` reads 0 on BOTH rows here, because these are two distinct cells
    at one run rather than two runs of one cell. So making it unconditional
    does not break this tie; `prompt_id` does, and it is positional. What the
    unconditional field buys is a join key of one shape at every run count,
    instead of a consumer inferring "single run" from an absent key.
    """

    def test_duplicate_temperatures_produce_two_rows_one_cell_key(
        self, fixed_provider: _FixedProvider
    ) -> None:
        payload = _run_to_stdout(
            "compare", "--models", "gpt-5.5", "--temperatures", "0,0", "a prompt"
        )
        rows = payload["results"]
        assert len(rows) == 2

        # The premise: the triple genuinely collides. If a future change
        # de-duplicates temperatures this assertion fails, which is the right
        # place to find that out - the tiebreaker below would then be moot.
        cell_keys = {(r["model"], r["temperature"], r["system"]) for r in rows}
        assert len(cell_keys) == 1, "expected a genuine cell-key collision"

        # `run_index` is present on both and reads 0 on both - it is not the
        # tiebreaker here, and pinning that stops the next reader assuming it
        # is. `prompt_id` is what separates them.
        assert all(r["run_index"] == 0 for r in rows)
        assert {r["prompt_id"] for r in rows} == {"p1", "p2"}

    def test_duplicate_system_prompts_collide_the_same_way(
        self, fixed_provider: _FixedProvider
    ) -> None:
        payload = _run_to_stdout(
            "compare", "--models", "gpt-5.5", "--system-prompts", "a,a", "a prompt"
        )
        rows = payload["results"]
        assert len(rows) == 2
        assert len({(r["model"], r["temperature"], r["system"]) for r in rows}) == 1
        assert all(r["run_index"] == 0 for r in rows)


# ===== invocation.command =====


class TestCommandIsAlwaysReadable:
    """Every path that writes a payload names the command that wrote it."""

    def test_compare_and_batch_disagree_on_stdout(
        self, fixed_provider: _FixedProvider, tmp_path: Path
    ) -> None:
        compare = _run_to_stdout("compare", "--models", "gpt-5.5", "a prompt")
        batch = _run_to_stdout("batch", str(_suite(tmp_path)), "--models", "gpt-5.5")
        assert compare["invocation"]["command"] == "compare"
        assert batch["invocation"]["command"] == "batch"

    def test_compare_and_batch_disagree_in_a_written_file(
        self, fixed_provider: _FixedProvider, tmp_path: Path
    ) -> None:
        compare = _run_to_file(
            tmp_path / "c.json", "compare", "--models", "gpt-5.5", "a prompt"
        )
        batch = _run_to_file(
            tmp_path / "b.json", "batch", str(_suite(tmp_path)), "--models", "gpt-5.5"
        )
        assert compare["invocation"]["command"] == "compare"
        assert batch["invocation"]["command"] == "batch"

    def test_command_alone_separates_them(
        self, fixed_provider: _FixedProvider, tmp_path: Path
    ) -> None:
        """No other single top-level key does this job.

        `methodology` is compare-only and would work today, but it is absent
        from a 0.1.9 compare payload too, so it conflates "batch" with "old
        tool". This asserts the positive case and the reason the obvious
        alternative was not taken.
        """
        compare = _run_to_stdout("compare", "--models", "gpt-5.5", "a prompt")
        batch = _run_to_stdout(
            "batch", str(_suite(tmp_path)), "--models", "gpt-5.5", "--no-assertions"
        )

        assert compare["invocation"]["command"] != batch["invocation"]["command"]

        # Row shape gives a consumer nothing to go on. `--no-assertions` is not
        # cheating here - it is the point: the two assertion keys a batch row
        # usually carries track whether ASSERTIONS RAN, not which command ran,
        # so they are absent from this batch and would be absent from any
        # suite that configured none. A discriminator that a flag can switch
        # off is not one.
        assert set(compare["results"][0]) == set(batch["results"][0])

    def test_a_txt_sourced_batch_mints_compare_shaped_prompt_ids(
        self, fixed_provider: _FixedProvider, tmp_path: Path
    ) -> None:
        """The heuristic a consumer would otherwise reach for, shown failing.

        `batch._parse_txt` numbers its prompts `p1, p2, ...` - the same
        convention `_states_to_compare_results` uses for compare's synthetic
        ids. Reading the id shape cannot tell the two commands apart.
        """
        suite = tmp_path / "prompts.txt"
        suite.write_text("first prompt\nsecond prompt\n", encoding="utf-8")
        payload = _run_to_stdout("batch", str(suite), "--models", "gpt-5.5")

        assert [r["prompt_id"] for r in payload["results"]] == ["p1", "p2"]
        assert payload["invocation"]["command"] == "batch"


class TestIdentityIsAllOrNothing:
    """A partial identity block is a half-answer, so it is not emitted."""

    def test_the_four_fields_arrive_together(
        self, fixed_provider: _FixedProvider
    ) -> None:
        payload = _run_to_stdout("compare", "--models", "gpt-5.5", "a prompt")
        present = [
            f
            for f in ("started_at", "run_id", "experiment_key", "invocation")
            if f in payload
        ]
        assert len(present) == 4, f"partial identity block: {present}"

    def test_a_hand_built_partial_identity_raises_rather_than_half_writing(
        self,
    ) -> None:
        # `build_run_identity` always returns all four, so this shape can only
        # come from a caller that assembled one by hand. Raising is the loud
        # failure; the alternative was silently writing `run_id` with no
        # `invocation`, which reads as a complete payload and is not one.
        from cli_modelarium.batch import BatchPrompt
        from cli_modelarium.output_formatters import _format_json, state_to_result
        from cli_modelarium.streaming import StreamState

        state = StreamState(
            model="m", provider_name="p", temperature=0.0, status="done", text="x"
        )
        results = [state_to_result(state, BatchPrompt(id="p1", prompt="q", system=None))]

        with pytest.raises(KeyError):
            _format_json(results, run_identity={"run_id": "only-this-one"})


# ===== the outcome counts =====


class TestEveryOutcomeCountIsReadable:
    """`total_results` splits into named terms, and every term is always there.

    A row lands in exactly one of four states, and three of the four counts
    were emitted only when non-zero. So `0` and "a tool too old to count this"
    were the same observation on a clean run - the inference `total_runs` was
    made unconditional to kill, applied to the fields a CI job is most likely
    to gate on.
    """

    OUTCOME_KEYS = ("failed_results", "refused_results", "cancelled_results")

    @pytest.mark.parametrize("key", OUTCOME_KEYS)
    def test_a_clean_compare_reports_zero(
        self, fixed_provider: _FixedProvider, key: str
    ) -> None:
        payload = _run_to_stdout("compare", "--models", "gpt-5.5", "a prompt")
        assert payload[key] == 0

    @pytest.mark.parametrize("key", OUTCOME_KEYS)
    def test_a_clean_batch_reports_zero(
        self, fixed_provider: _FixedProvider, tmp_path: Path, key: str
    ) -> None:
        payload = _run_to_stdout("batch", str(_suite(tmp_path)), "--models", "gpt-5.5")
        assert payload[key] == 0

    def test_the_named_terms_account_for_every_row(
        self, fixed_provider: _FixedProvider
    ) -> None:
        # The reason the counts have to be readable rather than inferred: they
        # are the terms of a sum against `total_results`, and a consumer
        # checking that sum cannot treat a missing term as zero without also
        # treating an old payload as a complete one.
        payload = _run_to_stdout(
            "compare", "--models", "gpt-5.5,gpt-5.6-terra", "a prompt"
        )
        named = sum(payload[k] for k in self.OUTCOME_KEYS)
        assert payload["total_results"] == 2
        assert named == 0, "a clean run has no failed, refused or cancelled rows"

    def test_the_assertion_refusal_count_reads_zero_when_the_block_fires(
        self, fixed_provider: _FixedProvider, tmp_path: Path
    ) -> None:
        # Scoped to the block, not to the payload: `total_assertions_refused`
        # follows `total_assertions_errored`, which is present whenever
        # assertions ran and absent when they did not.
        suite = tmp_path / "asserted.json"
        suite.write_text(
            json.dumps(
                [
                    {
                        "id": "one",
                        "prompt": "a prompt",
                        "assertions": [{"type": "contains", "value": "an answer"}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        payload = _run_to_stdout("batch", str(suite), "--models", "gpt-5.5")
        assert payload["total_assertions_refused"] == 0
        assert payload["total_assertions_errored"] == 0
        assert payload["total_assertions"] == 1
