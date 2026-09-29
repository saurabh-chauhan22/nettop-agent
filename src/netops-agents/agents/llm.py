"""One place to configure the Claude model that every agent uses."""
from langchain_anthropic import ChatAnthropic

from utils.config import load_env

load_env()


def claude(effort="low"):
    return ChatAnthropic(
        model="claude-opus-5",
        effort=effort,
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        model_kwargs={"fallbacks": "default"},  # if a safety classifier refuses, the API retries on a fallback model
    )
