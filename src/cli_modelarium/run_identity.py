"""Run identity: who this run was, so two runs can be told apart.

WHY THIS EXISTS. A probe against the published 0.1.9 ran the identical command
twice, 93 seconds apart, and diffed the JSON. Two fields differed:

    <   "latency_ms": 1327.6398930000114,     >   "latency_ms": 675.9965260000058,
    <   "ttft_ms":    1298.1032870000035,     >   "ttft_ms":    637.7918160000036,

That was the entire diff - `cost_usd`, every token count and the output string
were byte-identical. And the SECOND run was the faster one, so "higher latency
ran earlier" is not even a weak heuristic; it orders that pair backwards. The
only remaining signal was filesystem mtime, which does not survive `git add`, a
copy, a tar extract or an artifact upload.

So every per-model MEASUREMENT a drift monitor would compare was already there.
What was missing is run IDENTITY: which run this is, when it began, and whether
two payloads are even measuring the same thing.

WHAT EACH FIELD ANSWERS.

    started_at      "when did this run begin" - ordering, and the only field a
                    monitor needs to pick "the last two runs".
    run_id          "which run is this" - survives copying and renaming, and
                    distinguishes two runs started in the same second.
    experiment_key  "are these two payloads comparable at all" - stable across
                    runs of the same command, different when an input that
                    defines the experiment changes.
    invocation      "what was actually asked for" - the RESOLVED flags, so a
                    monitor sees the model set that ran rather than the group
                    name that was typed.

THE FIELDS ARE BUILT HERE AND PASSED IN, never generated at format time. Two
reasons, one of them enforced by the suite:
`tests/test_runs_display.py::test_json_format_byte_identical_when_runs_one`
calls `_format_json` twice and asserts byte equality, so a `uuid4()` inside the
formatter fails immediately. The other is semantic - `_format_json` runs after
the last provider call returns, so a timestamp taken there is a finish time.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

# Bump when the hash INPUTS change, never for a cosmetic edit. A consumer
# comparing keys across tool versions needs to distinguish "different
# experiment" from "different hashing", and a bare hash cannot say which.
EXPERIMENT_KEY_VERSION = 1

# Characters of hex kept from the digest. 16 is 64 bits: short enough to read
# in a terminal and diff by eye, long enough that a collision needs about 4
# billion experiments before it is likely.
_KEY_LENGTH = 16


def utc_now_iso() -> str:
    """Now, as ISO 8601 UTC with a `Z` suffix and second precision.

    Second precision and `Z` rather than `+00:00`, both deliberately: jq's
    `fromdateiso8601` - the thing a shell drift-monitor will reach for first -
    rejects fractional seconds and rejects the `+00:00` spelling. Two runs
    inside the same second are told apart by `run_id`, which is exactly the
    collision it exists to prevent.

    `datetime.now(UTC)`, never `utcnow()`: the latter returns a naive datetime
    and is deprecated from 3.12.
    """
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    """Stable text for hashing: sorted keys, no whitespace, non-ASCII kept."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_experiment_key(payload: dict[str, Any]) -> str:
    """Hash the inputs that define "the same experiment".

    WHAT IS IN, AND WHY IT IS DOCUMENTED HERE. A hash whose inputs are
    undocumented is worse than no hash: a consumer seeing two different keys
    cannot tell whether the experiment changed or the hashing did. The inputs
    are the command name, the prompt (or the batch suite's resolved prompts),
    the resolved model list, the parsed temperatures, the resolved system
    prompts, the judge models, and the run count.

    `runs` IS IN. Two runs of the same cells at n=1 and n=10 are not the same
    experiment: the second answers a question about variance that the first
    cannot, and a monitor that pooled them would compare a point estimate
    against a distribution.

    THE JUDGE MODEL IS IN, its criteria and template are NOT. The judge changes
    what is measured, so it belongs. The criteria and template are free text
    that can arrive from a file, and hashing a path would fork the key on a
    directory move that changed nothing.

    LATENCY, COST AND EVERY MEASURED VALUE ARE OUT, by construction - they are
    the outputs being compared, and a key that moved with them would never
    match. The OUTPUT DESTINATION is out too: `--output report.json` and
    `--output-format json` piped to stdout are the same experiment written
    twice, and a test in `test_stdout_machine_output.py` proves the point by
    running exactly that pair and comparing the bytes.

    THE MODEL LIST IS NOT SORTED, and that is a decision rather than an
    oversight. Sorting would make `--models a,b` and `--models b,a` share a
    key - defensible, since the same cells are measured - but `prompt_id` in
    compare is a positional row ordinal, so `p1` is model `a` in one run and
    model `b` in the other. A consumer joining two runs on
    `(experiment_key, prompt_id)` would then mis-align every row while both
    keys agreed. Keeping order makes those two runs distinct: a false
    "different" costs a monitor one skipped comparison, a false "same"
    silently corrupts one. The same reasoning is why the temperature list is
    left in the order given.
    """
    material = {"v": EXPERIMENT_KEY_VERSION, **payload}
    digest = hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()
    return digest[:_KEY_LENGTH]


def build_run_identity(
    *,
    command: str,
    started_at: str,
    prompts: list[str],
    models: list[str],
    temperatures: list[float],
    system_prompts: list[str | None],
    judges: list[str] | None = None,
    runs: int = 1,
) -> dict[str, Any]:
    """Build the four top-level identity fields for one run.

    Every argument must already be RESOLVED. `models` is the list after
    `parse_models_arg` and `_resolve_dynamic_groups`, so a run launched with
    `--models all-flagship` records the eight ids that actually ran - group
    membership is registry state and moves between versions, so the group name
    alone would not let a monitor reproduce the run. `temperatures` are parsed
    floats, so `0`, `0.0` and `0.00` do not fork the key.

    NOTHING SECRET IS RECORDED, and the exclusions are an allowlist rather
    than a redaction pass. `invocation` carries only the keys built below;
    anything not named here cannot reach it. In particular:

        --local-url is EXCLUDED. It is operator-supplied and can carry
        credentials in the userinfo position (`http://user:pass@host/v1`),
        which `security.redact_secrets` does not match - its patterns cover
        the `AQ.Ab`, `AIza`, `x-goog-api-key` and `?key=` forms, not a
        `user:pass` pair. A pattern matcher is the wrong instrument for a
        value with no pattern.

        FILE PATHS are EXCLUDED - --system-prompt-file, --expected-facts-file,
        --judge-template, --hallucination-template. A path leaks a home
        directory and a username, and the CONTENT that matters is already
        recorded: the resolved system prompts are here, and they are on every
        result row besides.

        API KEYS never reach this module. They are read from the keyring by
        the provider layer and are not parameters of `compare` or `batch`.

    The `--output` and `--output-format` flags are excluded for a different
    reason: they choose where a payload is written, not what was measured.
    """
    invocation: dict[str, Any] = {
        "command": command,
        "models": list(models),
        "temperatures": list(temperatures),
        "system_prompts": list(system_prompts),
    }
    if judges:
        invocation["judges"] = list(judges)

    # `runs` is deliberately absent from `invocation`: `total_runs` is already
    # top-level and unconditional, and a third copy of one number is a third
    # thing that can disagree. It IS hashed into the key, where it belongs.
    key_material = {
        "command": command,
        "prompts": list(prompts),
        "models": list(models),
        "temperatures": list(temperatures),
        "system_prompts": list(system_prompts),
        "judges": list(judges or []),
        "runs": runs,
    }

    return {
        "started_at": started_at,
        "run_id": str(uuid.uuid4()),
        "experiment_key": compute_experiment_key(key_material),
        "invocation": invocation,
    }
