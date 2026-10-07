"""
Week 2 — Baseline Gemini interaction.

Loads the system prompt from prompts/v1.0.md and provides a basic
Gemini text-generation function.

This module does not declare or execute SACCO tools.
Tool orchestration belongs in agent_tools.py.
"""

import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


# ---------------------------------------------------------------------------
# Project paths and configuration
# ---------------------------------------------------------------------------

SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent

PROMPTS_DIR = REPO_ROOT / "prompts"
DEFAULT_PROMPT_VERSION = "v1.0"
DEFAULT_PROMPT_FILE = PROMPTS_DIR / f"{DEFAULT_PROMPT_VERSION}.md"
DEFAULT_TEST_MESSAGE = "What is a SACCO?"

DEFAULT_MODEL = "gemini-3.6-flash"

# Used when a 429 does not include a usable retryDelay.
DEFAULT_429_WAIT_SECONDS = 60

# If Google asks us to wait longer than this, fail instead of hanging.
MAX_RETRY_WAIT_SECONDS = 120

RETRYABLE_STATUS_CODES = (429, 500, 503)

load_dotenv(REPO_ROOT / ".env")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def load_system_prompt(prompt_path: Path = DEFAULT_PROMPT_FILE) -> str:
    """
    Load the versioned system prompt.

    Includes every Markdown section beginning with '## ' except:
      - 1. Purpose
      - 10. Version Information

    These sections are notes for the team, not model instructions.
    """

    prompt_path = Path(prompt_path)

    if not prompt_path.is_file():
        raise FileNotFoundError(
            f"System prompt file not found: {prompt_path}\n"
            f"Check that the file exists in {PROMPTS_DIR}."
        )

    text = prompt_path.read_text(encoding="utf-8").strip()

    if not text:
        raise ValueError(f"System prompt file is empty: {prompt_path}")

    # Drop the title block before the first '## '.
    sections = re.split(r"(?m)^## ", text)[1:]

    skip = ("1. Purpose", "10. Version Information")

    kept = [s for s in sections if not s.startswith(skip)]

    if not kept:
        raise ValueError(
            f"No usable prompt sections found in {prompt_path}. "
            "Check the Markdown headings."
        )

    return "\n\n".join("## " + s.strip() for s in kept)


# ---------------------------------------------------------------------------
# Error-response helpers
# ---------------------------------------------------------------------------

def _error_body(response: requests.Response) -> dict:
    """Return the parsed 'error' object from a Google API error, or {}."""
    try:
        body = response.json()
    except ValueError:
        return {}

    error = body.get("error") if isinstance(body, dict) else None
    return error if isinstance(error, dict) else {}


def _error_details(response: requests.Response) -> list[dict]:
    """Return the structured 'details' entries of a Google API error."""
    details = _error_body(response).get("details") or []
    return [d for d in details if isinstance(d, dict)]


def _is_daily_quota_error(response: requests.Response) -> bool:
    """
    Decide whether a 429 is a daily quota limit (retrying cannot help).

    Primary check: the structured QuotaFailure detail. Each violation has a
    'quotaId' such as 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'.

    Fallback: if Google returns no structured details, search the raw text
    so we still fail safe instead of burning requests on a hopeless retry.
    """

    violations = []
    for detail in _error_details(response):
        if str(detail.get("@type", "")).endswith("QuotaFailure"):
            violations.extend(detail.get("violations") or [])

    if violations:
        return any(
            "perday" in str(v.get("quotaId", "")).lower()
            or "perday" in str(v.get("quotaMetric", "")).lower()
            for v in violations
            if isinstance(v, dict)
        )

    return "perday" in response.text.lower()


def _parse_retry_delay(response: requests.Response) -> float | None:
    """
    Read Google's suggested wait from the RetryInfo detail.

    The value is a protobuf duration string such as "34s" or "34.5s".
    Returns seconds, or None if it is missing or malformed.
    """

    for detail in _error_details(response):
        if str(detail.get("@type", "")).endswith("RetryInfo"):
            match = re.fullmatch(
                r"\s*(\d+(?:\.\d+)?)s\s*",
                str(detail.get("retryDelay", "")),
            )
            if match:
                return float(match.group(1))

    return None


def _wait_before_retry(response: requests.Response, attempt: int) -> float:
    """Work out how long to sleep before the next attempt."""

    if response.status_code != 429:
        return 2 ** attempt  # short backoff for 500/503

    delay = _parse_retry_delay(response)

    if delay is None:
        return DEFAULT_429_WAIT_SECONDS

    if delay > MAX_RETRY_WAIT_SECONDS:
        raise RuntimeError(
            f"Gemini asked us to wait {delay:.0f}s, which exceeds the "
            f"{MAX_RETRY_WAIT_SECONDS}s limit. Try again later."
        )

    return delay + 1  # small buffer so we do not land right on the edge


# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------

def call_gemini(
    user_message: str,
    system_prompt: str,
    retries: int = 1,
) -> str:
    """
    Send a basic text-generation request to Gemini.

    This function is intended for the baseline chat demonstration.
    It does not execute function calls or access SACCO tools.
    """

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check your repository .env file."
        )

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_message}],
            }
        ],
        "generationConfig": {"temperature": 0.2},
    }

    headers = {"x-goog-api-key": api_key}

    response = None

    for attempt in range(retries + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            if attempt >= retries:
                raise RuntimeError(
                    f"Could not reach the Gemini API: {exc}"
                ) from exc

            time.sleep(2 ** attempt)
            continue

        if response.ok:
            break

        # A daily quota limit will not be fixed by retrying.
        if response.status_code == 429 and _is_daily_quota_error(response):
            raise RuntimeError(
                f"Gemini daily quota exhausted: {response.text[:600]}"
            )

        if (
            response.status_code in RETRYABLE_STATUS_CODES
            and attempt < retries
        ):
            time.sleep(_wait_before_retry(response, attempt))
            continue

        raise RuntimeError(
            f"Gemini API error {response.status_code}: "
            f"{response.text[:1500]}"
        )

    if response is None or not response.ok:
        raise RuntimeError("Gemini request failed without a usable response.")

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("Gemini returned invalid JSON.") from exc

    candidates = data.get("candidates") or []

    if not candidates:
        raise RuntimeError(
            "Gemini returned no candidates. "
            f"Prompt feedback: {data.get('promptFeedback')}"
        )

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []

    text = "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict)
        and "text" in part
        and not part.get("thought")
    ).strip()

    finish_reason = candidate.get("finishReason")

    if not text:
        raise RuntimeError(
            "Gemini returned no usable text. "
            f"finishReason={finish_reason}, parts={len(parts)}"
        )

    if finish_reason not in (None, "STOP"):
        text += f"\n[WARNING: finishReason={finish_reason}, parts={len(parts)}]"

    return text


# ---------------------------------------------------------------------------
# Standalone baseline demonstration
# ---------------------------------------------------------------------------

def prompt_path_for(version: str) -> Path:
    """Turn 'v1.1' (or 'v1.1.md') into prompts/v1.1.md."""
    version = version.removesuffix(".md")
    return PROMPTS_DIR / f"{version}.md"


if __name__ == "__main__":
    # Usage (from the repo root):
    #   python src/baseline_chat.py                      -> v1.0, default question
    #   python src/baseline_chat.py v1.1                 -> v1.1, default question
    #   python src/baseline_chat.py v1.1 "Your question" -> v1.1, custom question
    version = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT_VERSION
    test_message = (
        " ".join(sys.argv[2:]) if len(sys.argv) > 2 else DEFAULT_TEST_MESSAGE
    )

    prompt_path = prompt_path_for(version)
    system_prompt = load_system_prompt(prompt_path)

    print(f"Using prompt file: {prompt_path}")
    print(f"Sending: {test_message}\n")

    reply = call_gemini(test_message, system_prompt)

    print("Model replied:")
    print(reply)