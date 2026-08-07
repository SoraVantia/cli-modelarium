#!/usr/bin/env bash
# Run a curated model group with a single flag (model groups).
#
# Static groups: all-premium (= all-flagship), all-budget, all-reasoning,
# all-cheap, all-open-weight. They expand verbatim - every member's provider
# needs a key and the run aborts on the first one missing. `all` and
# `all-local` are the exception; they resolve to what you have configured.
# all-budget = gpt-5.4-nano, claude-haiku-4-5, gemini-3.1-flash-lite,
# grok-4.20-0309-non-reasoning, deepseek-v4-flash, mistral-small-latest,
# qwen3.7-plus, glm-4.5-air.

set -euo pipefail

cli-modelarium "Explain the CAP theorem in 2 sentences." --models all-budget
