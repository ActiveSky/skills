from __future__ import annotations

from pathlib import Path
from typing import TextIO


class BodyInputError(ValueError):
    """正文输入来源无效（互斥冲突或文件不可读）。"""


def resolve_body(
    body: str | None,
    file: str | None,
    *,
    stdin: TextIO,
    stdin_isatty: bool,
) -> str | None:
    """按 --body > --file(-=stdin) > 管道 stdin 的优先级解析正文。

    在 TTY 下且未给任何来源时返回 None（由调用方决定是否必填）。
    """
    if body is not None and file is not None:
        raise BodyInputError("--body 与 --file 互斥，只能给其一")
    if body is not None:
        return body
    if file is not None:
        if file == "-":
            return stdin.read()
        try:
            return Path(file).read_text(encoding="utf-8")
        except OSError as exc:
            raise BodyInputError(f"无法读取文件 {file}：{exc}") from exc
    if not stdin_isatty:
        return stdin.read()
    return None
