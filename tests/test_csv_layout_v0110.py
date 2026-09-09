"""The CSV layout gained four columns, and they are APPENDED.

Groups 3, 4a and 4c each found a CSV gap and deferred it so the columns would
move once. They move here: `provider`, `status`, `assertions_configured` and
`assertions_errored`, plus a CI provenance block on the dynamic tail.

WHY APPEND, MEASURED. In the unfixed snapshot both layouts broke the same ten
tests, which is what made the choice look arbitrary. It is not: bumping the
width pins - the first mandatory step for either layout - splits them, and the
insert layout then fails
`TestCsvUntouchedByTheMixedKey::test_csv_columns_unchanged` with
`assert 'provider' == 'temperature'` while append passes it. A positional
reader does not crash on an insert either; it silently reads the provider name
as the temperature and `cached_tokens` as the cost.

APPEND IS NOT FREE. `run_index` and the CI columns are appended to `fieldnames`
AFTER `CSV_COLUMNS`, so growing the tuple pushes that tail right. The first 23
positions are byte-identical; nothing past them is.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from cli_modelarium.batch import BatchPrompt
from cli_modelarium.output_formatters import (
    CSV_COLUMNS,
    STATUS_VALUES,
    _format_csv,
    _format_json,
    _format_markdown,
    state_to_result,
)
from cli_modelarium.streaming import StreamState
from tests.conftest import V019_COLUMNS

PROMPT = BatchPrompt(id="p1", prompt="hi", system=None, assertions=[])


def _state(model: str, provider: str, **kw) -> StreamState:
    s = StreamState(model=model, provider_name=provider, temperature=0.0)
    s.status = kw.get("status", "complete")
    s.text = kw.get("text", "answer")
    s.cost_usd = kw.get("cost", 0.01)
    s.latency_ms = kw.get("latency", 100.0)
    s.input_tokens, s.output_tokens = 10, 20
    return s


def _row(result) -> dict:
    rows = list(csv.reader(io.StringIO(_format_csv([result]))))
    return dict(zip(rows[0], rows[1], strict=True))


class TestTheFirst23PositionsAreUntouched:
    def test_the_frozen_prefix_still_leads_the_header(self) -> None:
        assert CSV_COLUMNS[: len(V019_COLUMNS)] == V019_COLUMNS

    def test_the_new_columns_come_after_it(self) -> None:
        assert CSV_COLUMNS[len(V019_COLUMNS) :] == (
            "provider",
            "status",
            "assertions_configured",
            "assertions_errored",
        )

    def test_a_v019_positional_reader_still_reads_the_old_columns(self) -> None:
        """The whole point of appending. Index 4 is still the temperature and
        index 10 is still the cost, which an insert would have broken silently.
        """
        row = list(csv.reader(io.StringIO(_format_csv([
            state_to_result(_state("claude-opus-5", "anthropic"), PROMPT)
        ]))))[1]
        assert row[V019_COLUMNS.index("temperature")] == "0.0"
        assert row[V019_COLUMNS.index("cost_usd")] == "0.01"
        assert row[V019_COLUMNS.index("model")] == "claude-opus-5"


class TestProviderIsOnEveryRowInEveryFormat:
    def test_csv(self) -> None:
        assert _row(state_to_result(_state("claude-opus-5", "anthropic"), PROMPT))[
            "provider"
        ] == "anthropic"

    def test_json(self) -> None:
        payload = json.loads(
            _format_json([state_to_result(_state("claude-opus-5", "anthropic"), PROMPT)])
        )
        assert payload["results"][0]["provider"] == "anthropic"

    def test_markdown(self) -> None:
        md = _format_markdown(
            [state_to_result(_state("claude-opus-5", "anthropic"), PROMPT)], runs=1
        )
        assert "| Provider |" in md
        assert "`anthropic`" in md

    def test_it_is_the_route_not_the_vendor(self) -> None:
        """`openai/gpt-oss-120b` is served by groq. The row must say groq,
        because that is whose key was used and whose price was charged."""
        assert _row(state_to_result(_state("openai/gpt-oss-120b", "groq"), PROMPT))[
            "provider"
        ] == "groq"


class TestASavedRowForAGoneModelStillFormats:
    """A format-time `get_provider_for_model` would raise on exactly these.

    RetiredModelError for a retired id, UnknownModelError for one dropped from
    the registry - so a historical report, which is the most likely place to
    meet them, would crash instead of rendering.
    """

    @pytest.mark.parametrize(
        "model",
        ["deepseek-chat", "deepseek-reasoner", "grok-4.1-fast", "gpt-4-turbo-preview"],
    )
    def test_every_format_renders_it(self, model: str) -> None:
        r = state_to_result(_state(model, "deepseek"), PROMPT)
        assert _row(r)["provider"] == "deepseek"
        assert json.loads(_format_json([r]))["results"][0]["provider"] == "deepseek"
        assert "`deepseek`" in _format_markdown([r], runs=1)


class TestTheStatusColumnHasFourValues:
    def test_an_ordinary_row(self) -> None:
        assert _row(state_to_result(_state("claude-opus-5", "anthropic"), PROMPT))[
            "status"
        ] == "ok"

    def test_a_cancelled_row_does_not_read_as_answered(self) -> None:
        """A two-value column would have labelled the cost ceiling's cells
        `answered`, reintroducing on CSV exactly what 89aa560 removed."""
        s = StreamState(model="claude-opus-5", provider_name="anthropic", temperature=0.0)
        s.mark_cancelled()
        assert _row(state_to_result(s, PROMPT))["status"] == "cancelled"

    def test_a_refused_row(self) -> None:
        s = _state("claude-opus-5", "anthropic", text="")
        s.refused = True
        s.stop_reason = "refusal"
        assert _row(state_to_result(s, PROMPT))["status"] == "refused"

    def test_an_errored_row(self) -> None:
        s = _state("claude-opus-5", "anthropic")
        s.mark_error("boom")
        assert _row(state_to_result(s, PROMPT))["status"] == "error"

    def test_the_set_is_closed_and_none_is_mangled_by_the_formula_guard(self) -> None:
        """Unlike `stop_category`, which is the provider's own open set. And
        none of the four begins with a formula character, so none picks up the
        leading apostrophe `-` would."""
        assert set(STATUS_VALUES) == {"ok", "refused", "error", "cancelled"}
        for word in STATUS_VALUES:
            assert not word.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))

    def test_json_keeps_refused_as_a_boolean(self) -> None:
        """README.md:398's jq recipe is `select(.error or .refused)`. In jq
        every non-empty string is truthy, so a categorical there would select
        every row."""
        s = _state("claude-opus-5", "anthropic", text="")
        s.refused = True
        row = json.loads(_format_json([state_to_result(s, PROMPT)]))["results"][0]
        assert row["refused"] is True
        assert row["cancelled"] is False


class TestARefusedRowIsDistinguishableFromOneWithNoAssertions:
    """Both used to render `0, 0, ""` - byte-identical - so a pipeline summing
    the two columns across rows reported a clean 100% and the refusal vanished.
    Markdown already showed a warn mark with `0/4`; CSV had no column that
    could carry it.
    """

    def _refused_with_assertions(self):
        from cli_modelarium.assertions import refused_results

        s = _state("claude-opus-5", "anthropic", text="")
        s.refused = True
        s.stop_reason = "refusal"
        cfg = [{"type": "contains", "value": v} for v in ("a", "b", "c")]
        return state_to_result(s, PROMPT, assertion_results=refused_results(cfg))

    def test_the_refused_row_names_what_it_could_not_check(self) -> None:
        cells = _row(self._refused_with_assertions())
        assert cells["assertions_configured"] == "3", cells
        assert cells["assertions_errored"] == "3", cells
        assert cells["assertions_total"] == "0"
        assert cells["assertions_passed"] == "0"
        assert cells["status"] == "refused"

    def test_a_row_with_no_assertions_stays_blank(self) -> None:
        cells = _row(state_to_result(_state("claude-opus-5", "anthropic"), PROMPT))
        assert cells["assertions_configured"] == ""
        assert cells["assertions_errored"] == ""

    def test_the_two_rows_are_no_longer_identical(self) -> None:
        refused = _row(self._refused_with_assertions())
        none_configured = _row(state_to_result(_state("claude-opus-5", "anthropic"), PROMPT))
        keys = ("assertions_passed", "assertions_total", "assertions_configured",
                "assertions_errored")
        assert [refused[k] for k in keys] != [none_configured[k] for k in keys]

    def test_assertions_total_is_not_widened(self) -> None:
        """It is the denominator of `pass_rate`. Widening it to cover errored
        assertions would break `assertions_passed / assertions_total`."""
        assert _row(self._refused_with_assertions())["assertions_total"] == "0"


class TestTheCiProvenanceTail:
    """`_flatten_cell_cis` carries eight fields per interval and CSV wrote two:
    every row of a cost-ceiling run carried the same bounds with nothing saying
    how many observations they rested on."""

    def _cis(self):
        return {
            ("claude-opus-5", 0.0, None): {
                "latency_ms": {
                    "ci_low": 10.0, "ci_high": 20.0, "ci_level": 0.95,
                    "method": "bca", "n_resamples": 5000, "seed": 42,
                    "point_estimate": 15.0, "n_samples": 5,
                }
            }
        }

    def _header_and_row(self):
        rows = list(csv.reader(io.StringIO(_format_csv(
            [state_to_result(_state("claude-opus-5", "anthropic"), PROMPT)],
            runs=2, stats_by_cell_cis=self._cis(),
        ))))
        return rows[0], dict(zip(rows[0], rows[1], strict=True))

    def test_the_pairs_keep_their_order_and_provenance_follows(self) -> None:
        header, _ = self._header_and_row()
        tail = header[header.index("run_index") :]
        assert tail == [
            "run_index",
            "latency_ms_ci_low",
            "latency_ms_ci_high",
            "latency_ms_ci_n",
            "ci_method",
            "ci_level",
            "ci_resamples",
            "ci_seed",
        ], tail

    def test_it_says_how_many_observations_the_interval_rests_on(self) -> None:
        _, cells = self._header_and_row()
        assert cells["latency_ms_ci_n"] == "5"
        assert cells["ci_method"] == "bca"
        assert cells["ci_level"] == "0.95"
        assert cells["ci_resamples"] == "5000"
        assert cells["ci_seed"] == "42"

    def test_a_run_with_no_intervals_gains_no_tail(self) -> None:
        header = list(csv.reader(io.StringIO(_format_csv(
            [state_to_result(_state("claude-opus-5", "anthropic"), PROMPT)], runs=1
        ))))[0]
        assert header == list(CSV_COLUMNS)
