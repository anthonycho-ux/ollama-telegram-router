#!/usr/bin/env node
/**
 * ollama-telegram-router — data-driven model routing for Telegram bots
 *
 * Grounded in autonomous benchmark evidence: 71 cycles, 30 prompts × 2 models.
 * Every routing decision cites the measured metric that backs it.
 *
 * Usage:
 *   const { routeMessage } = require('./router');
 *   const decision = routeMessage("search the web for climate data");
 *   console.log(decision.model);  // "qwen3.5:4b"
 */

const path = require("path");
const fs = require("fs");

// ─── Benchmark Data (71-cycle cumulative, as of 2026-04-09) ────────────────────
// Source: experiment_log.md, LOOP_STATUS.md
// Combined score = (tool_acc + args_acc) / avg_latency

const BENCHMARK = {
  "qwen3.5_4b": {
    model: "qwen3.5:4b",
    size: "3.4 GB",
    accuracy: 0.986,        // 98.6% mean over 71 cycles
    latency_s: 1.0,
    combined: 1.93,
    perfectRate: 0.465,     // 46.5% of runs hit 30/30
    floor: 28,             // worst single run was 28/30
    strengths: ["tool_use", "low_latency", "fast"],
  },
  "gemma4_e4b": {
    model: "gemma4:e4b",
    size: "9.6 GB",
    accuracy: null,         // 30-prompt benchmark in progress (cycles 50+)
    latency_s: null,
    combined: null,
    perfectRate: null,
    floor: null,
    strengths: ["reasoning", "complex", "quality"],
  },
  // e2b was the primary benchmark candidate — proxy for e4b until full data is in
  "gemma4_e2b": {
    model: "gemma4:e2b",
    size: "7.2 GB",
    accuracy: 0.987,        // 98.7% mean over 71 cycles
    latency_s: 1.2,
    combined: 1.63,
    perfectRate: 0.662,    // 66.2% perfect runs — most consistent model
    floor: 28,
    strengths: ["consistent", "reliable", "no_regression"],
  },
};

// ─── Classification Keywords ───────────────────────────────────────────────────
// Extracted from failure patterns observed in per_prompt_log.csv

const TOOL_KEYWORDS = [
  "search", "look up", "find", "calculate", "compute",
  "execute", "tool", "function", "api", "fetch", "call ",
  "open ", "read file", "write file", "git ", "bash", "shell",
  "http", "url", "web", "scrape", "crawl", "code", "debug",
  "install", "build", "compile", "test", "deploy",
  "docker", "kubernetes", "script", "terminal", "grep",
  "curl", "wget", "ssh", "chmod", "chown", "tar", "zip", "unzip",
];

const COMPLEX_KEYWORDS = [
  "explain", "analyze", "compare", "design", "architecture",
  "refactor", "optimize", "strategy", "research", "deep dive",
  "thorough", "comprehensive", "detailed",
  "why", "how does", "vs ", "versus", "difference between",
  "tradeoff", "trade-off", "plan", "implement",
  "build a", "create a", "develop",
  "evaluate", "assess", "recommend", "judge", "critique",
];

// ─── Classification ───────────────────────────────────────────────────────────

/**
 * Classify message intent — mirrors gemma-sense classify():
 * every pattern observed from the call log, not assumed.
 */
function classify(message) {
  const lower = message.toLowerCase();
  const words = message.trim().split(/\s+/);

  // Check keywords first — tool/complex intent overrides word count
  if (TOOL_KEYWORDS.some((kw) => lower.includes(kw))) return "TOOL_USE";
  if (COMPLEX_KEYWORDS.some((kw) => lower.includes(kw))) return "COMPLEX";
  // CASUAL only when short AND no tool/complex signals
  if (words.length <= 8) return "CASUAL";
  return "ROUTINE";
}

// ─── Routing ──────────────────────────────────────────────────────────────────

/**
 * Route message to optimal model — returns structured decision.
 *
 * Evidence chain for each decision:
 *   TOOL_USE  → qwen3.5:4b: 98.6% tool accuracy, 1.0s, combined 1.93
 *   CASUAL    → qwen3.5:4b: fastest, no accuracy penalty
 *   COMPLEX   → gemma4:e4b: better reasoning (e2b proxy, e4b accumulating)
 *   ROUTINE   → qwen3.5:4b: default, fastest
 *
 * @param {string} message - Raw Telegram message
 * @returns {{ model: string, modelKey: string, category: string,
 *              confidence: string, reasoning: string, benchmarkEvidence: object }}
 */
function routeMessage(message) {
  const category = classify(message);
  const qwen = BENCHMARK["qwen3.5_4b"];
  const e2b = BENCHMARK["gemma4_e2b"];
  const e4b = BENCHMARK["gemma4_e4b"];

  let model, modelKey, confidence, reasoning;

  switch (category) {
    case "TOOL_USE":
      model = qwen.model;
      modelKey = "fast";
      confidence = `HIGH — ${(qwen.accuracy * 100).toFixed(1)}% tool accuracy over 71 cycles, ${qwen.latency_s}s latency`;
      reasoning =
        `TOOL_USE: qwen3.5:4b scores 98.6% on tool tasks (71 cycles), ` +
        `1.0s latency. Combined score ${qwen.combined} — highest in benchmark. ` +
        `Source: experiment_log.md, cycle 1–71.`;
      break;

    case "CASUAL":
      model = qwen.model;
      modelKey = "fast";
      confidence = `HIGH — ${qwen.latency_s}s vs ${e2b.latency_s}s, negligible accuracy difference`;
      reasoning =
        `CASUAL (≤8 words): qwen3.5:4b is ${Math.round((1 - qwen.latency_s / e2b.latency_s) * 100)}% faster ` +
        `(${qwen.latency_s}s vs ${e2b.latency_s}s) with no measurable accuracy penalty on short queries. ` +
        `Source: LOOP_STATUS.md cumulative latency data.`;
      break;

    case "COMPLEX":
      if (e4b.accuracy !== null) {
        model = e4b.model;
        modelKey = "complex";
        confidence = `HIGH — e4b 30-prompt benchmark complete, ${(e4b.accuracy * 100).toFixed(1)}% accuracy`;
        reasoning = `COMPLEX: gemma4:e4b preferred for reasoning tasks (benchmark complete).`;
      } else {
        // Proxy via e2b — e4b VRAM fit is confirmed; 30-prompt data accumulating
        model = e2b.model;
        modelKey = "complex";
        confidence = "MEDIUM — e4b data accumulating; e2b proxy: 98.7% accuracy, 66.2% perfect runs";
        reasoning =
          `COMPLEX: gemma4:e2b (proxy for e4b) scores 98.7% accuracy, ` +
          `66.2% perfect runs — most consistent model in benchmark. ` +
          `gemma4:e4b 30-prompt benchmark in progress (cycles 50+). ` +
          `Source: LOOP_STATUS.md, VARIANCE_ANALYSIS.md.`;
      }
      break;

    case "ROUTINE":
    default:
      model = qwen.model;
      modelKey = "fast";
      confidence = "MEDIUM — default to fastest model";
      reasoning =
        `ROUTINE: qwen3.5:4b is default — 20% faster than e2b with no accuracy ` +
        `penalty for non-complex, non-tool queries. Source: 71-cycle latency study.`;
      break;
  }

  return {
    model,
    modelKey,
    category,
    confidence,
    reasoning,
    benchmarkEvidence: {
      qwenAccuracy: qwen.accuracy,
      qwenLatency: qwen.latency_s,
      qwenCombined: qwen.combined,
      e2bAccuracy: e2b.accuracy,
      e2bLatency: e2b.latency_s,
      e2bCombined: e2b.combined,
      e4bAccuracy: e4b.accuracy,  // null until benchmark complete
      e4bLatency: e4b.latency_s,
      e4bCombined: e4b.combined,
    },
  };
}

// ─── CLI ──────────────────────────────────────────────────────────────────────

if (require.main === module) {
  const message = process.argv.slice(2).join(" ") || "search the web for climate data";
  const d = routeMessage(message);

  console.log("\n╔══════════════════════════════════════╗");
  console.log("║     ollama-telegram-router             ║");
  console.log("╚══════════════════════════════════════╝");
  console.log(`  Message   : "${message}"`);
  console.log(`  Category  : ${d.category}`);
  console.log(`  Model     : ${d.model}  (${d.modelKey})`);
  console.log(`  Confidence: ${d.confidence}`);
  console.log(`  Reasoning : ${d.reasoning}`);
  console.log();
}
module.exports = { routeMessage, classify, BENCHMARK };
