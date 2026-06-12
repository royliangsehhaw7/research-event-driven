from __future__ import annotations

import os
from dotenv import load_dotenv


def get_model(env_key: str):
    """Return a pydantic-ai model instance for the given env var key.

    Uses OpenRouter via the OpenAI-compatible provider.
    OPENROUTER_BASE_URL and OPENROUTER_API_KEY must be set in .env.

    Args:
        env_key: environment variable name, e.g. "RESEARCH_MODEL"

    Returns:
        A pydantic-ai OpenAIModel configured for OpenRouter.

    Raises:
        EnvironmentError: if the env var or API key is not set.
    """
    load_dotenv()

    model_string = os.getenv(env_key)
    if not model_string:
        raise EnvironmentError(
            f"Environment variable {env_key!r} is not set. "
            "Check your .env file."
        )

    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL")

    if not api_key:
        raise EnvironmentError(
            "OPENROUTER_API_KEY is not set. Check your .env file."
        )

    # pydantic-ai OpenAI-compatible provider
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.settings import ModelSettings

    provider = OpenAIProvider(
        base_url=base_url,
        api_key=api_key
    )
    settings = ModelSettings(
        temperature=0.25
    )

    return OpenAIChatModel(
        model_name=model_string, 
        settings=settings,
        provider=provider)