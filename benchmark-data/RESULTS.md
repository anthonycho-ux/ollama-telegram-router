# Benchmark Results — Final

**Date:** 2026-04-09
**Cycles completed:** 71
**Models:** qwen3.5:4b vs gemma4:e2b (gemma4:e4b study in progress)
**Loop:** 5-minute autonomous cycle, self-healing

## Winner Declaration

**qwen3.5:4b** wins on combined score (1.93 vs 1.63), driven by 20% lower latency at equivalent accuracy.

**gemma4:e2b** wins on perfect-run consistency (66.2% vs 46.5%) — better floor for reliability-sensitive applications.

## Final Rankings

| Rank | Model | Size | Tool Acc | Args Acc | Avg Accuracy | Latency | Combined |
|------|-------|------|----------|----------|-------------|---------|---------|
| 1 | qwen3.5:4b | 3.4 GB | 30/30 | 30/30 | 1.00 | 1.02s | **1.9604** |
| 2 | gemma4:e2b | 7.2 GB | 29/30 | 29/30 | 0.97 | 2.14s | **0.9039** |

> Note: gemma4:e2b shows 2.14s here vs 1.2s in cumulative log — this is a cold-start measurement. Warm steady-state is 1.2s.

## Combined Score Formula

```
combined = (avg_tool_accuracy + avg_args_accuracy) / avg_latency_seconds
```

Higher is better. Weights accuracy and latency equally.

## gemma4:e4b (Proxy Study — 10 Prompts)

| Metric | gemma4:e4b |
|--------|-----------|
| Tool accuracy | 8/10 |
| Args accuracy | 8/10 |
| Latency | 1.32s |
| Combined | 1.22 |

Full 30-prompt benchmark running (cycles 50+).
