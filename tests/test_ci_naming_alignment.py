"""CSV and JSON name the same interval the same way, and the CSV did not move.

They diverged four for four - `latency_ms_ci_low` against
`latency_mean_ms_ci_low` - so a consumer reading both carried a translation
table. The JSON side moved, for two reasons: renaming the CSV columns would
break a header-name reader, which is the one consumer the layout change
promises not to disturb; and two of the four JSON prefixes named point-estimate
keys that do not exist in the record. There is a `latency_mean_ms` and an
`output_tokens_mean`, but no `cost_mean_usd` and no `score_mean`, so
`cost_mean_usd_ci_low` pointed at nothing at all.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json

from cli_modelarium.output_formatters import BatchResult, _format_csv, _format_json

METRICS = ("latency_ms", "output_tokens", "cost_usd", "score")


def _r() -> BatchResult:
    return BatchResult(
        prompt_id="p1", prompt="q", system=None, model="m", temperature=0.0,
        latency_ms=1.0, ttft_ms=1.0, input_tokens=1, output_tokens=1,
        cached_tokens=0, cost_usd=0.001, output="o", error=None, retries=0,
        provider="anthropic",
    )


def _cis() -> dict:
    one = {
        "ci_low": 1.0, "ci_high": 2.0, "ci_level": 0.95, "method": "bca",
        "n_resamples": 5000, "seed": 42, "point_estimate": 1.5, "n_samples": 5,
    }
    return {("m", 0.0, None): dict.fromkeys(METRICS, one)}


class TestTheTwoFormatsAgree:
    def test_every_metric_uses_the_same_name_on_both_sides(self) -> None:
        text = _format_csv([_r()], runs=2, stats_by_cell_cis=_cis())
        header = next(csv.reader(io.StringIO(text)))
        payload = json.loads(_format_json([_r()], runs=2, stats_by_cell_cis=_cis()))
        cell = payload["stats_by_cell"][0]
        for metric in METRICS:
            assert f"{metric}_ci_low" in header, metric
            assert f"{metric}_ci_low" in cell, metric

    def test_no_json_key_names_a_point_estimate_that_does_not_exist(self) -> None:
        payload = json.loads(_format_json([_r()], runs=2, stats_by_cell_cis=_cis()))
        cell = payload["stats_by_cell"][0]
        for gone in ("cost_mean_usd_ci_low", "score_mean_ci_low",
                     "latency_mean_ms_ci_low", "output_tokens_mean_ci_low"):
            assert gone not in cell, gone

    def test_the_point_estimates_the_record_really_has_are_untouched(self) -> None:
        payload = json.loads(_format_json([_r()], runs=2, stats_by_cell_cis=_cis()))
        cell = payload["stats_by_cell"][0]
        assert "latency_mean_ms" in cell
        assert "output_tokens_mean" in cell


class TestTheCsvBytesDidNotMove:
    def test_the_csv_is_byte_identical_across_the_rename(self) -> None:
        """Pinned by hash. The alignment must never be done from the CSV side:
        a header-name reader of `latency_ms_ci_low` would get nothing back.
        """
        text = _format_csv([_r()], runs=2, stats_by_cell_cis=_cis())
        assert hashlib.sha256(text.encode()).hexdigest().startswith("b00c89e2ac3048ed")

    def test_a_header_name_reader_still_finds_its_columns(self) -> None:
        rows = list(csv.DictReader(
            io.StringIO(_format_csv([_r()], runs=2, stats_by_cell_cis=_cis()))
        ))
        assert rows[0]["latency_ms_ci_low"] == "1.0"
        assert rows[0]["latency_ms_ci_n"] == "5"


class TestTheAssertionTagSurvivesIntoJson:
    def test_error_kind_is_emitted(self) -> None:
        """It exists so nobody has to match on the message text - and it was
        dropped, leaving that as the only way to tell a refusal from a broken
        regex per row."""
        from cli_modelarium.assertions import refused_results

        r = BatchResult(
            prompt_id="p1", prompt="q", system=None, model="m", temperature=0.0,
            latency_ms=1.0, ttft_ms=1.0, input_tokens=1, output_tokens=1,
            cached_tokens=0, cost_usd=0.0, output="", error=None, retries=0,
            refused=True,
            assertion_results=refused_results([{"type": "contains", "value": "x"}]),
        )
        a = json.loads(_format_json([r]))["results"][0]["assertions"][0]
        assert a["error_kind"] == "refused"

    def test_it_is_null_on_the_normal_path(self) -> None:
        from cli_modelarium.assertions import AssertionResult

        r = BatchResult(
            prompt_id="p1", prompt="q", system=None, model="m", temperature=0.0,
            latency_ms=1.0, ttft_ms=1.0, input_tokens=1, output_tokens=1,
            cached_tokens=0, cost_usd=0.0, output="x", error=None, retries=0,
            assertion_results=[
                AssertionResult(type="contains", passed=True, expected="x",
                                actual="x", message="ok")
            ],
        )
        a = json.loads(_format_json([r]))["results"][0]["assertions"][0]
        assert a["error_kind"] is None
