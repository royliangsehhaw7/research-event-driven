# main.py
"""
`argparse` is the standard library module in Python used to handle Command Line Arguments. 
It allows you to create user-friendly command-line interfaces for your scripts
"""


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
    """
    Load .env and check all required keys are present and non-empty.

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
        action="store_true",        # convert existance of --validate-env as TRUE for checking below
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