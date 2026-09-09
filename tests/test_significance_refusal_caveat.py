"""A significance verdict computed partly from declines must say so.

A partially-refused cell mixes two denominators - latency over every billed
run, tokens over the answered ones - and rendered as an ordinary `2/0` before
the OK/Ref/Fail column. The verdict below the table inherits that mix.

The caveat fires on ANY decline, not on a fraction and not only when the
verdict came out significant. Both narrower rules were measured and both miss
half the harm:

    slow declines, A truly faster    2 of 5   p 0.0000 -> 0.0710   signal ERASED
    fast declines, A answered once   4 of 5   p 0.0000 -> 0.0183   verdict CREATED

A fraction threshold tuned on the second column is silent on the first, and
"only when significant" is silent on the whole first column - where a real
difference was destroyed and a null result invites no scrutiny.

The statistic itself is untouched: a decline is a real, billed round trip, and
0.1.9 settled deliberately that timing and cost keep it.
"""

from __future__ import annotations

import io
import json

import pytest
from rich.console import Console

import cli_modelarium.cli as cli_module
from cli_modelarium.output_formatters import (
    _markdown_significance_section,
    _significance_result_to_dict,
    refused_arms,
    significance_refusal_caveat,
)
from cli_modelarium.run_statistics import compute_pairwise_significance
from cli_modelarium.streaming import StreamState

A_MODEL = "claude-opus-5"
B_MODEL = "claude-sonnet-4-5"


def _state(model: str, latency: float, *, refused: bool) -> StreamState:
    state = StreamState(model=model, provider_name="anthropic", temperature=0.0)
    state.latency_ms = latency
    state.refused = refused
    state.error = None
    state.text = "" if refused else "Paris"
    state.output_tokens = 0 if refused else 4
    state.cost_usd = 0.000725
    return state


def _verdict(a_latencies: list[float], a_refused: int, b_latencies: list[float]) -> object:
    a = [
        _state(A_MODEL, latency, refused=i < a_refused)
        for i, latency in enumerate(a_latencies)
    ]
    b = [_state(B_MODEL, latency, refused=False) for latency in b_latencies]
    return compute_pairwise_significance(
        {A_MODEL: a, B_MODEL: b},
        None,
        metric="latency_ms",
        test="welch",
        correction="bonferroni",
    )[0]


# A truly answers ~900ms and B ~1500ms; A's two declines are slow, so they drag
# A's mean up and erase a difference that is real.
SUPPRESSION = ([1500.0, 1502.0, 910.0, 895.0, 902.0], 2, [1500.0, 1505.0, 1495.0, 1502.0, 1498.0])
# A declines four of five, fast; the one answer plus four quick declines rank it
# significantly faster than a model that answered every time.
INVERSION = ([150.0, 151.0, 152.0, 153.0, 2270.0], 4, [2200.0, 2210.0, 2205.0, 2215.0, 2208.0])


class TestTheFieldsArePopulated:
    def test_each_arm_carries_its_own_count(self) -> None:
        r = _verdict(*SUPPRESSION)
        assert r.n_refused_a == 2
        assert r.n_refused_b == 0

    def test_a_clean_comparison_carries_zeroes(self) -> None:
        r = _verdict([900.0, 905.0, 910.0, 895.0, 902.0], 0, [1500.0] * 5)
        assert r.n_refused_a == 0
        assert r.n_refused_b == 0


class TestItFiresOnPresenceNotOnOutcome:
    def test_it_fires_on_the_suppression_case_which_is_not_significant(self) -> None:
        r = _verdict(*SUPPRESSION)
        # The rule that fires only on a significant verdict would be silent
        # here, and this is the case a reader is least likely to catch: a real
        # difference reported as none.
        assert r.significant_at_threshold is False
        assert refused_arms([r]) == [(A_MODEL, 2)]

    def test_it_fires_on_the_inversion_case(self) -> None:
        r = _verdict(*INVERSION)
        assert r.significant_at_threshold is True
        assert refused_arms([r]) == [(A_MODEL, 4)]

    def test_it_fires_on_a_single_decline(self) -> None:
        # Presence, not a fraction. One in five is 0.20, below any threshold
        # that would catch the measured inversions.
        r = _verdict([1500.0, 910.0, 905.0, 900.0, 902.0], 1, [1500.0] * 5)
        assert refused_arms([r]) == [(A_MODEL, 1)]

    def test_it_stays_quiet_when_nothing_declined(self) -> None:
        r = _verdict([900.0, 905.0, 910.0, 895.0, 902.0], 0, [1500.0] * 5)
        assert refused_arms([r]) == []


class TestTheTextNamesTheModel:
    def test_the_model_and_its_count_appear(self) -> None:
        text = significance_refusal_caveat([(A_MODEL, 3)])
        # With three or more models a reader cannot otherwise tell which arm is
        # contaminated.
        assert A_MODEL in text
        assert "3 declined" in text

    def test_both_arms_are_named_when_both_declined(self) -> None:
        text = significance_refusal_caveat([(A_MODEL, 2), (B_MODEL, 1)])
        assert A_MODEL in text and B_MODEL in text

    def test_it_says_the_numbers_are_unchanged(self) -> None:
        # The statistic is not the defect; the silence was. A reader must not
        # come away thinking the means were adjusted.
        assert "unchanged" in significance_refusal_caveat([(A_MODEL, 2)])


@pytest.fixture
def captured_console(
    monkeypatch: pytest.MonkeyPatch, capture_console: Console
) -> io.StringIO:
    """Swap cli.console for the width-pinned shared Console from conftest.

    Replaces the object rather than mutating the module-level one in place:
    setting `width` on the real console leaks into every later test in the
    session, and monkeypatch restores this automatically.
    """
    monkeypatch.setattr(cli_module, "console", capture_console)
    return capture_console.file  # type: ignore[return-value]


class TestItReachesBothSurfaces:
    def test_the_console_prints_it_above_the_verdicts(
        self, captured_console: io.StringIO
    ) -> None:
        r = _verdict(*SUPPRESSION)
        cli_module._display_significance([r])
        rendered = " ".join(captured_console.getvalue().split())
        assert f"{A_MODEL} (2 declined)" in rendered
        # Above the verdict line, so it is read before the number it qualifies.
        assert rendered.index("2 declined") < rendered.index("p=0.0710")

    def test_the_markdown_report_carries_it(self) -> None:
        # This is the artifact a team circulates, and it is where a Significant
        # verdict computed from declines currently lands unqualified.
        r = _verdict(*INVERSION)
        section = "\n".join(_markdown_significance_section([r]))
        assert f"{A_MODEL} (4 declined)" in section
        assert section.index("4 declined") < section.index("| `claude-opus-5` |")

    def test_the_markdown_stays_quiet_on_a_clean_run(self) -> None:
        r = _verdict([900.0, 905.0, 910.0, 895.0, 902.0], 0, [1500.0] * 5)
        section = "\n".join(_markdown_significance_section([r]))
        assert "declined" not in section


class TestJsonKeysAreOptional:
    def test_they_appear_when_an_arm_declined(self) -> None:
        payload = _significance_result_to_dict(_verdict(*SUPPRESSION))
        assert payload["n_refused_a"] == 2
        assert payload["n_refused_b"] == 0

    def test_they_are_absent_on_a_clean_comparison(self) -> None:
        # A consumer diffing a saved payload from a run with no refusals must
        # see no new keys at all.
        payload = _significance_result_to_dict(
            _verdict([900.0, 905.0, 910.0, 895.0, 902.0], 0, [1500.0] * 5)
        )
        assert "n_refused_a" not in payload
        assert "n_refused_b" not in payload
        assert json.dumps(payload)  # still serialisable


class TestReadThroughGetattr:
    """`tests/test_display_gaps.py` drives the renderers with a duck-typed stub
    carrying only the fields the display reads. A direct attribute access would
    raise there rather than fail a meaningful assertion, so every read of the
    new fields uses a default."""

    class _StubWithoutTheNewFields:
        model_a = A_MODEL
        model_b = B_MODEL
        metric = "latency_ms"
        test_used = "welch_t_test"
        correction_method = "bonferroni"
        threshold = 0.05
        p_value = 0.04
        p_value_corrected = 0.04
        significant_at_threshold = True
        mean_a = 1.0
        mean_b = 2.0
        effect_size = 0.5
        effect_size_interpretation = "medium"
        n_a = 5
        n_b = 5
        stdev_a = 0.1
        stdev_b = 0.1
        test_statistic = 1.0
        degrees_of_freedom = 8.0
        n_comparisons = 1

    def test_the_collector_tolerates_a_stub(self) -> None:
        assert refused_arms([self._StubWithoutTheNewFields()]) == []

    def test_the_markdown_section_tolerates_a_stub(self) -> None:
        section = "\n".join(
            _markdown_significance_section([self._StubWithoutTheNewFields()])
        )
        assert "declined" not in section

    def test_the_console_tolerates_a_stub(self, captured_console: io.StringIO) -> None:
        cli_module._display_significance([self._StubWithoutTheNewFields()])
        assert "declined" not in captured_console.getvalue()


class TestNoStatisticMoved:
    def test_the_means_and_p_value_are_what_they_were(self) -> None:
        # Adding the fields must not disturb the arithmetic: a decline is a real
        # measured round trip and stays in the latency sample by design.
        r = _verdict(*SUPPRESSION)
        assert r.mean_a == pytest.approx(1141.8)
        assert r.mean_b == pytest.approx(1500.0)
        assert r.p_value_corrected == pytest.approx(0.0710, abs=5e-4)
        assert r.n_a == 5
        assert r.n_b == 5


class TestRenderedWidthIsPinned:
    def test_the_caveat_wraps_rather_than_truncating(self) -> None:
        buffer = io.StringIO()
        Console(file=buffer, width=100, force_terminal=False).print(
            significance_refusal_caveat([(A_MODEL, 2)])
        )
        rendered = " ".join(buffer.getvalue().split())
        assert A_MODEL in rendered
        assert rendered.endswith("before acting on it.")
