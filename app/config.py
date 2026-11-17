import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    openai_api_key: str
    anthropic_api_key: str
    openai_model: str
    anthropic_model: str
    openai_base_url: str
    anthropic_base_url: str


def load_settings() -> Settings:
    load_dotenv()

    values = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", ""),
        "ANTHROPIC_MODEL": os.getenv("ANTHROPIC_MODEL", ""),
        "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", ""),
        "ANTHROPIC_BASE_URL": os.getenv("ANTHROPIC_BASE_URL", ""),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Не заполнены переменные окружения: " + ", ".join(missing)
        )

    return Settings(
        openai_api_key=values["OPENAI_API_KEY"],
        anthropic_api_key=values["ANTHROPIC_API_KEY"],
        openai_model=values["OPENAI_MODEL"],
        anthropic_model=values["ANTHROPIC_MODEL"],
        openai_base_url=values["OPENAI_BASE_URL"],
        anthropic_base_url=values["ANTHROPIC_BASE_URL"],
    )