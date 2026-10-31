from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOST = "www.yuque.com"


def host() -> str:
    return os.environ.get("YUQUE_HOST") or DEFAULT_HOST


def base_url(host_override: str | None = None) -> str:
    return f"https://{host_override or host()}"


def config_dir() -> Path:
    override = os.environ.get("YUQUE_CONFIG_DIR")
    if override:
        return Path(override)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "yuque-cli"


def session_file() -> Path:
    return config_dir() / "session.json"


def no_color() -> bool:
    return bool(os.environ.get("NO_COLOR"))
