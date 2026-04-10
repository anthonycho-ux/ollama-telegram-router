# Temperature Study

**Purpose:** Find the temperature setting that eliminates argument-level parsing misses on qwen3.5:4b.

## Setup

- Model: qwen3.5:4b
- Prompts: 10 prompts (subset of 30-prompt suite)
- Temperatures tested: 0.0, 0.1, 0.7
- Metric: args-level miss rate per temperature

## Results

| Temperature | Tool Miss | Args Miss | Verdict |
|-------------|-----------|-----------|---------|
| 0.0 | 0 | 0 | **BEST** — perfect on all 10 |
| 0.1 | 0 | ~1/run | Args-level variability |
| 0.7 | variable | variable | Chaotic — expected |

## Conclusion

**Use `temperature=0.0`** for deterministic tool calling.
qwen3.5:4b is not improved by temperature randomization — it only introduces variability in argument parsing.

## Application

Set in benchmark.py and telegram-bridge.js:

```bash
export OLLAMA_TEMPERATURE=0.0
# or in the API call:
json={"model": "qwen3.5:4b", "temperature": 0.0, ...}
```
