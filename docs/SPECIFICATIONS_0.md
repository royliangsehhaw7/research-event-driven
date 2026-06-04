# Stage 0 — Repo Scaffold & Environment Setup
## Implementation Specification

**Goal:** A clean, runnable repo with all dependencies installed, environment
variables validated at startup, and a passing smoke test that confirms the
Python environment is healthy before any code is written.

**Ends with:** `python main.py --validate-env` prints all keys present/missing.
`pytest tests/test_env.py` passes. The project folder exists and imports cleanly.

---

## What This Stage Does and Why

Stage 0 has no agents, no searches, no LLM calls. Its only job is to make
Stage 1 frictionless. Every real problem that surfaces here — wrong Python
version, missing package, bad `.env` path, import collision — would otherwise
surface mid-pipeline and look like a code bug. Surface them now.

---

## 0.1 Prerequisites

Before creating any file, confirm:

```bash
python --version   # must be 3.11 or 3.12
pip --version      # must be pip 23+
```

Python 3.10 is not acceptable — `X | Y` union syntax in type hints requires 3.10+,
but `match` statements and `tomllib` (used by pydantic-ai internals) require 3.11.
Use 3.11 or 3.12 to avoid subtle compatibility issues.

If using a virtual environment (recommended):

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows
```

---

## 0.2 Folder Structure to Create

Create this exact layout. Every folder and file listed here must exist before
Stage 1 begins. Empty files are fine for now — they establish the import
namespace.

```
university_research/
│
├── skills/
│   ├── accommodation/
│   ├── alternatives/
│   ├── background/
│   ├── career/
│   ├── conversation/
│   ├── employability/
│   ├── forum/
│   ├── news/
│   ├── program/
│   ├── rankings/
│   └── scoring/
│
├── core/
│   ├── __init__.py
│   ├── message_hub.py          (empty for now)
│   ├── blackboard.py           (empty for now)
│   ├── deps.py                 (empty for now)
│   ├── llm_factory.py          (empty for now)
│   └── skill_loader.py         (empty for now)
│
├── schemas/
│   ├── __init__.py
│   ├── messages/
│   │   └── __init__.py
│   └── outputs/
│       └── __init__.py
│
├── agents/
│   └── __init__.py
│
├── tools/
│   └── __init__.py
│
├── report/
│   ├── __init__.py
│   └── templates/
│
├── services/
│   └── __init__.py
│
├── ui/
│   └── __init__.py
│
├── tests/
│   └── __init__.py
│
├── main.py                     (stub)
├── .env                        (your keys — never commit)
├── .env.example                (committed — safe template)
├── .gitignore
└── requirements.txt
```

**Why `__init__.py` everywhere:** pydantic-ai and pytest both rely on proper
Python packages for import resolution. Missing `__init__.py` files cause
confusing `ModuleNotFoundError` that look like code errors but are actually
packaging errors. Add them to every folder that will contain Python files.

**Why `skills/` subfolders now:** `skill_loader.py` (Stage 1a) iterates
`sorted(skills_dir.iterdir())` and looks for `SKILL.md` inside each subfolder.
If the folders don't exist, the loader returns an empty dict and no warning —
it silently does nothing. Creating them now means Stage 1a tests can confirm
the loader finds exactly the right number of folders.

---

## 0.3 Create `.gitignore`

```gitignore
# Environment
.env
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/

# Outputs — generated per run, not committed
outputs/
*.md.generated

# OS
.DS_Store
Thumbs.db
```

The `.env` line is critical. One accidental commit of API keys to a public repo
will trigger automated key-scanning bots within minutes.

---

## 0.4 Create `.env.example`

This file is committed to the repo. It shows collaborators what keys are needed
without exposing actual values.

```bash
# .env.example — copy to .env and fill in your keys

# Search
TAVILY_API_KEY=tvly-...

# Reddit API — create at https://www.reddit.com/prefs/apps (script type)
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=university_research_bot/1.0

# LLM via OpenRouter — https://openrouter.ai
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Model selection — use any OpenRouter model string
RESEARCH_MODEL=openrouter/google/gemini-2.5-pro
SCORING_MODEL=openrouter/google/gemini-2.5-pro
CONVERSATION_MODEL=openrouter/google/gemini-2.5-flash
```

**`REDDIT_USER_AGENT`:** Reddit's API requires a descriptive user agent string.
The format is `<app_name>/<version> by <reddit_username>`. Without it, PRAW
will raise a `prawcore.exceptions.ResponseException`. Include it in `.env.example`
so it is never forgotten.

---

## 0.5 Create `requirements.txt`

```
# requirements.txt
pydantic-ai[openai]       # OpenAI-compatible provider support (needed for OpenRouter)
pydantic>=2.0
chainlit
pyyaml                    # SKILL.md frontmatter parsing
tavily-python             # Tavily search client
praw                      # Reddit API client (ForumAgent)
duckduckgo-search         # NewsAgent fallback — no key needed
jinja2                    # report generation
python-dotenv
pytest                    # testing
pytest-asyncio            # async test support
```

**Why `pydantic-ai[openai]`:** OpenRouter exposes an OpenAI-compatible API.
pydantic-ai needs its OpenAI provider extras to communicate with it. Without
the `[openai]` extra, `from pydantic_ai.providers.openai import OpenAIProvider`
raises an `ImportError` at runtime.

**Why `pytest-asyncio`:** The hub, agents, and handlers are all async. Without
`pytest-asyncio`, any `async def test_...` function is silently skipped by
pytest rather than run — a subtle failure mode where your tests "pass" but
never actually execute.

Install:

```bash
pip install -r requirements.txt
```

Confirm no errors. If you see version conflicts, pin the conflicting packages.
Do not proceed to Stage 1 with unresolved install errors.

---

## 0.6 Create `.env`

Copy `.env.example` to `.env` and fill in your real keys:

```bash
cp .env.example .env
```

Then edit `.env` with actual values. All keys must be present for the validator
to pass, even if some agents won't be used until later stages.

---

## 0.7 Create `main.py` — Environment Validator Stub

This is not the final `main.py`. It is a minimal stub that does one thing:
loads `.env` and reports which required keys are present and which are missing.

```python
# main.py
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

REQUIRED_KEYS = [
    "TAVILY_API_KEY",
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "REDDIT_USER_AGENT",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "RESEARCH_MODEL",
    "SCORING_MODEL",
    "CONVERSATION_MODEL",
]


def validate_env() -> bool:
    """Load .env and check all required keys are present and non-empty.

    Returns True if all keys present. Prints a status line for each key.
    Does not print key values — only presence/absence.
    """
    load_dotenv()
    all_present = True
    for key in REQUIRED_KEYS:
        value = os.getenv(key)
        if value:
            print(f"  ✓  {key}")
        else:
            print(f"  ✗  {key}  ← MISSING")
            all_present = False
    return all_present


def main() -> None:
    parser = argparse.ArgumentParser(description="University Research Assistant")
    parser.add_argument(
        "--validate-env",
        action="store_true",
        help="Check all required environment variables are set",
    )
    args = parser.parse_args()

    if args.validate_env:
        print("\nEnvironment validation:")
        ok = validate_env()
        if ok:
            print("\n  All required keys present. Environment is ready.\n")
            sys.exit(0)
        else:
            print("\n  One or more keys missing. Check your .env file.\n")
            sys.exit(1)

    print("No command given. Use --validate-env to check environment.")


if __name__ == "__main__":
    main()
```

**Why exit codes matter:** `sys.exit(1)` on failure means CI pipelines and
shell scripts can detect the missing-key condition with `$?`. `sys.exit(0)`
on success is equally important — without it, some shells treat any non-zero
exit as a problem even when the command succeeded.

**Why not print key values:** printing actual key values to stdout is a
security risk in shared environments and CI logs. Presence/absence is all
the validator needs to convey.

---

## 0.8 Create `tests/test_env.py`

```python
# tests/test_env.py
"""
Stage 0 smoke test.

Confirms:
1. The .env file exists and can be loaded.
2. All required keys are present and non-empty.
3. The project package structure imports cleanly.

This test does NOT make any network calls.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Same list as main.py — kept in sync manually (no shared import yet)
REQUIRED_KEYS = [
    "TAVILY_API_KEY",
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "REDDIT_USER_AGENT",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "RESEARCH_MODEL",
    "SCORING_MODEL",
    "CONVERSATION_MODEL",
]


def test_dotenv_file_exists() -> None:
    """The .env file must exist at the project root."""
    env_path = Path(".env")
    assert env_path.exists(), (
        ".env file not found. Copy .env.example to .env and fill in your keys."
    )


def test_all_required_keys_present() -> None:
    """Every required env var must be set and non-empty after loading .env."""
    load_dotenv()
    missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    assert not missing, (
        f"Missing required environment variables: {missing}\n"
        "Check your .env file."
    )


def test_skills_folders_exist() -> None:
    """All 11 skills subfolders must exist under skills/."""
    expected = {
        "accommodation", "alternatives", "background", "career",
        "conversation", "employability", "forum", "news",
        "program", "rankings", "scoring",
    }
    skills_dir = Path("skills")
    assert skills_dir.is_dir(), "skills/ directory not found"
    found = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    missing = expected - found
    assert not missing, f"Missing skills subfolders: {missing}"


def test_core_package_importable() -> None:
    """core/ package must be importable (even if modules are empty stubs)."""
    import core  # noqa: F401


def test_schemas_package_importable() -> None:
    """schemas/ package must be importable."""
    import schemas  # noqa: F401
    import schemas.messages  # noqa: F401
    import schemas.outputs  # noqa: F401


def test_openrouter_base_url_format() -> None:
    """OPENROUTER_BASE_URL must point to the OpenRouter API endpoint."""
    load_dotenv()
    url = os.getenv("OPENROUTER_BASE_URL", "")
    assert "openrouter.ai" in url, (
        f"OPENROUTER_BASE_URL looks wrong: {url!r}\n"
        "Expected: https://openrouter.ai/api/v1"
    )
```

**Why test the URL format:** a common mistake is setting `OPENROUTER_BASE_URL`
to the dashboard URL instead of the API endpoint. This catches it immediately
rather than at the first LLM call in Stage 1c.

---

## 0.9 Run the Validation

```bash
# Validate environment variables
python main.py --validate-env

# Run the smoke tests
pytest tests/test_env.py -v
```

Expected output from `pytest`:

```
tests/test_env.py::test_dotenv_file_exists PASSED
tests/test_env.py::test_all_required_keys_present PASSED
tests/test_env.py::test_skills_folders_exist PASSED
tests/test_env.py::test_core_package_importable PASSED
tests/test_env.py::test_schemas_package_importable PASSED
tests/test_env.py::test_openrouter_base_url_format PASSED

6 passed in 0.XXs
```

All 6 must pass before moving to Stage 1a. A failing test here means the
environment is broken, not the code — fix the environment first.

---

## 0.10 Common Failure Modes at This Stage

**`ModuleNotFoundError: No module named 'core'`**
Cause: running `pytest` from the wrong directory, or missing `__init__.py`.
Fix: run from the `university_research/` root. Confirm `core/__init__.py` exists.

**`test_all_required_keys_present FAILED — Missing: ['TAVILY_API_KEY', ...]`**
Cause: `.env` file not found, or keys not filled in.
Fix: confirm `.env` exists at the project root (same level as `main.py`).
`load_dotenv()` looks in the current working directory by default.

**`test_skills_folders_exist FAILED`**
Cause: skills subfolders not created yet, or created with wrong names.
Fix: names are lowercase, no underscores — `forum` not `forum_agent`.

**`ImportError: pydantic_ai.providers.openai` not found**
Cause: installed `pydantic-ai` without the `[openai]` extra.
Fix: `pip install pydantic-ai[openai]`.

---

## Stage 0 Completion Checklist

Before marking Stage 0 done and moving to Stage 1a, confirm every item:

- [ ] Python 3.11 or 3.12 in use
- [ ] `requirements.txt` installed with no errors
- [ ] `.env` file created with all 9 required keys filled in
- [ ] `.env` listed in `.gitignore`
- [ ] All 11 `skills/` subfolders created
- [ ] `__init__.py` present in every package folder
- [ ] `python main.py --validate-env` exits 0 with all ✓
- [ ] `pytest tests/test_env.py -v` — 6 passed, 0 failed