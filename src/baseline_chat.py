"""
Week 2 — Task 2: Working baseline model interaction (Gemini 3.8 Flash, free tier).

Goal: prove the app can call Gemini's API and get a response back, using the
system prompt loaded from prompts/vX.X.md.

"""

import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# Repo layout assumed: <repo_root>/src/baseline_chat.py and <repo_root>/prompts/vX.X.md
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_PROMPT_FILE = PROMPTS_DIR / "v1.0.md"


def load_system_prompt(prompt_path: Path = DEFAULT_PROMPT_FILE) -> str:
    """Extract just the prompt text from a prompts/vX.X.md file.

    Expects the file to contain a '## Prompt' heading; everything after that
    heading (up to the next '##' heading or end of file) is treated as the
    actual system prompt. Version notes above the heading are ignored.
    """
    text = prompt_path.read_text(encoding="utf-8")
    marker = "## Prompt"
    if marker not in text:
        raise ValueError(f"No '## Prompt' section found in {prompt_path}")
    after_marker = text.split(marker, 1)[1]
    # Stop at the next heading, if any, so trailing sections don't leak in
    prompt_text = after_marker.split("\n## ", 1)[0]
    return prompt_text.strip()


def call_gemini(user_message: str, system_prompt: str) -> str:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = requests.post(
        url,
        params={"key": api_key},
        json={
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": user_message}]}],
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


if __name__ == "__main__":
    system_prompt = load_system_prompt()
    test_message = "What is a SACCO?"

    print(f"Using prompt file: {DEFAULT_PROMPT_FILE.name}")
    print(f"Sending: {test_message}\n")

    reply = call_gemini(test_message, system_prompt)
    print("Model replied:")
    print(reply)
