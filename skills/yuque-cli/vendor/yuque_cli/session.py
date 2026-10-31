from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SESSION_COOKIE = "_yuque_session"
CSRF_COOKIE = "yuque_ctoken"


class SessionError(ValueError):
    """会话缺失或无效（未登录、cookie 不含登录态等）。"""


def parse_cookie_string(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


@dataclass(frozen=True)
class Session:
    cookies: dict[str, str]

    @property
    def cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    @property
    def csrf_token(self) -> str | None:
        return self.cookies.get(CSRF_COOKIE)

    def require_session(self) -> None:
        if SESSION_COOKIE not in self.cookies:
            raise SessionError(
                f"cookie 中缺少 {SESSION_COOKIE}（登录态）；请重新运行 yuque auth login"
            )


def from_cookie_string(raw: str) -> Session:
    session = Session(parse_cookie_string(raw))
    session.require_session()
    return session


def save(session: Session, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"cookies": session.cookies}, ensure_ascii=False),
        encoding="utf-8",
    )
    path.chmod(0o600)


def load(path: Path) -> Session:
    if not path.exists():
        raise SessionError("尚未登录；请先运行 yuque auth login")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Session(dict(data["cookies"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise SessionError(f"会话文件损坏：{path}（{exc}）") from exc
