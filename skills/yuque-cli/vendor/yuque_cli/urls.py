from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


class UrlParseError(ValueError):
    """输入无法解析成知识库（repo）或文档（doc）地址。"""


@dataclass(frozen=True)
class RepoRef:
    space: str
    repo: str
    host: str | None = None


@dataclass(frozen=True)
class DocRef:
    space: str
    repo: str
    slug: str
    host: str | None = None

    @property
    def repo_ref(self) -> RepoRef:
        return RepoRef(self.space, self.repo, host=self.host)


def _segments(raw: str) -> list[str]:
    s = raw.strip()
    if not s:
        return []
    s = s.split("#", 1)[0].split("?", 1)[0]
    if "://" in s:
        path = urlsplit(s).path
    else:
        # 无 scheme 时可能是 "host/seg/..." 也可能是纯 "seg/seg..."。
        # 语雀 space 不含点，故首段含 "." 即视为 host 并剥掉。
        parts = s.split("/")
        if "." in parts[0]:
            parts = parts[1:]
        path = "/".join(parts)
    return [seg for seg in path.split("/") if seg]


def extract_host(raw: str) -> str | None:
    """从完整 URL 或带 host 的路径中提取 host；无法识别时返回 None。"""
    s = raw.strip()
    if not s:
        return None
    if "://" in s:
        return urlsplit(s).hostname
    # 无 scheme：首段含 "." 即视为 host
    parts = s.split("/")
    if parts and "." in parts[0]:
        return parts[0]
    return None


def parse_doc_ref(raw: str) -> DocRef:
    segs = _segments(raw)
    if len(segs) < 3:
        raise UrlParseError(
            f"文档地址应形如 {{space}}/{{repo}}/{{slug}}（三段），得到：{raw!r}"
        )
    space, repo, slug = segs[:3]
    return DocRef(space=space, repo=repo, slug=slug, host=extract_host(raw))


def parse_repo_ref(raw: str) -> RepoRef:
    segs = _segments(raw)
    if len(segs) < 2:
        raise UrlParseError(
            f"知识库地址应形如 {{space}}/{{repo}}（两段），得到：{raw!r}"
        )
    if len(segs) > 3:
        raise UrlParseError(f"地址段数过多，无法识别为知识库：{raw!r}")
    return RepoRef(space=segs[0], repo=segs[1], host=extract_host(raw))
