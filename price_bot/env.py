# env.py

import os
from dotenv import load_dotenv


def load_environment() -> None:
    """
    Load environment variables from the .env file.
    Call this once at the start of main.py.
    """
    load_dotenv()


def get_env(key: str, default: str | None = None) -> str:
    """
    Get an environment variable.

    If no default is provided and the variable is missing,
    raise an error so the app fails clearly.
    """
    value = os.getenv(key, default)

    if value is None:
        raise ValueError(f"Missing required environment variable: {key}")

    return value