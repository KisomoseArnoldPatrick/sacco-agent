"""
Week 2 — Task 2: Working baseline model interaction (Gemini 3.6 Flash, free tier).

Goal: prove the app can call Gemini's API and get a response back, using the
system prompt loaded from prompts/vX.X.md.

"""

import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# Repo layout assumed: <repo_root>/src/baseline_chat.py and <repo_root>/prompts/vX.X.md
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_PROMPT_FILE = PROMPTS_DIR / "v1.0.md"


def load_system_prompt(prompt_path: Path = DEFAULT_PROMPT_FILE) -> str:
    """Build the system prompt from a prompts/vX.X.md file.

    Sends every '## ' section except '1. Purpose' and '10. Version Information',
    which are notes for the team and are not part of the instructions.
    """
    text = prompt_path.read_text(encoding="utf-8")
    sections = re.split(r"(?m)^## ", text)[1:]  # drop the title block before the first '## '
    skip = ("1. Purpose", "10. Version Information")
    kept = [s for s in sections if not s.startswith(skip)]
    if not kept:
        raise ValueError(f"No prompt sections found in {prompt_path}")
    return "\n\n".join("## " + s.strip() for s in kept)



def call_gemini(user_message: str, system_prompt: str, retries: int = 1) -> str:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": 0.2},
    }
    headers = {"x-goog-api-key": api_key}

    for attempt in range(retries + 1):
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        # Daily quota: retrying cannot help and only wastes requests
        if response.status_code == 429 and "PerDay" in response.text:
            raise RuntimeError(f"Daily quota exhausted: {response.text[:600]}")
        if response.status_code in (429, 500, 503) and attempt < retries:
            # per-minute limit: wait out the minute; other errors: short backoff
            time.sleep(60 if response.status_code == 429 else 2 ** attempt)
            continue
        if not response.ok:
            raise RuntimeError(f"{response.status_code}: {response.text[:1500]}")
        break

    data = response.json()
    candidates = data.get("candidates") or []
    if not candidates or "content" not in candidates[0]:
        raise RuntimeError(f"No usable reply: {data.get('promptFeedback') or candidates}")
    finish = candidates[0].get("finishReason")
    text = candidates[0]["content"]["parts"][0]["text"]
    if finish not in (None, "STOP"):
        text += f"\n[WARNING: finishReason={finish}]"
    return text


if __name__ == "__main__":
    system_prompt = load_system_prompt()
    test_message = "What is a SACCO?"

    print(f"Using prompt file: {DEFAULT_PROMPT_FILE.name}")
    print(f"Sending: {test_message}\n")

    reply = call_gemini(test_message, system_prompt)
    print("Model replied:")
    print(reply)
