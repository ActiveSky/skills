from __future__ import annotations

import json
import re
from urllib.parse import unquote

# 匹配 window.appData = JSON.parse(decodeURIComponent("...")) 中被 percent-encode 的串。
# 编码后的内容不含裸引号（" 会变成 %22），故 [^"]* 足以圈定整段。
_APP_DATA_RE = re.compile(
    r'window\.appData\s*=\s*JSON\.parse\(\s*decodeURIComponent\(\s*"([^"]*)"\s*\)\s*\)'
)


class AppDataError(ValueError):
    """页面 HTML 中找不到或无法解析 window.appData。"""


def parse_app_data(html: str) -> dict:
    m = _APP_DATA_RE.search(html)
    if not m:
        raise AppDataError("页面中未找到 window.appData（可能未登录或页面结构变化）")
    try:
        return json.loads(unquote(m.group(1)))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppDataError(f"window.appData 解码失败：{exc}") from exc


def repo_id(app_data: dict) -> int:
    try:
        return int(app_data["book"]["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppDataError("appData 中缺少 book.id") from exc


def doc_id(app_data: dict) -> int:
    try:
        return int(app_data["doc"]["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppDataError("appData 中缺少 doc.id（该页面可能不是文档页）") from exc


def group_id(app_data: dict) -> int:
    try:
        return int(app_data["book"]["user_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppDataError("appData 中缺少 book.user_id") from exc
