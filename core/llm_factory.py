from __future__ import annotations

import os
from dotenv import load_dotenv

from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.providers.google import GoogleProvider


# # -- tests with nim models
# def get_model(env_key: str):
#     load_dotenv()

#     primary_name = os.getenv(env_key)
#     nvidia_key = os.getenv("NVIDIA_API_KEY")

#     print(f"DEBUG nvidia model: {primary_name!r}")
#     print(f"DEBUG nvidia key present: {bool(nvidia_key)}")

#     # Initialize the explicit NVIDIA-targeted native client
#     nvidia_client = AsyncOpenAI(
#         api_key=nvidia_key,
#         base_url="https://integrate.api.nvidia.com/v1"
#     )

#     # Wrap it inside the single OpenAIModel expected by your agents
#     return OpenAIChatModel(
#         model_name="nvidia/llama-3.3-nemotron-super-49b-v1.5",
#         provider=OpenAIProvider(openai_client=nvidia_client),
#     )



def get_model(env_key: str):
    load_dotenv()

    primary_name = os.getenv(env_key)
    gemini_name = os.getenv("GEMINI_MODEL")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    print(f"DEBUG primary model: {primary_name!r}")
    print(f"DEBUG gemini model:  {gemini_name!r}")
    print(f"DEBUG openrouter key present: {bool(openrouter_key)}")
    print(f"DEBUG gemini key present:     {bool(gemini_key)}")

    primary_model = OpenRouterModel(
        model_name=os.getenv(env_key),
        provider=OpenRouterProvider(api_key=os.getenv("OPENROUTER_API_KEY")),
    )
    secondary_model = GoogleModel(
        model_name = os.getenv("GEMINI_MODEL"),
        provider=GoogleProvider(api_key=os.getenv("GEMINI_API_KEY"))
    )

    return FallbackModel(primary_model, secondary_model)
