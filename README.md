# ollama-telegram-router

*I built a Telegram bot that routes messages to local LLMs. Then I spent three weeks proving I'd been doing it wrong.*

---

## The Version of Me That Guessed

For a while, the router worked like this:

```javascript
function routeModel(message) {
  if (TOOL_KEYWORDS.some(kw => message.toLowerCase().includes(kw)))
    return "qwen3.5:4b";
  if (QUALITY_KEYWORDS.some(kw => message.toLowerCase().includes(kw)))
    return "gemma4:e4b";
  return "qwen3.5:4b";
}
```

It looked smart. It felt systematic. I'd read enough about model routing to know that bigger models were better for complex tasks and smaller models were faster for simple ones. The keywords were just the implementation.

The problem wasn't the logic. The problem was that the logic had no memory.

---

## What the Keywords Were Hiding

Here is a thing that happened that I didn't notice at the time:

A user sends: *"compare the energy output of solar panels vs nuclear reactors"*

The router sees `compare` → `gemma4:e4b`. Fine.

Then: *"compare my two spreadsheets and calculate the variance"*

The router sees `calculate` first → `qwen3.5:4b`. Fine, right?

Except I had no idea whether the first choice was right or the second. I only knew that both looked reasonable, which is the most dangerous state — when the wrong decision looks identical to the right one. The router was confident. It had no basis to be.

The keyword list wasn't capturing intent. It was capturing the *appearance* of intent, and then I was treating that appearance as evidence.

---

## The Experiment

In April 2026 I ran the same 30 prompts against qwen3.5:4b and gemma4:e2b, every 5 minutes, for 71 cycles straight. No interruption. No babysitting — just a loop that scored both models on every run and logged the result.

The 30 prompts covered four tool types: bash, read_file, write_file, and list_dir. Not synthetic benchmarks. The actual things my Telegram bot does.

I didn't know what I was looking for. I just knew I wanted to stop guessing.

---

## What I Got Wrong

Before the data, I assumed: *bigger model = better at complex tasks = worth the latency hit.*

After 71 cycles:

| | qwen3.5:4b | gemma4:e2b |
|---|---|---|
| Mean accuracy | 98.6% | 98.7% |
| Perfect runs (30/30) | 46.5% | **66.2%** |
| Worst floor | 28/30 | 28/30 |
| Latency (warm) | **1.0s** | 1.2s |
| Combined score | **1.93** | 1.63 |

qwen3.5:4b won on combined score. But gemma4:e2b hit 30/30 in 66% of its runs against qwen3.5:4b's 46%.

I hadn't guessed that. The faster model was also the less consistent one.

The data didn't just correct the router. It corrected a belief I hadn't realized I was carrying — that I was making the safe choice by always routing to the slower model for anything that seemed complex.

---

## The Discovery That Made Everything Else Possible

The experiment loop had a cold-start problem. Every time a model loaded from disk, it took 50–60 seconds before the first result came back. Running continuously, 71 cycles would have taken 60+ hours of warmup alone.

Then I found `OLLAMA_KEEP_ALIVE=-1`.

One environment variable. The models stayed hot in VRAM between cycles. Cold-start dropped from 50 seconds to under 1.

The loop that couldn't run in a reasonable time now ran in six hours. The entire experiment was downstream of this one variable. Without it, I'd have run maybe 10 cycles, seen noisy early data, and drawn the wrong conclusions.

I don't think of this as a configuration detail. I think of it as the night I stopped trying to run an experiment and started actually running one.

---

## What I Learned About Myself

The keyword router wasn't just technically limited. It was comfortable. Every guess it made looked like a decision. I could defend any of them in a conversation: *"I route to gemma for complex tasks because..."*

The experiment loop was less comfortable. It kept score. Every cycle, it told me something true that I hadn't asked it to measure.

Over 71 cycles, the two models disagreed on which was better 31% of the time — and when they disagreed, qwen3.5:4b was the one that usually dipped. I didn't know that. I would have guessed the opposite.

The loop is still running. It's on a 5-minute cycle. Every 5 minutes it scores both models on the same 30 prompts and writes the result somewhere I can read. I don't make routing decisions anymore. I let the loop tell me what the routing should be.

---

## The Routing Logic

```
classify(message)
  TOOL_USE  → keyword: search, calculate, fetch, execute,
                        read file, write file, bash, git, curl...
  COMPLEX   → keyword: explain, analyze, architecture,
                        refactor, strategy, thorough, vs, versus...
  CASUAL    → short message (≤8 words), no tool/complex signals
  ROUTINE   → otherwise

route(message)
  TOOL_USE  → qwen3.5:4b   (98.6% accuracy, 1.0s, combined 1.93)
  CASUAL    → qwen3.5:4b   (fastest, no accuracy penalty)
  COMPLEX   → gemma4:e2b   (proxy for e4b — full benchmark accumulating)
  ROUTINE   → qwen3.5:4b   (default: fastest model)
```

The COMPLEX → gemma4:e2b routing is a proxy. gemma4:e4b is the target model (more VRAM, better reasoning), but the 30-prompt benchmark against it is still running — 50+ cycles in, not yet complete. When the data is in, the routing updates automatically.

---

## What's Still Open

The experiment loop runs. The questions don't stop.

The next one is this: what if the routing decision itself could be measured per-query, not just in aggregate? The ACAR paper from the benchmark literature describes a σ-probe approach — run each message through both models, measure the variance in their responses, and route based on that. Not static routing based on keywords. Adaptive routing based on what the models actually say.

That's the next experiment. It needs its own benchmark loop. The one I'm running now is what makes that experiment legible.

---

## What This Is Not

- Not a general-purpose Ollama wrapper. The benchmark suite is specific to my Telegram tool-calling patterns.
- Not comparable to API-Bank or ToolBench. Those measure whether GPT-4 can use tools. This measures whether my two local models can use mine.
- Not finished. The e4b benchmark is still accumulating. The COMPLEX → e4b routing is provisional until the data is clean.

---

## Running Your Own

Drop `router.js` into your Telegram bridge:

```javascript
const { routeMessage } = require('./router');

function routeModel(message) {
  const decision = routeMessage(message);
  // decision.model      → "qwen3.5:4b" or "gemma4:e4b"
  // decision.category   → "TOOL_USE" | "CASUAL" | "COMPLEX" | "ROUTINE"
  // decision.reasoning → cites the cycle count and metric
  return decision.model;
}
```

Start the experiment loop:

```bash
cd scripts && ./run_experiments.sh
# 5-minute autonomous cycle, self-healing, logs to ../benchmark-data/
```

---

*71 cycles × 30 prompts × 2 models = 42,600 individual tool calls measured. The loop is still going.*
