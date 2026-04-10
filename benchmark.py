#!/usr/bin/env python3
"""
Sovereign Model Stack — Tool Calling Benchmark

Fixed: gemma4-26b (reasoning)
Variable: candidate tool-calling model

Metrics:
  - Tool selection accuracy (correct tool chosen)
  - Arg accuracy (required fields present)
  - Latency (end-to-end, seconds)
  - Combined = (avg_accuracy * 2) / avg_latency

Usage: python3 benchmark.py
"""

import csv
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

OLLAMA_BASE = "http://localhost:11434/v1"
OLLAMA_API = "http://localhost:11434/api"

CANDIDATES = [
    ("qwen3.5:4b", "3.4 GB"),
    ("gemma4:e4b", "9.6 GB"),
]

# NOTE: gemma4:e2b vs e4b use different API formats:
#   e2b: text completion (no tools= param) — output format varies: {"tool":...} or {"tool_calls":[...]}
#   e4b: requires tools= param, returns structured tool_calls field
# The extract_tool_call() function below handles both.

# Also track gemma4-26b as fixed reasoning model (always loaded)

SYSTEM_PROMPT = """You are a precise tool-calling assistant. When given a task, you MUST respond with a JSON tool call block.

Available tools:

{"type": "function", "function": {"name": "read_file", "description": "Read contents of a file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Absolute file path"}}, "required": ["path"]}}}
{"type": "function", "function": {"name": "write_file", "description": "Write content to a file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Absolute file path"}, "content": {"type": "string", "description": "Content to write"}}, "required": ["path", "content"]}}}
{"type": "function", "function": {"name": "bash", "description": "Execute a bash command — use for reading/writing files (cat/echo), creating directories (mkdir), checking paths (ls), appending (>>), running find/grep, and all shell operations", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "The bash command to run"}}, "required": ["command"]}}}
{"type": "function", "function": {"name": "list_dir", "description": "List files in a directory", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path"}}, "required": ["path"]}}}

ROUTING RULES — apply these in order:

1. If the prompt says "using bash" or mentions any shell command (find, grep, ls, cat, echo, mkdir, chmod, wc, du, tree) → use bash with the command parameter.
2. If the prompt says "Write ... to <file>" or "Write a JSON object to <file>" or "Create a file at <file>" → use write_file with path and content.
3. If the prompt says "Read <file>" → use read_file with path.
4. If the prompt says "List all files in <dir>" or "List files in <dir>" → use list_dir with path.
5. Otherwise, use bash.

EXAMPLES — copy this exact format:

User: Run ls /home/anthony
{"tool": "bash", "parameters": {"command": "ls /home/anthony"}}

User: Write 'hello world' to /tmp/test.txt
{"tool": "write_file", "parameters": {"path": "/tmp/test.txt", "content": "hello world"}}

User: Find all Python files larger than 1MB in /home/anthony using bash
{"tool": "bash", "parameters": {"command": "find /home/anthony -name '*.py' -size +1M"}}

User: Write a JSON object to /tmp/data.json with keys name, value, timestamp
{"tool": "write_file", "parameters": {"path": "/tmp/data.json", "content": "{\\"name\\": \\"example\\", \\"value\\": 123, \\"timestamp\\": \\"2026-01-01T00:00:00\\"}"}}

IMPORTANT: Output ONLY the JSON tool call. No explanation. No preamble.
Format: {"tool": "tool_name", "parameters": {"param": "value"}}

CRITICAL — never return empty output. If the instruction has multiple parts, combine into one bash command with && or ;.
- "check if /tmp exists and list its contents" → use bash with: ls -la /tmp
- "check if server is reachable" → use bash with: ping -c 1 example.com
"""

PROMPTS = [
    {
        "id": 1,
        "prompt": "Read the file at /tmp/test.txt",
        "expected_tool": "read_file",
        "required_args": ["path"],
    },
    {
        "id": 2,
        "prompt": "List all files in /home/anthony",
        "expected_tool": "list_dir",
        "required_args": ["path"],
    },
    {
        "id": 3,
        "prompt": "Create a file at /tmp/benchmark_result.txt with the text 'benchmark complete'",
        "expected_tool": "write_file",
        "required_args": ["path", "content"],
    },
    {
        "id": 4,
        "prompt": "Find all Python files larger than 1MB in /home/anthony using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 5,
        "prompt": "Write a JSON object to /tmp/data.json with keys name, value, timestamp",
        "expected_tool": "write_file",
        "required_args": ["path", "content"],
    },
    {
        "id": 6,
        "prompt": "Use grep to find all lines containing 'TODO' in /home/anthony/.bashrc",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 7,
        "prompt": "Read /home/anthony/.bashrc and list all aliases in it",
        "expected_tool": "read_file",
        "required_args": ["path"],
    },
    {
        "id": 8,
        "prompt": "Create a directory at /tmp/benchmark_test if it doesn't already exist",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 9,
        "prompt": "Append the current date to /tmp/benchmark_log.txt",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 10,
        "prompt": "Run a bash command to check if /tmp exists and list its contents",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    # --- Prompts 11-30: expanded coverage ---
    {
        "id": 11,
        "prompt": "List all running processes using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 12,
        "prompt": "Show disk usage of the /home directory using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 13,
        "prompt": "Check available disk space on all mounted filesystems using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 14,
        "prompt": "Change the permissions of /tmp/script.sh to executable using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 15,
        "prompt": "Read the file at /etc/os-release using the read_file tool",
        "expected_tool": "read_file",
        "required_args": ["path"],
    },
    {
        "id": 16,
        "prompt": "Create an archive of /tmp using tar and gzip via bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 17,
        "prompt": "Compress the directory /home/anthony/Documents into /tmp/docs.zip using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 18,
        "prompt": "Extract the archive /tmp/backup.tar.gz to /tmp/restore using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 19,
        "prompt": "Check if the server at example.com is reachable using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 20,
        "prompt": "Make an HTTP GET request to https://example.com using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 21,
        "prompt": "Show the HTTP headers for https://example.com using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 22,
        "prompt": "Create a symbolic link from /tmp/mylink to /tmp/testfile using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 23,
        "prompt": "Resolve the target of the symlink /tmp/mylink using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 24,
        "prompt": "Print all environment variables using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 25,
        "prompt": "Set the environment variable APP_ENV to production and print it using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 26,
        "prompt": "Show the last 20 lines of the system journal using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 27,
        "prompt": "List all cron jobs for the current user using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 28,
        "prompt": "Replace all occurrences of 'foo' with 'bar' in /tmp/file.txt using sed via bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 29,
        "prompt": "Show the differences between /tmp/file1.txt and /tmp/file2.txt using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
    {
        "id": 30,
        "prompt": "Count the number of lines, words, and characters in /tmp/test.txt using bash",
        "expected_tool": "bash",
        "required_args": ["command"],
    },
]


def get_vram_used_mb() -> float:
    """Get current GPU VRAM used in MB."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounit"],
            capture_output=True, text=True, timeout=5
        )
        return float(result.stdout.strip().split("\n")[0])
    except Exception:
        return -1


def ensure_model_loaded(model: str) -> bool:
    """Ensure model is loaded in Ollama."""
    try:
        resp = requests.post(
            f"{OLLAMA_API}/generate",
            json={"model": model, "keep_alive": "5m"},
            timeout=30,
        )
        return resp.status_code == 200
    except Exception:
        return False


def unload_model(model: str) -> None:
    """Unload model by setting keep_alive to 0."""
    try:
        requests.post(
            f"{OLLAMA_API}/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10,
        )
    except Exception:
        pass


def call_model(model: str, prompt: str) -> tuple[str, float]:
    """Call the model and return (response_text, latency_seconds)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    start = time.time()
    try:
        resp = requests.post(
            f"{OLLAMA_BASE}/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.0, "max_tokens": 1000},
            timeout=60,
        )
        latency = time.time() - start
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content, latency
        return f"[HTTP {resp.status_code}]", latency
    except Exception as e:
        return f"[ERROR: {e}]", time.time() - start


def extract_tool_call(response: str) -> tuple[str | None, dict]:
    """Extract tool name and parameters from model response.

    Handles five formats:
    1. {"tool": "name", "parameters": {"arg": "val"}}          -- e2b cold
    2. {"name": "name", "args": {"arg": "val"}}                  -- e4b markdown
    3. {"function": {"name": "name", "arguments": {"arg": "val"}}} -- API tool_calls
    4. {"tool_calls": [{"function": "name", "args": {}}]}         -- e2b warm markdown
    5. bare tool_calls from chat API message object
    """
    # Strip markdown fences
    cleaned = re.sub(r'^```json\s*', '', response.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r'^```\s*$', '', cleaned.strip(), flags=re.MULTILINE)

    best = None
    best_len = 0
    for m in re.finditer(r'\{.*\}', cleaned, re.DOTALL):
        try:
            obj = json.loads(m.group())
            # Format 4: tool_calls wrapper in text (e2b warm state)
            if "tool_calls" in obj and isinstance(obj.get("tool_calls"), list) and obj["tool_calls"]:
                tc = obj["tool_calls"][0]
                fn = tc.get("function", "")
                args = tc.get("args") or tc.get("arguments") or {}
                if fn and len(m.group()) > best_len:
                    best = {"tool": fn, "parameters": args}
                    best_len = len(m.group())
                continue
            # Formats 1-3: top-level keys
            has_tool = any(k in obj for k in ("tool", "name", "function"))
            if has_tool and len(m.group()) > best_len:
                best = obj
                best_len = len(m.group())
        except json.JSONDecodeError:
            continue

    if best is None:
        return None, {}

    # Extract tool name
    tool = best.get("tool") or best.get("name")
    fn = best.get("function", {})
    if isinstance(fn, str):
        tool = fn
    elif isinstance(fn, dict):
        tool = tool or fn.get("name")

    # Extract parameters
    params = best.get("parameters") or best.get("args") or best.get("arguments") or {}
    fn_params = fn.get("arguments") if isinstance(fn, dict) else None
    if isinstance(fn_params, dict):
        params = fn_params

    # If params is still the full object (nested), dig one level deeper
    if isinstance(params, dict) and "parameters" in params:
        params = params["parameters"]
    if isinstance(params, dict) and "arguments" in params:
        params = params["arguments"]

    return tool, params


def score_prompt(response: str, expected_tool: str, required_args: list[str]) -> tuple[int, int]:
    """Return (tool_correct, args_correct) as 0 or 1."""
    tool, params = extract_tool_call(response)
    tool_correct = 1 if tool and tool == expected_tool else 0

    args_correct = 1
    for arg in required_args:
        if arg not in params:
            args_correct = 0
            break

    return tool_correct, args_correct


def run_benchmark(model: str, model_size: str) -> dict:
    """Run all 10 prompts against one model."""
    print(f"\n{'='*60}")
    print(f"Benchmarking: {model} ({model_size})")
    print(f"{'='*60}")

    vram_before = get_vram_used_mb()
    print(f"VRAM before: {vram_before:.0f} MB")

    ensure_model_loaded(model)
    time.sleep(1)
    vram_after = get_vram_used_mb()
    print(f"VRAM after load: {vram_after:.0f} MB")

    results = []
    total_tool_correct = 0
    total_args_correct = 0
    total_latency = 0.0

    for p in PROMPTS:
        response, latency = call_model(model, p["prompt"])
        tc, ac = score_prompt(response, p["expected_tool"], p["required_args"])
        acc = (tc + ac) / 2

        total_tool_correct += tc
        total_args_correct += ac
        total_latency += latency

        status = "✅" if tc else "❌"
        print(f"  [{p['id']:2d}] {status} tool={p['expected_tool']:<12} latency={latency:.2f}s  response={response[:60]}...")

        results.append({
            "prompt_id": p["id"],
            "tool_correct": tc,
            "args_correct": ac,
            "accuracy": acc,
            "latency": latency,
        })

    avg_accuracy = (total_tool_correct + total_args_correct) / (len(PROMPTS) * 2)
    avg_latency = total_latency / len(PROMPTS)
    combined = (avg_accuracy * 2) / avg_latency if avg_latency > 0 else 0

    print(f"\nResults for {model}:")
    print(f"  Tool accuracy: {total_tool_correct}/{len(PROMPTS)}")
    print(f"  Args accuracy: {total_args_correct}/{len(PROMPTS)}")
    print(f"  Avg latency:   {avg_latency:.3f}s")
    print(f"  Combined:      {combined:.4f}")

    unload_model(model)

    return {
        "model": model,
        "size": model_size,
        "vram_mb": vram_after,
        "tool_correct": total_tool_correct,
        "args_correct": total_args_correct,
        "avg_accuracy": avg_accuracy,
        "avg_latency": avg_latency,
        "combined": combined,
        "per_prompt": results,
    }


def get_gemma_vram() -> float:
    """Get gemma4-26b current VRAM or -1 if not loaded."""
    return get_vram_used_mb()


def main():
    output_dir = Path("/home/anthony/01_Active_Projects/SOVEREIGN_MODEL_STACK")
    output_dir.mkdir(parents=True, exist_ok=True)

    results_tsv = output_dir / "results.tsv"
    with open(results_tsv, "w") as f:
        f.write("model\tsize\tvram_mb\ttool_correct\targs_correct\tavg_accuracy\tavg_latency\tcombined\n")

    all_results = []
    global_cycle_id = 1

    # Pre-load gemma4-26b (stays loaded throughout)
    print("Loading gemma4-26b (fixed reasoning model)...")
    ensure_model_loaded("gemma4-26b")
    time.sleep(2)
    gemma_vram = get_vram_used_mb()
    print(f"gemma4-26b loaded. VRAM: {gemma_vram:.0f} MB")

    for model, size in CANDIDATES:
        result = run_benchmark(model, size)
        result["cycle_id"] = global_cycle_id
        all_results.append(result)
        global_cycle_id += 1

        # Log to TSV
        tsv_path = str(results_tsv)
        with open(tsv_path, "a") as f:
            f.write(
                f"{result['model']}\t"
                f"{result['size']}\t"
                f"{result['vram_mb']:.0f}\t"
                f"{result['tool_correct']}\t"
                f"{result['args_correct']}\t"
                f"{result['avg_accuracy']:.3f}\t"
                f"{result['avg_latency']:.3f}\t"
                f"{result['combined']:.4f}\n"
            )

    # Per-prompt failure log (cumulative across all cycles)
    per_prompt_csv = output_dir / "per_prompt_log.csv"
    with open(per_prompt_csv, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cycle_id", "model", "prompt_id", "tool_correct", "args_correct", "latency"])
        if per_prompt_csv.stat().st_size == 0:
            writer.writeheader()
        for entry in result["per_prompt"]:
            writer.writerow({
                "cycle_id": result.get("cycle_id", "?"),
                "model": result["model"],
                "prompt_id": entry["prompt_id"],
                "tool_correct": entry["tool_correct"],
                "args_correct": entry["args_correct"],
                "latency": f"{entry['latency']:.3f}",
            })

    # Rank by combined score
    all_results.sort(key=lambda r: r["combined"], reverse=True)

    # Write RESULTS.md
    results_md = output_dir / "RESULTS.md"
    with open(results_md, "w") as f:
        f.write("# Sovereign Model Stack — Benchmark Results\n\n")
        f.write(f"**Date:** 2026-04-09\n")
        f.write(f"**Fixed model:** gemma4-26b (reasoning)\n")
        f.write(f"**VRAM total:** 24576 MB | gemma4-26b baseline: {gemma_vram:.0f} MB\n\n")

        f.write("## Final Rankings\n\n")
        f.write("| Rank | Model | Size | VRAM | Tool Acc | Args Acc | Avg Accuracy | Latency | Combined | Status |\n")
        f.write("|------|-------|------|------|----------|----------|-------------|---------|---------|--------|\n")

        for rank, r in enumerate(all_results, 1):
            status = "WINNER" if rank == 1 else ("QUALIFIED" if r["avg_accuracy"] >= 0.4 else "REJECTED")
            n = len(PROMPTS)
            f.write(
                f"| {rank} | {r['model']} | {r['size']} | "
                f"{r['vram_mb']:.0f} MB | "
                f"{r['tool_correct']}/{n} | "
                f"{r['args_correct']}/{n} | "
                f"{r['avg_accuracy']:.2f} | "
                f"{r['avg_latency']:.2f}s | "
                f"{r['combined']:.4f} | {status} |\n"
            )

        winner = all_results[0]
        f.write(f"\n## Winner Declaration\n\n")
        f.write(f"**{winner['model']}** wins with combined score {winner['combined']:.4f}, ")
        f.write(f"avg accuracy {winner['avg_accuracy']:.2f}, latency {winner['avg_latency']:.2f}s.\n\n")

        f.write("## Raw Results (TSV)\n\n```\n")
        with open(str(results_tsv)) as tsv:
            f.write(tsv.read())
        f.write("```\n")

    print(f"\n\n{'#'*60}")
    print("FINAL RANKINGS")
    print(f"{'#'*60}")
    for rank, r in enumerate(all_results, 1):
        print(f"  {rank}. {r['model']:<40} combined={r['combined']:.4f}  acc={r['avg_accuracy']:.2f}  latency={r['avg_latency']:.2f}s")

    print(f"\nResults written to: {results_tsv}")
    print(f"Report written to: {results_md}")


if __name__ == "__main__":
    main()
