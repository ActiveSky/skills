from __future__ import annotations

import json
import unicodedata
from typing import Any


def _display_width(s: str) -> int:
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _pad(s: str, width: int) -> str:
    return s + " " * (width - _display_width(s))


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [_display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _display_width(cell))
    lines = ["  ".join(_pad(h, widths[i]) for i, h in enumerate(headers)).rstrip()]
    for row in rows:
        lines.append("  ".join(_pad(row[i], widths[i]) for i in range(len(headers))).rstrip())
    return "\n".join(lines)


def _first_line(text: str, limit: int = 60) -> str:
    line = (text or "").splitlines()[0] if text else ""
    return line if len(line) <= limit else line[: limit - 1] + "…"


def render_user(u: dict) -> str:
    fields = [("space", "login"), ("name", "name"), ("id", "id"), ("email", "email"), ("organization_space", "organization_login")]
    return "\n".join(f"{label}: {u[key]}" for label, key in fields if key in u)


def render_repos(repos: list[dict]) -> str:
    rows = [
        [
            str(r.get("name", "")),
            str(r.get("slug", "")),
            str(r.get("items_count", "")),
            "yes" if r.get("public") else "no",
            str(r.get("id", "")),
        ]
        for r in repos
    ]
    return table(["NAME", "SLUG", "DOCS", "PUBLIC", "ID"], rows)


def render_docs(docs: list[dict]) -> str:
    rows = [
        [str(d.get("title", "")), str(d.get("slug", "")), str(d.get("id", ""))]
        for d in docs
    ]
    return table(["TITLE", "SLUG", "ID"], rows)


def _strip_html(html: str) -> str:
    """提取 HTML 中的纯文本。"""
    import re

    text = re.sub(r"<[^>]+>", "", html or "")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return text.strip()


def render_comments(comments: list[dict]) -> str:
    rows = [
        [
            str(c.get("id", "")),
            str((c.get("user") or {}).get("name", "")),
            "划词" if c.get("type") == "WORDING_COMMENT" else "正文",
            _first_line(
                _strip_html(c.get("body", ""))
                if c.get("type") == "WORDING_COMMENT"
                else (c.get("body", "") or "")
            ),
        ]
        for c in comments
    ]
    return table(["ID", "AUTHOR", "TYPE", "BODY"], rows)


def render_repo_overview(data: dict, docs: list[dict] | None = None) -> str:
    """通用渲染：按 key 逐行展示，遇到 dict 取其 name/login/id，其它值直接展示。"""
    _SKIP_KEYS = {"enableCustomBody", "enableCatalog", "order", "layout", "customIndex", "enableUserFeed"}
    lines: list[str] = []
    for key, val in data.items():
        if key in _SKIP_KEYS:
            continue
        if isinstance(val, dict):
            val = val.get("name") or val.get("login") or val.get("id") or json.dumps(val, ensure_ascii=False)
        elif isinstance(val, list):
            if val and isinstance(val[0], dict):
                val = ", ".join(v.get("name") or str(v) for v in val)
            else:
                val = ", ".join(str(v) for v in val)
        elif isinstance(val, bool):
            val = "yes" if val else "no"
        elif val is None:
            val = ""
        lines.append(f"{key}: {val}")
    if docs:
        lines.append("")
        lines.append(f"文档数量: {len(docs)}")
        lines.append(render_docs(docs))
    return "\n".join(lines)


def render_spaces(spaces: list[dict]) -> str:
    rows = [
        [str(s.get("id", "")), str(s.get("name", "")), str(s.get("login", ""))]
        for s in spaces
    ]
    return table(["ID", "NAME", "SPACE"], rows)


def render_toc(nodes: list[dict]) -> str:
    """渲染知识库文档目录树（来自 book.toc）。"""
    uuid_to_node = {n["uuid"]: n for n in nodes}

    ordered_children: dict[str, list[dict]] = {}
    for n in nodes:
        puid = n.get("parent_uuid", "")
        ordered_children.setdefault(puid, []).append(n)

    for puid in ordered_children:
        parent = uuid_to_node.get(puid)
        first_uuid = parent.get("child_uuid", "") if parent else ""
        siblings = []
        seen: set[str] = set()
        cur = first_uuid
        while cur and cur not in seen:
            node = uuid_to_node.get(cur)
            if not node:
                break
            seen.add(cur)
            siblings.append(node)
            cur = node.get("sibling_uuid", "")
        if siblings:
            ordered_children[puid] = siblings

    def _render(
        node: dict,
        children: dict[str, list[dict]],
        lasts: list[bool],
    ) -> list[str]:
        indent_parts = ["│   " if not last else "    " for last in lasts[:-1]]
        indent_prefix = "".join(indent_parts)

        is_last = not lasts or lasts[-1]
        branch = "└── " if is_last else "├── "

        title = node["title"]
        lines: list[str] = []
        if node["type"] == "TITLE":
            node_uuid = node.get("uuid", "")
            lines.append(f"{indent_prefix}{branch}{title}/  ({node_uuid})")
        else:
            node_uuid = node.get("uuid", "")
            lines.append(f"{indent_prefix}{branch}{title}  ({node_uuid})")

        kids = children.get(node["uuid"], [])
        for i, child in enumerate(kids):
            child_lasts = lasts + [i == len(kids) - 1]
            lines.extend(_render(child, children, child_lasts))
        return lines

    roots = [n for n in nodes if not n.get("parent_uuid", "")]
    lines: list[str] = []
    for root in roots:
        title = root["title"]
        root_uuid = root.get("uuid", "")
        if root["type"] == "TITLE":
            line = f"{title}/  ({root_uuid})"
        else:
            line = f"{title}  ({root_uuid})"
        lines.append(line)
        kids = ordered_children.get(root["uuid"], [])
        for j, child in enumerate(kids):
            lines.extend(_render(child, ordered_children, [j == len(kids) - 1]))
    return "\n".join(lines)


def render_doc_authors(data: dict) -> str:
    """渲染文档协作者信息。"""
    rows: list[list[str]] = []
    seen: set[int] = set()
    user = data.get("user") or {}
    if user:
        rows.append([str(user.get("name", "")), str(user.get("login", "")), "author"])
        uid = user.get("id")
        if isinstance(uid, int):
            seen.add(uid)
    last_editor = data.get("last_editor") or {}
    if last_editor:
        leid = last_editor.get("id")
        if isinstance(leid, int) and leid not in seen:
            rows.append([str(last_editor.get("name", "")), str(last_editor.get("login", "")), "last editor"])
            seen.add(leid)
    for c in data.get("contributors") or []:
        cid = c.get("id")
        if not isinstance(cid, int) or cid in seen:
            continue
        rows.append([str(c.get("name", "")), str(c.get("login", "")), "contributor"])
        seen.add(cid)
    if not rows:
        return "(无协作者信息)"
    return table(["NAME", "LOGIN", "ROLE"], rows)


def render_review(
    review: dict,
    doc_url: str,
    approver_names: list[str] | None = None,
    cc_names: list[str] | None = None,
) -> str:
    review_id = review.get("id", "")
    lines = [f"已创建评审（id={review_id}）：{doc_url}"]
    if approver_names:
        lines.append(f"评审人：{', '.join(approver_names)}")
    if cc_names:
        lines.append(f"抄送人：{', '.join(cc_names)}")
    return "\n".join(lines)


_REVIEW_STATUS_MAP = {0: "进行中", 1: "已通过", 2: "未通过", 3: "已取消"}


def render_reviews(reviews: list[dict]) -> str:
    if not reviews:
        return "(无评审)"
    rows = [
        [
            str(r.get("id", "")),
            str(r.get("name", "")),
            _REVIEW_STATUS_MAP.get(r.get("status"), str(r.get("status", ""))),
        ]
        for r in reviews
    ]
    return table(["ID", "NAME", "STATUS"], rows)
