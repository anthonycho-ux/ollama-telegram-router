# ollama-telegram-router

*I built a Telegram bot that routes messages to local LLMs. Then I spent three weeks proving I'd been doing it wrong.*

[한국어](./README.ko.md)

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

It looked smart. It felt systematic. I had read enough to know that bigger models were better for complex tasks and smaller models were faster for simple ones. The keywords were just the implementation.

The problem wasn't the logic. The problem was that the logic had no memory.

---

## What Karpathy Taught Me to Build

Andrej Karpathy's approach to autoregressive model work is simple in principle: **build fast, measure, learn, repeat.** Not think harder about the architecture. Not read more papers. Run the experiment and let the data correct your beliefs before you've had time to get attached to them.

That's what I tried to do here.

I built a benchmark loop — 30 prompts, two models, every 5 minutes. Autonomous. Self-healing. No babysitting. I didn't start with a conclusion. I started with a disagreement I couldn't resolve with intuition alone, and I built the thing that would settle it.

The prompts weren't synthetic benchmarks. They were the actual things my Telegram bot does: bash commands, file reads, file writes, directory listings. If a model could handle those reliably, I wanted to know which one and why. If it couldn't, I wanted to know that too.

---

## The Experiment

In April 2026 I ran the same 30 prompts against qwen3.5:4b and gemma4:e2b, every 5 minutes, for 71 cycles straight. No interruption. No babysitting.

The rig: NVIDIA RTX 3090 (24GB VRAM, ~15GB free during benchmark), AMD Ryzen 7 5700G, 16 cores. The VRAM ceiling is real — at 26GB total for the three-model stack, there were experiments I couldn't run because they wouldn't fit in memory simultaneously.

71 cycles × 30 prompts × 2 models = 42,600 individual tool calls measured.

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

More striking: **the two models disagreed on which was better in 31% of cycles.** When they disagreed, it was almost always qwen3.5:4b that dipped (22 of 31 disagreement cycles). gemma4:e2b dipped in only 5. And in the 8 cycles where both models dipped simultaneously — the hardest failures — they never hit their floor on the same prompts. The failures were complementary, not overlapping.

The data didn't just correct the router. It corrected a belief I hadn't realized I was carrying — that I was making the safe choice by routing to the slower model for anything that seemed complex.

---

## The Three Numbers That Changed Everything

### 1. temperature = 0.0

The first temperature study nearly didn't happen. It was a 10-prompt side run, quick and dirty.

qwen3.5:4b at temperature 0.1: 28/30. The same temperature I'd been running in production.

Same model, same prompts, temperature set to 0.0: **10/10 on the 10-prompt subset.**

One setting. No model change. No prompt engineering. I went back through the 71-cycle log and found 8 cycles where qwen had scored 28/30 — each of those was probably a temperature artifact, not a genuine model failure.

Applied to production: one line change. Combined score: ~1.97.

### 2. OLLAMA_KEEP_ALIVE = -1

The experiment loop had a cold-start problem. Every time a model loaded from disk, it took 50–60 seconds before the first result came back. Running continuously, 71 cycles would have taken 60+ hours of warmup alone.

Then I found `OLLAMA_KEEP_ALIVE=-1`. One environment variable. The models stayed hot in VRAM between cycles.

Cold-start dropped from 50 seconds to under 1.

The loop that couldn't run in a reasonable time now ran in six hours. Without it, I'd have run maybe 10 cycles, seen noisy early data, and drawn the wrong conclusions. The entire experiment was downstream of this one variable.

### 3. NUM_PARALLEL = 8

Before tuning, single-prompt latency: 2.11 seconds.

After setting `OLLAMA_NUM_PARALLEL=8`: 0.86 seconds. **2.4x faster.**

The benchmark loop was also a performance optimization loop. I found two settings that together reduced total cycle time by more than half.

---

## What I Learned About Myself

The keyword router wasn't just technically limited. It was comfortable. Every guess it made looked like a decision. I could defend any of them in a conversation: *"I route to gemma for complex tasks because..."*

The experiment loop was less comfortable. It kept score. It told me something true that I hadn't asked it to measure, every 5 minutes.

Over 71 cycles, the confidence intervals narrowed. Not to zero — gemma4:e4b is still running its full benchmark (50+ cycles in), and the COMPLEX → e4b routing is still provisional. But the comparison between qwen3.5:4b and gemma4:e2b is now clean enough to route on.

The loop is still running. Every 5 minutes it scores both models and writes the result somewhere I can read. I don't make routing decisions anymore. I let the loop tell me what the routing should be.

---

## What Didn't Work (And Why That's In Here)

I tried several things that didn't make the final system, and the data is the reason I know they didn't work:

**Planner/caller decomposition.** The Multi-LLM Agent and ACAR papers both show that separating planning from execution adds an extra model pass. At 99% accuracy, the latency cost outweighs the accuracy benefit. I didn't need to read the papers for this — the combined score math told me the same thing.

**Keyword refinement.** Adding more keywords, or finer-grained keywords, didn't solve the fundamental problem: the keyword was capturing the *appearance* of intent, not the intent itself. "calculate" in a spreadsheet context and "calculate" in a financial context require the same word and opposite routing decisions. More keywords just made the false confidence worse.

**gemma4:e4b in the 3-model stack.** e4b scored 26% higher than e2b in the proxy study (8/10 vs 6/10 on a 10-prompt subset). But the VRAM math is tight: gemma4-26b (17GB) + e4b (9.6GB) + qwen3.5:4b (3.4GB) = 30GB. I have 26GB. The full benchmark for e4b is still accumulating — when it's clean, I'll know whether to drop qwen, drop gemma4-26b, or accept the latency hit from sequential loading.

The open question that interests me most: what if the routing decision itself could be adaptive per-query? The ACAR paper describes a σ-probe approach — run each message through both models, measure response variance, and route based on that. That's the next experiment. It needs its own benchmark loop. The one I'm running now is what makes that experiment legible.

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

The COMPLEX → gemma routing is provisional. gemma4:e4b is the target (26% higher combined in proxy study, more VRAM, better reasoning), but the full 30-prompt benchmark is still running. When the data is in, the routing updates automatically.

---

## Running Your Own

Drop `router.js` into your Telegram bridge:

```javascript
const { routeMessage } = require('./router');

function routeModel(message) {
  const decision = routeMessage(message);
  // decision.model      → "qwen3.5:4b" or "gemma4:e4b"
  // decision.category   → "TOOL_USE" | "CASUAL" | "COMPLEX" | "ROUTINE"
  // decision.reasoning  → cites the cycle count and metric behind the decision
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
