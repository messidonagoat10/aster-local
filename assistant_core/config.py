"""Configuration and safe defaults for the local assistant."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


APP_NAME = "Aster"
DEFAULT_MODEL = "qwen3:4b"
DEFAULT_SYSTEM_PROMPT = (
    f"You are {APP_NAME}, a composed, capable, concise local assistant. Be clear, useful, and honest. "
    "Admit uncertainty instead of inventing facts. Keep ordinary replies brief, and give more detail "
    "when asked. Use only the tools explicitly provided for the current turn and follow their "
    "permission and confirmation requirements. Never claim an action happened unless its tool "
    "returned success. Do not claim capabilities or access that are not available in the tools."
)
_ALLOWED_MODEL_TAG = re.compile(r"^qwen3:[a-z0-9][a-z0-9._-]{0,120}$")


def validate_local_ollama_url(value: str) -> str:
    """Accept only plain HTTP URLs whose host is an explicit loopback address."""
    parsed = urlsplit(value)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("Ollama must use plain HTTP on a loopback address.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Ollama URL must not contain credentials, a query, or a fragment.")
    if parsed.path not in ("", "/"):
        raise ValueError("Ollama URL must be an origin without a path.")
    host = parsed.hostname.lower()
    if host != "localhost":
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("Ollama URL must point to this computer (loopback only).")
        except ValueError as exc:
            if str(exc).startswith("Ollama URL"):
                raise
            raise ValueError("Ollama URL must use localhost or a loopback IP address.") from exc
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Ollama port must be between 1 and 65535.")
    return value.rstrip("/")


def validate_model_tag(value: str) -> str:
    """Accept the local Qwen3 model family; reject cloud tags and other model families."""
    model = value.strip().lower()
    if not _ALLOWED_MODEL_TAG.fullmatch(model) or re.search(r"(?:^|[:-])cloud(?:$|[-:])", model):
        raise ValueError(
            "Only installed local qwen3 model tags are allowed; cloud models and other families are disabled."
        )
    return model


def default_data_directory() -> Path:
    """Keep user data out of the source checkout by default."""
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        return Path(root) / "Aster" if root else Path.home() / "AppData" / "Local" / "Aster"
    if sys_platform := os.environ.get("XDG_DATA_HOME"):
        return Path(sys_platform) / "aster"
    if os.uname().sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Aster"
    return Path.home() / ".local" / "share" / "aster"


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings are local environment overrides; the listener is never configurable."""

    port: int
    data_dir: Path
    database_path: Path
    ollama_url: str
    model: str
    system_prompt: str
    max_input_chars: int = 12_000
    max_context_messages: int = 40
    max_context_chars: int = 32_000
    max_memory_items: int = 4

    @classmethod
    def from_environment(cls) -> "Settings":
        port = int(os.environ.get("ASTER_PORT", "8765"))
        if not 1 <= port <= 65535:
            raise ValueError("ASTER_PORT must be between 1 and 65535.")
        data_dir = Path(os.environ.get("ASTER_DATA_DIR", str(default_data_directory()))).expanduser().resolve()
        ollama_url = validate_local_ollama_url(
            os.environ.get("ASTER_OLLAMA_URL", "http://127.0.0.1:11434")
        )
        model = validate_model_tag(os.environ.get("ASTER_MODEL", DEFAULT_MODEL))
        system_prompt = os.environ.get("ASTER_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT).strip()
        if not system_prompt or len(system_prompt) > 8_000:
            raise ValueError("ASTER_SYSTEM_PROMPT must contain 1 to 8000 characters.")
        return cls(
            port=port,
            data_dir=data_dir,
            database_path=data_dir / "aster.sqlite3",
            ollama_url=ollama_url,
            model=model,
            system_prompt=system_prompt,
        )

