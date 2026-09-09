#!/usr/bin/env bash
# Reproducibility analysis - run the same prompt N times across models
# to see variance in latency, tokens, and outputs.
#
# Output includes mean/median/stdev of latency, coefficient of variation,
# mode answer, and output diversity per model.

set -euo pipefail

# --bootstrap-seed is pinned deliberately. Without it the bootstrap draws a
# fresh resample every invocation, so two runs over byte-identical data produce
# different interval bounds - measured at 119.6 against 119.1 - and a figure you
# cannot reproduce is not one you can cite. The CSV now records the seed, the
# method, the resample count and the per-metric sample size alongside the
# bounds, so the file says what produced it.
cli-modelarium "What is quantum computing in one paragraph?" \
  --models gpt-5.5,claude-opus-4-7,gemini-3.1-pro-preview \
  --runs 10 \
  --bootstrap-seed 42 \
  --output reproducibility_results.csv \
  --output-format csv
