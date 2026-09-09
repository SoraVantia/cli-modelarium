"""Facts asserted by the nine README files, checked against the registry.

README.md and its eight translations have needed correcting four times: a
provider count that stayed at ten, a temperature list that stayed at nine, a
`--runs` bullet that was never translated, and an `all`-group sentence that
never learned about NVIDIA. Every one of those facts already exists in the
code, so none of them needs to be maintained by reading nine files.

Each check below derives its expectation from `PRICING` / `MODEL_GROUPS` /
`all_known_providers()` and asserts the documentation agrees. Structural
parity between nine stale files is not the goal - agreeing with the registry
is.

Two conventions this file adopts, both worth stating because they are the
parts a future edit is most likely to get wrong:

    Numerals are matched as digits, not words. The provider count is written
    `11` in all nine files even where the surrounding prose is German or
    Japanese, and the model-id lists are backticked identifiers that no
    translator touches. Counts spelled out in prose ("Diese zwölf Modelle")
    are deliberately NOT asserted here - they would need a numeral table per
    language, and the digit sites already fail if the count moves.

    ENGLISH_ONLY_HEADINGS is the single source of truth for what may legally
    differ between README.md and a translation. The note at line 10 of each
    translation names the same set in prose; if the two disagree, that is the
    bug this file exists to catch. Adding a section to README.md without
    either translating it or listing it here fails
    `test_heading_count_matches_english_minus_exceptions`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cli_modelarium.models_registry import DYNAMIC_GROUPS, MODEL_GROUPS, all_known_providers
from cli_modelarium.pricing import NOT_PRICED, PRICING, PRICING_VERIFICATION

REPO_ROOT = Path(__file__).parent.parent

ENGLISH_README = "README.md"
TRANSLATED_READMES = [
    "README.de.md",
    "README.es.md",
    "README.fr.md",
    "README.it.md",
    "README.ja.md",
    "README.ko.md",
    "README.pt.md",
    "README.zh.md",
]
ALL_READMES = [ENGLISH_README, *TRANSLATED_READMES]

# Sections that exist only in README.md. The note at line 10 of every
# translation names this same set in prose - keep the two in step.
ENGLISH_ONLY_HEADINGS = [
    "Reproducibility analysis",
    "Statistical significance testing",
    "Bootstrap confidence intervals",
    "Paired tests for same-prompt",
    "McNemar's test",
    "Headless Linux servers",
    "More examples",
]


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def _headings(text: str) -> list[str]:
    """Markdown headings, skipping `#` comment lines inside fenced blocks."""
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and re.match(r"^#{1,3} ", line):
            out.append(line.rstrip())
    return out


def _bullets(text: str, heading_fragment: str) -> list[str]:
    """Top-level `- ` bullets under the first heading containing a fragment."""
    lines = text.split("\n")
    start = next(
        i
        for i, line in enumerate(lines)
        if re.match(r"^#{1,3} ", line) and heading_fragment in line
    )
    out: list[str] = []
    for line in lines[start + 1 :]:
        if re.match(r"^#{1,3} ", line):
            break
        if line.startswith("- "):
            out.append(line)
    return out


# A markdown table's separator row: pipes, dashes, optional alignment colons.
# Body rows always carry letters, so this cannot match one by accident.
_SEPARATOR_ROW = re.compile(r"^\|[\s:|-]+\|$")


def _table_rows(text: str, cell_fragment: str) -> list[list[str]]:
    """Body rows of the pipe table containing a fragment, wherever it appears.

    The fragment is matched against ANY line of the table, header or body, and
    the table's start is then found by walking back to the separator row. The
    obvious alternative - anchor on a header word - is not available here:
    every header is translated (`Group` is `Gruppe`, `Grupo`, `Groupe`,
    `Gruppo`, `グループ`, `그룹`, `组`), so the only translation-stable anchors
    in these files are the backticked identifiers in the body cells.

    This function previously took `start + 2` from the match "to skip header
    and separator", which is correct only when the match IS the header. Its one
    caller passes a body fragment, so it silently returned the table minus its
    first two rows: `all-premium`/`all-flagship` and `all-budget` were compared
    against MODEL_GROUPS in none of the nine files. Anchoring on the separator
    removes the assumption rather than re-tuning the offset under it.
    """
    lines = text.split("\n")
    match = next(
        (i for i, line in enumerate(lines) if line.startswith("|") and cell_fragment in line),
        None,
    )
    assert match is not None, f"no pipe-table line contains {cell_fragment!r}"
    separator = next((i for i in range(match, -1, -1) if _SEPARATOR_ROW.match(lines[i])), None)
    assert separator is not None, (
        f"{cell_fragment!r} matched line {match} but no separator row precedes it - "
        f"the fragment is not inside a markdown table."
    )
    rows: list[list[str]] = []
    for line in lines[separator + 1 :]:
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


# ===== expectations derived from the registry =====

CLOUD_PROVIDER_COUNT = len([p for p in all_known_providers() if p != "local"])
TEMPERATURE_OMITTED = {m for m, e in PRICING.items() if e.get("rejects_sampling_params")}
# Groups the static table must document, one alias per cell. Derived rather
# than a literal count: `all` and `all-local` resolve at runtime and have no
# row, and `all-premium`/`all-flagship` share one row while being two keys, so
# neither `len(MODEL_GROUPS)` nor a hardcoded row count states the real rule.
STATIC_GROUPS = set(MODEL_GROUPS) - DYNAMIC_GROUPS

# Every date the READMEs state. They are deliberately different from each
# other: pricing was re-verified after the rate limits were, and model
# availability moved when the NIM rows landed. Stored as the ISO set so a
# language-specific format cannot smuggle a wrong one through.
#
# The Z.AI exception (2026-06-22) is gone: the 2026-09-06 sweep covered that
# block, so it no longer carries a date older than the pricing one.
EXPECTED_DATES = {
    "2026-09-06",  # pricing verification (stated twice - How it works, Pricing data)
    "2026-06-21",  # rate-limit verification
    "2026-08-15",  # model availability
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9,
    "januar": 1, "februar": 2, "märz": 3, "juni": 6, "juli": 7,
    # "september" is spelled identically in German and shares the English key.
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9,
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "juin": 6, "juillet": 7,
    "août": 8, "septembre": 9,
    "gennaio": 1, "febbraio": 2, "giugno": 6, "luglio": 7, "settembre": 9,
    "janeiro": 1, "junho": 6, "julho": 7, "setembro": 9,
}


def _to_iso(raw: str) -> str | None:
    """Normalise a bolded date to ISO, whatever language wrote it."""
    text = raw.strip()
    for pattern in (
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일",
    ):
        match = re.fullmatch(pattern, text)
        if match:
            return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.fullmatch(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", text)
    if match:
        return f"{match.group(3)}-{_MONTHS[match.group(1).lower()]:02d}-{int(match.group(2)):02d}"
    # The month name is matched with \w rather than an ASCII class: French
    # "août" and German "März" both carry accents, and an ASCII-only class
    # silently skips the date rather than failing loudly.
    match = re.fullmatch(r"(\d{1,2})\.?\s*(?:de\s+)?(\w+)\s*(?:de\s+)?(\d{4})", text, re.UNICODE)
    if match and match.group(2).lower() in _MONTHS:
        return f"{match.group(3)}-{_MONTHS[match.group(2).lower()]:02d}-{int(match.group(1)):02d}"
    return None


class TestProviderCount:
    """The cloud-provider count, stated three times per file as a digit."""

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_count_matches_registry(self, name: str) -> None:
        text = _read(name)
        stale = rf"(?<![\d.]){CLOUD_PROVIDER_COUNT - 1}(?![\d.])\s*(?:cloud|Cloud)"
        wrong = re.findall(stale, text)
        assert not wrong, (
            f"{name} states {CLOUD_PROVIDER_COUNT - 1} cloud providers; the registry has "
            f"{CLOUD_PROVIDER_COUNT}."
        )
        stated = len(re.findall(rf"(?<![\d.]){CLOUD_PROVIDER_COUNT}(?![\d.])", text))
        assert stated >= 3, (
            f"{name} mentions {CLOUD_PROVIDER_COUNT} only {stated} time(s). The count appears in "
            f"the tagline, the Providers heading and the streaming bullet - if one was missed, it "
            f"is still stating the old number."
        )


class TestTemperatureModelList:
    """The backticked list of models called without a temperature field."""

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_list_equals_registry(self, name: str) -> None:
        line = next(
            line
            for line in _read(name).split("\n")
            if "--temperatures 0" in line and "claude-opus-4-7" in line
        )
        listed = {tok for tok in re.findall(r"`([^`]+)`", line) if not tok.startswith("--")}
        assert listed == TEMPERATURE_OMITTED, (
            f"{name} lists {len(listed)} models as omitting temperature; the registry has "
            f"{len(TEMPERATURE_OMITTED)}. Missing: {sorted(TEMPERATURE_OMITTED - listed)}. "
            f"Extra: {sorted(listed - TEMPERATURE_OMITTED)}."
        )


class TestStaticGroupTables:
    """Every static group row, member for member, against MODEL_GROUPS."""

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_group_membership_matches_registry(self, name: str) -> None:
        documented: dict[str, list[str]] = {}
        for row in _table_rows(_read(name), "`all-premium`"):
            # `all-premium` / `all-flagship` documents two aliases in one cell.
            # Both are real MODEL_GROUPS keys, so both are checked - reading
            # only the first left `all-flagship` unverified.
            members = [m.strip() for m in row[1].split(",")]
            for alias in (a.strip().strip("`") for a in row[0].split("/")):
                documented[alias] = members

        # Coverage before contents: a row silently dropped from the table, or a
        # group added to MODEL_GROUPS without a row, has to fail here. The old
        # `assert rows` only checked non-emptiness, which stayed true while two
        # of the five rows were being skipped.
        assert set(documented) == STATIC_GROUPS, (
            f"{name} documents groups {sorted(documented)}; the registry's static groups are "
            f"{sorted(STATIC_GROUPS)}. Missing: {sorted(STATIC_GROUPS - set(documented))}. "
            f"Extra: {sorted(set(documented) - STATIC_GROUPS)}."
        )

        for group, members in documented.items():
            assert MODEL_GROUPS[group] == members, (
                f"{name} group {group!r} disagrees with MODEL_GROUPS. "
                f"README: {members}. Registry: {MODEL_GROUPS[group]}."
            )


class TestDates:
    """The several verification dates, which are deliberately not equal."""

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_date_set_matches_expected(self, name: str) -> None:
        found = set()
        for raw in re.findall(r"\*\*([^*]*\d{4}[^*]*)\*\*", _read(name)):
            iso = _to_iso(raw)
            if iso is not None:
                found.add(iso)
        assert found == EXPECTED_DATES, (
            f"{name} states dates {sorted(found)}; expected {sorted(EXPECTED_DATES)}. These are "
            f"separate facts - a correction to one must not be applied to the others."
        )

    def test_pricing_date_matches_the_constant(self) -> None:
        from cli_modelarium.pricing import PRICING_AS_OF

        assert PRICING_AS_OF in EXPECTED_DATES, (
            f"PRICING_AS_OF is {PRICING_AS_OF} but the READMEs state {sorted(EXPECTED_DATES)}."
        )


class TestStructuralParity:
    """What may differ between README.md and a translation, and nothing else."""

    @pytest.mark.parametrize("name", TRANSLATED_READMES)
    def test_heading_count_matches_english_minus_exceptions(self, name: str) -> None:
        english = _headings(_read(ENGLISH_README))
        expected = [
            h for h in english if not any(frag in h for frag in ENGLISH_ONLY_HEADINGS)
        ]
        actual = _headings(_read(name))
        assert len(actual) == len(expected), (
            f"{name} has {len(actual)} headings; README.md minus the "
            f"{len(ENGLISH_ONLY_HEADINGS)} English-only sections has {len(expected)}. Either a "
            f"section was dropped from the translation, or one was added to README.md that "
            f"belongs in ENGLISH_ONLY_HEADINGS."
        )

    @pytest.mark.parametrize("name", TRANSLATED_READMES)
    def test_english_only_sections_are_actually_absent(self, name: str) -> None:
        headings = _headings(_read(name))
        present = [
            frag for frag in ENGLISH_ONLY_HEADINGS if any(frag in h for h in headings)
        ]
        assert not present, f"{name} carries sections declared English-only: {present}"

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_heading_levels_are_in_the_same_order(self, name: str) -> None:
        english = _headings(_read(ENGLISH_README))
        expected = [
            h.split(" ")[0]
            for h in english
            if not any(frag in h for frag in ENGLISH_ONLY_HEADINGS)
        ]
        actual = [h.split(" ")[0] for h in _headings(_read(name))]
        if name == ENGLISH_README:
            actual = [h.split(" ")[0] for h in english]
            expected = actual
        assert actual == expected, f"{name}: heading level sequence diverges from README.md"

    @pytest.mark.parametrize(
        "heading_fragment", ["Evaluation features", "Comparison methodology"]
    )
    @pytest.mark.parametrize("name", TRANSLATED_READMES)
    def test_bullet_counts_match_english(self, name: str, heading_fragment: str) -> None:
        # These two sections are where `--runs` went missing from all eight
        # translations for four releases: the English bullet documenting the
        # flag simply had no counterpart.
        english_headings = _headings(_read(ENGLISH_README))
        # Index into the FILTERED English list: the translations do not carry
        # the English-only sections, so raw positions do not line up.
        shared = [
            h for h in english_headings if not any(f in h for f in ENGLISH_ONLY_HEADINGS)
        ]
        index = next(i for i, h in enumerate(shared) if heading_fragment in h)
        translated_headings = _headings(_read(name))
        expected = len(_bullets(_read(ENGLISH_README), shared[index]))
        actual = len(_bullets(_read(name), translated_headings[index]))
        assert actual == expected, (
            f"{name} has {actual} bullets under the section matching {heading_fragment!r}; "
            f"README.md has {expected}."
        )


class TestAllGroupExclusions:
    """`all` excludes three provider classes, and the docs must name them."""

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_every_excluded_provider_is_named(self, name: str) -> None:
        line = next(line for line in _read(name).split("\n") if line.startswith("- `all` "))
        lowered = line.lower()
        for provider in ("openrouter", "nvidia"):
            assert provider in lowered, (
                f"{name} describes the `all` group without naming {provider!r}. "
                f"_resolve_all_cloud excludes local, openrouter and nvidia; a reader who "
                f"configures that provider's key and runs `--models all` gets nothing from it."
            )

    def test_the_exclusion_set_is_what_the_docs_claim(self) -> None:
        # Pins the code side of the assertion above: if a fourth exclusion is
        # added, this fails and the nine files need a sentence, rather than the
        # docs silently going stale again.
        import inspect

        from cli_modelarium import cli

        source = inspect.getsource(cli._resolve_all_cloud)
        match = re.search(r'provider in \(([^)]*)\)', source)
        assert match is not None, "could not find the exclusion tuple in _resolve_all_cloud"
        excluded = {tok.strip().strip('"') for tok in match.group(1).split(",") if tok.strip()}
        assert excluded == {"local", "openrouter", "nvidia"}, (
            f"_resolve_all_cloud now excludes {sorted(excluded)}. Update the `all` group "
            f"sentence in all nine READMEs, then update this test."
        )


# The supported-providers table, row by row, in the order all nine files use it.
# Matched on the leading brand token of the first cell: those survive translation
# where the surrounding prose does not ("registered IDs" becomes "registrierte
# IDs", but "OpenRouter" stays "OpenRouter").
PROVIDER_TABLE_ROWS = [
    ("OpenAI (", "openai"),
    ("Anthropic (", "anthropic"),
    ("Google (", "google"),
    ("xAI (", "xai"),
    ("DeepSeek (", "deepseek"),
    ("Mistral (", "mistral"),
    ("Groq (", "groq"),
    ("OpenRouter (", "openrouter"),
    ("Alibaba/DashScope (", "dashscope"),
    ("Z.AI/GLM (", "zai"),
    ("NVIDIA NIM (", "nvidia"),
    ("Moonshot AI / Kimi (", "moonshot"),
]
LOCAL_ROW_COUNT = 4
# What a `not-priced` provider renders as. The four local rows have nothing to
# verify - their cost column already says Free - so a status word there would be
# a category error rather than a caveat.
NOT_PRICED_CELL = "\u2014"


def _provider_table(text: str) -> list[list[str]]:
    """Return the supported-providers table's data rows, cell by cell.

    Located by the first cell of its first row rather than by a heading: the
    headings are translated and an earlier release found English line numbers
    landing up to 154 lines off in the translations.
    """
    lines = text.split("\n")
    start = next(
        i
        for i, line in enumerate(lines)
        if line.startswith("|") and line.split("|")[1].strip().startswith("OpenAI (")
    )
    rows = []
    while start < len(lines) and lines[start].startswith("|"):
        rows.append([c.strip() for c in lines[start].split("|")[1:-1]])
        start += 1
    return rows


class TestVerificationColumn:
    """The table's verification cell, pinned against PRICING_VERIFICATION.

    The status words are left in English and backticked on purpose. This table
    translates its PROSE cells - NVIDIA's "No published rate" is "Kein
    veröffentlichter Tarif" in German - but not its IDENTIFIER cells, and a
    status drawn from a closed set in the code is an identifier. Backticking it
    says so, keeps this assertion a literal string comparison in all nine files
    rather than nine translation tables, and matches how TestTemperatureModelList
    already pins model ids. The translated header carries the meaning.
    """

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_every_row_has_a_verification_cell(self, name: str) -> None:
        rows = _provider_table(_read(name))
        assert len(rows) == len(PROVIDER_TABLE_ROWS) + LOCAL_ROW_COUNT
        for row in rows:
            assert len(row) == 5, f"{name}: {row[0]!r} has {len(row)} cells, expected 5"

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_cells_match_the_registry(self, name: str) -> None:
        rows = _provider_table(_read(name))
        for (prefix, provider), row in zip(PROVIDER_TABLE_ROWS, rows):
            assert row[0].startswith(prefix), (
                f"{name}: expected the {provider} row to start {prefix!r}, got {row[0][:40]!r}. "
                f"The table's row order is part of what this test pins."
            )
            expected = f"`{PRICING_VERIFICATION[provider]}`"
            assert row[4] == expected, (
                f"{name}: the {provider} row says {row[4]!r}; PRICING_VERIFICATION says "
                f"{expected}. The constant is the source of truth - fix the table, not this test."
            )

    @pytest.mark.parametrize("name", ALL_READMES)
    def test_local_rows_carry_no_status(self, name: str) -> None:
        rows = _provider_table(_read(name))[len(PROVIDER_TABLE_ROWS) :]
        assert PRICING_VERIFICATION["local"] == NOT_PRICED
        for row in rows:
            assert row[4] == NOT_PRICED_CELL, (
                f"{name}: local row {row[0]!r} should render {NOT_PRICED_CELL!r}, not {row[4]!r}"
            )

    def test_every_cloud_provider_appears_exactly_once(self) -> None:
        # Pins the code side: a thirteenth provider added to the registry has to
        # gain a table row, rather than the table silently describing twelve.
        listed = {p for _, p in PROVIDER_TABLE_ROWS}
        assert listed == set(all_known_providers()) - {"local"}
        assert len(PROVIDER_TABLE_ROWS) == len(listed), "a provider is listed twice"


class TestTableDeclaredCounts:
    """Three rows state a registered-ID count as a digit. Those can go stale.

    The example model NAMES cannot be pinned - "Claude Opus 5" is a marketing
    name, not a registry id, and mapping one to the other would be editorial
    machinery that goes stale itself. The counts are different: they are digits,
    which this file's convention already matches, and they are exactly what a
    sweep that adds or removes a row invalidates.
    """

    COUNTED = {
        "openrouter": "OpenRouter (",
        "nvidia": "NVIDIA NIM (",
        "moonshot": "Moonshot AI / Kimi (",
    }

    @pytest.mark.parametrize("name", ALL_READMES)
    @pytest.mark.parametrize("provider", sorted(COUNTED))
    def test_declared_count_matches_the_registry(self, name: str, provider: str) -> None:
        rows = _provider_table(_read(name))
        cell = next(r[0] for r in rows if r[0].startswith(self.COUNTED[provider]))
        stated = re.search(r"(\d+)", cell)
        assert stated is not None, f"{name}: no count in {cell!r}"
        actual = sum(1 for v in PRICING.values() if v["provider"] == provider)
        assert int(stated.group(1)) == actual, (
            f"{name}: the {provider} row claims {stated.group(1)} registered IDs; "
            f"the registry has {actual}."
        )
