"""
Local RU→EN tutor via Ollama (interactive CLI)

Prereqs:
- Ollama installed and working:
    ollama run qwen2.5:7b
- Python 3.10+

Usage:
    python LLM.py
Type Russian text, press Enter. Type /quit to exit.
"""

from __future__ import annotations

import subprocess
import sys

DEFAULT_MODEL = "qwen2.5:7b"

PROMPT_TEMPLATE = """You are a Russian→English translation tutor.
For the Russian text below, output:

Natural English translation

Word-by-word gloss (tokenized)

Grammar notes: cases, aspect, tense, gender/number, syntax/word order

2 alternative English phrasings and why

Russian: «{russian}»
"""


def run_ollama(prompt: str, model: str) -> str:
    """Run Ollama with a prompt and return output."""
    try:
        proc = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        raise RuntimeError("Could not find 'ollama' on PATH. Run: where ollama")

    if proc.returncode != 0:
        stderr = proc.stderr.strip() or "(no stderr)"
        raise RuntimeError(f"Ollama error (code {proc.returncode}):\n{stderr}")

    return proc.stdout.strip()


def main() -> int:
    model = DEFAULT_MODEL

    print(f"RU→EN Tutor (local) using Ollama model: {model}")
    print("Enter a Russian sentence.")
    print("Commands:")
    print("  /model <name>  (switch model, e.g. qwen2.5:14b)")
    print("  /quit\n")

    while True:
        try:
            line = input("RU> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not line:
            continue

        if line.lower() in {"/quit", "/exit"}:
            print("Bye.")
            return 0

        if line.lower().startswith("/model "):
            new_model = line.split(" ", 1)[1].strip()
            if new_model:
                model = new_model
                print(f"[ok] Model set to: {model}\n")
            else:
                print("[warn] Usage: /model qwen2.5:14b\n")
            continue

        prompt = PROMPT_TEMPLATE.format(russian=line)

        try:
            out = run_ollama(prompt, model)
            print("\n" + out + "\n")
        except Exception as e:
            print(f"[error] {e}\n", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
