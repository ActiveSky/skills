"""Markdown to Yuque Lake format converter.

Produces the dual-format output that Yuque's API expects when ``format: "lake"``:
``body`` (lake-content HTML) and ``body_asl`` (Atomic String Language with cards).
"""

from __future__ import annotations

import html
import json
import re
import secrets
import urllib.parse
from typing import Any, Iterator

import mistune
from mistune.core import BlockState
from mistune.plugins import table
from mistune.plugins.task_lists import task_lists_hook

# -- mention support ----------------------------------------------------------

_INLINE_MENTION_RE = re.compile(r'@([\w一-鿿㐀-䶿·]+)')


def _random_id() -> str:
    return "u" + secrets.token_hex(4)


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_mention_html(login: str, name: str, userid: int, span_id: str, base_url: str) -> str:
    return (
        f'<span id="{span_id}" class="ne-mention">'
        f'<a href="{base_url}/{login}">@{name}</a>'
        f'</span>'
    )


def _build_mention_asl(login: str, name: str, userid: int, span_id: str) -> str:
    value_json = json.dumps(
        {"login": login, "name": name, "userid": userid, "workId": "", "id": span_id},
        ensure_ascii=False, separators=(",", ":"),
    )
    value = "data:" + urllib.parse.quote(value_json, safe="")
    return (
        f'<card type="inline" name="mention" '
        f'data-login="{login}" data-name="{name}" data-userid="{userid}" '
        f'value="{value}"></card>'
    )


_MentionMap = dict[str, tuple[str, str, int]]  # name → (login, display_name, userid)


def _render_inline_text(
    text: str,
    mention_map: _MentionMap | None,
    base_url: str,
    *,
    asl: bool,
    next_id,
) -> str:
    """Render inline text, replacing @name patterns with mention cards/spans."""
    if not mention_map:
        sid = next_id()
        return (
            f'<span data-lake-id="{sid}" id="{sid}">{_escape_xml(text)}</span>'
            if asl
            else _escape_xml(text)
        )

    parts = _INLINE_MENTION_RE.split(text)
    if len(parts) == 1:
        sid = next_id()
        return (
            f'<span data-lake-id="{sid}" id="{sid}">{_escape_xml(text)}</span>'
            if asl
            else _escape_xml(text)
        )

    result: list[str] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 0:
            # regular text
            sid = next_id()
            result.append(
                f'<span data-lake-id="{sid}" id="{sid}">{_escape_xml(part)}</span>'
                if asl
                else _escape_xml(part)
            )
        else:
            # @name — replace with mention card/span
            if part in mention_map:
                login, display_name, userid = mention_map[part]
                span_id = next_id()
                if asl:
                    result.append(_build_mention_asl(login, display_name, userid, span_id))
                else:
                    result.append(_build_mention_html(login, display_name, userid, span_id, base_url))
            else:
                sid = next_id()
                result.append(
                    f'<span data-lake-id="{sid}" id="{sid}">@{_escape_xml(part)}</span>'
                    if asl
                    else f"@{_escape_xml(part)}"
                )
    return "".join(result)


def _build_codeblock_card_json(code: str, language: str, block_id: str) -> str:
    data = {
        "search": "",
        "mode": language or "text",
        "code": code,
        "autoWrap": False,
        "lineNumbers": True,
        "heightLimit": True,
        "collapsed": False,
        "hideToolbar": False,
        "name": "",
        "tabSize": None,
        "indentWithTab": False,
        "lightLines": [],
        "foldLines": [],
        "theme": "Github Light",
        "customStyle": [],
        "fontSize": 14,
        "__spacing": "both",
        "id": block_id,
        "margin": {"top": True, "bottom": True},
    }
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    encoded = urllib.parse.quote(json_str, safe="")
    value = f"data:{encoded}"
    return f'<card type="inline" name="codeblock" value="{_escape_xml(value)}"></card>'


# -- fold block parser -------------------------------------------------------

_FOLD_START_PATTERN = r'^ {0,3}:::fold\{title="(?P<fold_title>[^"]*)"\}'
_FOLD_END_RE = re.compile(r'^ {0,3}:::$', re.M)


def _parse_fold(block: Any, m: re.Match[str], state: BlockState) -> int:
    title = m.group("fold_title")
    cursor_start = m.end() + 1
    m2 = _FOLD_END_RE.search(state.src, cursor_start)
    if m2:
        content = state.src[cursor_start:m2.start()]
        end_pos = m2.end()
        # Consume trailing newline after :::
        if end_pos < state.cursor_max and state.src[end_pos] == "\n":
            end_pos += 1
    else:
        content = state.src[cursor_start:]
        end_pos = state.cursor_max

    child = state.child_state(content)
    block.parse(child, block.block_quote_rules)
    state.append_token({
        "type": "fold",
        "attrs": {"title": title},
        "children": child.tokens,
    })
    return end_pos


# -- callout / alert support -------------------------------------------------

_CALLOUT_RE = re.compile(r'^\[!(NOTE|WARNING|DANGER|TIP|IMPORTANT|CAUTION)\]\s*')

_ALERT_TYPE_MAP: dict[str, str] = {
    "NOTE": "info",
    "WARNING": "warning",
    "DANGER": "danger",
    "TIP": "tip",
    "IMPORTANT": "warning",
    "CAUTION": "danger",
}


def _callout_hook(md: Any, state: BlockState) -> Any:
    return _rewrite_callouts(state.tokens)


def _rewrite_callouts(tokens: list[dict[str, Any]]) -> Any:
    for tok in tokens:
        if tok["type"] == "block_quote" and "children" in tok:
            _maybe_convert_callout(tok)
        if "children" in tok:
            _rewrite_callouts(tok["children"])
    return tokens


def _maybe_convert_callout(tok: dict[str, Any]) -> None:
    children: list[dict[str, Any]] = tok.get("children", [])
    if not children:
        return
    first = children[0]
    if first.get("type") != "paragraph":
        return
    # Before _iter_render, the text is in the 'text' field on the paragraph token
    text: str = first.get("text", "")
    if not text:
        return
    m = _CALLOUT_RE.match(text)
    if not m:
        return

    alert_type = m.group(1).upper()
    lake_type = _ALERT_TYPE_MAP.get(alert_type, "info")

    remaining = text[m.end():]
    first["text"] = remaining if remaining else ""

    tok["type"] = "block_alert"
    tok["attrs"] = {"alert_type": lake_type}


# -- task list list-type marker ----------------------------------------------

def _mark_task_lists_hook(md: Any, state: BlockState) -> Any:
    return _mark_task_lists(state.tokens)


def _mark_task_lists(tokens: list[dict[str, Any]]) -> Any:
    for tok in tokens:
        if tok["type"] == "list" and "children" in tok:
            children: list[dict[str, Any]] = tok["children"]
            if children and all(
                c.get("type") == "task_list_item" for c in children
            ):
                tok.setdefault("attrs", {})["list_type"] = "task"
        if "children" in tok:
            _mark_task_lists(tok["children"])
    return tokens


# ---------------------------------------------------------------------------
# HTML body renderer  (lake-content div body)
# ---------------------------------------------------------------------------


class _LakeHTMLRenderer(mistune.HTMLRenderer):
    """Renders Markdown to Lake HTML format used in the ``body`` field."""

    def __init__(
        self, id_gen: Iterator[str],
        mention_map: _MentionMap | None = None,
        base_url: str = "",
    ) -> None:
        super().__init__()
        self._id_gen = id_gen
        self._mention_map = mention_map
        self._base_url = base_url

    def heading(self, text: str, level: int, **attrs: object) -> str:
        bid = next(self._id_gen)
        return f'<h{level} id="{bid}">{text}</h{level}>\n'

    def paragraph(self, text: str) -> str:
        bid = next(self._id_gen)
        return f'<p id="{bid}" class="ne-p">{text}</p>\n'

    def block_code(self, code: str, info: str | None = None) -> str:
        bid = next(self._id_gen)
        lang = info or ""
        escaped = html.escape(code)
        return (
            f'<pre data-language="{lang}" id="{bid}" '
            f'class="ne-codeblock language-{lang}"><code>{escaped}</code></pre>\n'
        )

    def codespan(self, text: str) -> str:
        return f'<code class="ne-code">{_escape_xml(text)}</code>'

    def block_quote(self, text: str) -> str:
        return f'<blockquote class="ne-blockquote">{text}</blockquote>\n'

    def block_alert(self, text: str, alert_type: str = "info") -> str:
        bid = next(self._id_gen)
        return (
            f'<blockquote id="{bid}" class="lake-alert lake-alert-{alert_type}">'
            f'{text}</blockquote>\n'
        )

    def list(self, text: str, ordered: bool, **attrs: object) -> str:
        tag = "ol" if ordered else "ul"
        if attrs.get("list_type") == "task":
            cls = "ne-ul ne-task-list"
        else:
            cls = "ne-ol" if ordered else "ne-ul"
        return f'<{tag} class="{cls}">{text}</{tag}>\n'

    def list_item(self, text: str, **attrs: object) -> str:
        return f"<li>{text}</li>\n"

    def task_list_item(self, text: str, checked: bool = False, **attrs: object) -> str:
        value = "data:true" if checked else "data:false"
        return (
            f'<li class="ne-task-list-item">'
            f'<card type="inline" name="checkbox" value="{value}"></card>'
            f'{text}</li>\n'
        )

    def fold(self, text: str, title: str = "", **attrs: object) -> str:
        bid = next(self._id_gen)
        return (
            f'<details id="{bid}" class="lake-collapse" open="true">'
            f'<summary class="lake-summary"><span class="ne-text">{_escape_xml(title)}</span></summary>'
            f'{text}'
            f'</details>\n'
        )

    def thematic_break(self) -> str:
        return "<hr>\n"

    def image(self, src: str, alt: str = "", title: str | None = None) -> str:
        return f'<img src="{src}" alt="{alt}" class="ne-image" />'

    def text(self, text: str) -> str:
        return _render_inline_text(
            text, self._mention_map, self._base_url,
            asl=False, next_id=lambda: next(self._id_gen),
        )

    def emphasis(self, text: str) -> str:
        return f"<em>{text}</em>"

    def strong(self, text: str) -> str:
        return f"<strong>{text}</strong>"

    def link(self, text: str, url: str, title: str | None = None) -> str:
        title_attr = f' title="{title}"' if title else ""
        return f'<a href="{url}"{title_attr}>{text}</a>'

    def table(self, text: str) -> str:
        bid = next(self._id_gen)
        return f'<table id="{bid}">{text}</table>\n'

    def table_head(self, text: str) -> str:
        return f"<thead><tr>{text}</tr></thead>\n"

    def table_body(self, text: str) -> str:
        return f"<tbody>{text}</tbody>\n"

    def table_row(self, text: str) -> str:
        return f"<tr>{text}</tr>\n"

    def table_cell(self, text: str, align: str | None = None, head: bool = False) -> str:
        tag = "th" if head else "td"
        if align:
            return f'<{tag} align="{align}">{text}</{tag}>'
        return f"<{tag}>{text}</{tag}>"

    def blank_line(self) -> str:
        return ""

    def block_text(self, text: str) -> str:
        return text


# ---------------------------------------------------------------------------
# ASL body renderer  (body_asl with cards)
# ---------------------------------------------------------------------------


class _LakeASLRenderer(mistune.HTMLRenderer):
    """Renders Markdown to Lake ASL format used in the ``body_asl`` field."""

    def __init__(
        self, id_gen: Iterator[str],
        mention_map: _MentionMap | None = None,
        base_url: str = "",
    ) -> None:
        super().__init__()
        self._id_gen = id_gen
        self._mention_map = mention_map
        self._base_url = base_url

    def heading(self, text: str, level: int, **attrs: object) -> str:
        bid = next(self._id_gen)
        return f'<h{level} data-lake-id="{bid}" id="{bid}">{text}</h{level}>'

    def paragraph(self, text: str) -> str:
        bid = next(self._id_gen)
        return f'<p data-lake-id="{bid}" id="{bid}">{text}</p>'

    def block_code(self, code: str, info: str | None = None) -> str:
        bid = next(self._id_gen)
        return _build_codeblock_card_json(code, info or "", bid)

    def codespan(self, text: str) -> str:
        sid = next(self._id_gen)
        return f'<code data-lake-id="{sid}" id="{sid}">{_escape_xml(text)}</code>'

    def text(self, text: str) -> str:
        if not text:
            return ""
        return _render_inline_text(
            text, self._mention_map, self._base_url,
            asl=True, next_id=lambda: next(self._id_gen),
        )

    def emphasis(self, text: str) -> str:
        sid = next(self._id_gen)
        return f'<em data-lake-id="{sid}" id="{sid}">{text}</em>'

    def strong(self, text: str) -> str:
        sid = next(self._id_gen)
        return f'<strong data-lake-id="{sid}" id="{sid}">{text}</strong>'

    def link(self, text: str, url: str, title: str | None = None) -> str:
        sid = next(self._id_gen)
        title_attr = f' title="{title}"' if title else ""
        return f'<a data-lake-id="{sid}" id="{sid}" href="{url}"{title_attr}>{text}</a>'

    def block_quote(self, text: str) -> str:
        bid = next(self._id_gen)
        return f'<blockquote data-lake-id="{bid}" id="{bid}">{text}</blockquote>'

    def block_alert(self, text: str, alert_type: str = "info") -> str:
        bid = next(self._id_gen)
        return (
            f'<blockquote data-lake-id="{bid}" id="{bid}" '
            f'class="lake-alert lake-alert-{alert_type}">{text}</blockquote>\n'
        )

    def list(self, text: str, ordered: bool, **attrs: object) -> str:
        bid = next(self._id_gen)
        tag = "ol" if ordered else "ul"
        if attrs.get("list_type") == "task":
            return f'<{tag} list="{bid}" class="lake-list">{text}</{tag}>\n'
        return f'<{tag} data-lake-id="{bid}" id="{bid}">{text}</{tag}>'

    def list_item(self, text: str, **attrs: object) -> str:
        bid = next(self._id_gen)
        return f'<li data-lake-id="{bid}" id="{bid}">{text}</li>'

    def task_list_item(self, text: str, checked: bool = False, **attrs: object) -> str:
        bid = next(self._id_gen)
        fid = next(self._id_gen)
        value = "data:true" if checked else "data:false"
        return (
            f'<li fid="{fid}" data-lake-id="{bid}" id="{bid}" '
            f'class="lake-list-node lake-list-task">'
            f'<card type="inline" name="checkbox" value="{value}"></card>'
            f'{text}</li>\n'
        )

    def fold(self, text: str, title: str = "", **attrs: object) -> str:
        bid = next(self._id_gen)
        sid = next(self._id_gen)
        span_id = next(self._id_gen)
        return (
            f'<details data-lake-id="{bid}" id="{bid}" open="true" class="lake-collapse">'
            f'<summary data-lake-id="{sid}" id="{sid}" class="lake-summary">'
            f'<span data-lake-id="{span_id}" id="{span_id}">{_escape_xml(title)}</span>'
            f'</summary>'
            f'{text}'
            f'</details>\n'
        )

    def image(self, src: str, alt: str = "", title: str | None = None) -> str:
        bid = next(self._id_gen)
        img_data = {"src": src, "alt": alt or "", "id": bid}
        json_str = json.dumps(img_data, ensure_ascii=False, separators=(",", ":"))
        encoded = urllib.parse.quote(json_str, safe="")
        value = f"data:{encoded}"
        return f'<card type="inline" name="image" value="{_escape_xml(value)}"></card>'

    def thematic_break(self) -> str:
        return "<hr>"

    def table(self, text: str) -> str:
        bid = next(self._id_gen)
        return f'<table data-lake-id="{bid}" id="{bid}">{text}</table>'

    def table_head(self, text: str) -> str:
        return f"<thead><tr>{text}</tr></thead>"

    def table_body(self, text: str) -> str:
        return f"<tbody>{text}</tbody>"

    def table_row(self, text: str) -> str:
        return f"<tr>{text}</tr>"

    def table_cell(self, text: str, align: str | None = None, head: bool = False) -> str:
        tag = "th" if head else "td"
        sid = next(self._id_gen)
        if align:
            return f'<{tag} data-lake-id="{sid}" id="{sid}" align="{align}">{text}</{tag}>'
        return f'<{tag} data-lake-id="{sid}" id="{sid}">{text}</{tag}>'

    def blank_line(self) -> str:
        return ""

    def block_text(self, text: str) -> str:
        return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _needs_lake_conversion(body: str) -> bool:
    """Return True when the Markdown body contains elements that need Lake conversion."""
    if "```" in body:
        return True
    if ":::fold" in body:
        return True
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.count("|") >= 2:
            return True
        if re.match(r'^[-*+]\s+\[[ xX]\]', stripped):
            return True
        if re.match(r'^>\s+\[!(NOTE|WARNING|DANGER|TIP|IMPORTANT|CAUTION)\]', stripped):
            return True
    return False


def markdown_to_lake(
    md_text: str,
    mention_map: _MentionMap | None = None,
    base_url: str = "",
) -> tuple[str, str]:
    """Convert Markdown to Yuque Lake format.

    Args:
        md_text: Markdown source text.
        mention_map: Optional dict mapping ``@name`` → ``(login, display_name, userid)``.
        base_url: Base URL used in mention ``<a href>`` links (HTML format only).

    Returns:
        ``(body_html, body_asl)`` tuple suitable for ``format: "lake"`` API payloads.
    """
    if not md_text or not md_text.strip():
        return "", ""

    _inf = iter(int, 1)
    html_gen: Iterator[str] = (_random_id() for _ in _inf)
    asl_gen: Iterator[str] = (_random_id() for _ in _inf)

    html_md = mistune.create_markdown(
        renderer=_LakeHTMLRenderer(html_gen, mention_map=mention_map, base_url=base_url),
        plugins=[table.table],
    )
    asl_md = mistune.create_markdown(
        renderer=_LakeASLRenderer(asl_gen, mention_map=mention_map, base_url=base_url),
        plugins=[table.table],
    )

    # Register fold block parser on both instances
    html_md.block.register("fold", _FOLD_START_PATTERN, _parse_fold)
    asl_md.block.register("fold", _FOLD_START_PATTERN, _parse_fold)

    # Register hooks: task lists → mark task lists → callout detection
    for md_inst in (html_md, asl_md):
        md_inst.before_render_hooks.append(task_lists_hook)
        md_inst.before_render_hooks.append(_mark_task_lists_hook)
        md_inst.before_render_hooks.append(_callout_hook)

    inner_html = html_md(md_text)
    inner_asl = asl_md(md_text)

    body_html = f'<div class="lake-content" typography="classic">{inner_html}</div>'
    body_asl = (
        '<!doctype lake>'
        '<meta name="doc-version" content="1" />'
        '<meta name="viewport" content="fixed" />'
        '<meta name="typography" content="classic" />'
        f'{inner_asl}'
        '<!hash>'
    )

    return body_html, body_asl


# ---------------------------------------------------------------------------
# 反向转换：语雀原生 Markdown → 标准 Markdown
# ---------------------------------------------------------------------------

_YUQUE_CALLOUT_RE = re.compile(
    r"^:::(info|warning|danger|tip|success)\n(.*?)^:::$",
    re.DOTALL | re.MULTILINE,
)

_CALLOUT_TYPE_TO_GFM: dict[str, str] = {
    "info": "NOTE",
    "warning": "WARNING",
    "danger": "DANGER",
    "tip": "TIP",
    "success": "TIP",
}

_YUQUE_FOLD_RE = re.compile(
    r"<details class=\"lake-collapse\"><summary[^>]*>(.*?)</summary>(.*?)</details>",
    re.DOTALL,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_plain(text: str) -> str:
    """Strip HTML tags and convert basic elements to markdown equivalents."""
    # Preserve content of specific tags by converting to markdown
    text = re.sub(r"</?span[^>]*>", "", text)
    text = re.sub(r"<p[^>]*>", "", text)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<li[^>]*>", "- ", text)
    text = re.sub(r"</li>", "\n", text)
    text = re.sub(r"</?(?:ul|ol)[^>]*>", "", text)
    text = re.sub(r"<strong[^>]*>", "**", text)
    text = re.sub(r"</strong>", "**", text)
    text = re.sub(r"<em[^>]*>", "*", text)
    text = re.sub(r"</em>", "*", text)
    text = re.sub(r"<code[^>]*>", "`", text)
    text = re.sub(r"</code>", "`", text)
    # Strip any remaining HTML tags
    text = _HTML_TAG_RE.sub("", text)
    return text.strip()


def _convert_callout_block(m: re.Match[str]) -> str:
    yuque_type = m.group(1)
    gfm_type = _CALLOUT_TYPE_TO_GFM.get(yuque_type, "NOTE")
    content = m.group(2).rstrip("\n")
    lines = content.split("\n")
    converted = "\n".join(f"> {line}" if line.strip() else ">" for line in lines)
    return f"> [!{gfm_type}]\n{converted}\n"


def _convert_fold_block(m: re.Match[str]) -> str:
    title_html = m.group(1)
    body_html = m.group(2)

    title = _html_to_plain(title_html).strip()
    body = _html_to_plain(body_html).strip()

    # Indent body content for readability inside the fold
    return f':::fold{{title="{title}"}}\n{body}\n:::\n'


def normalize_yuque_markdown(md_text: str) -> str:
    """将语雀原生 Markdown 转为标准格式。

    转换规则：
    - ``:::info`` / ``:::warning`` / ``:::danger`` / ``:::tip`` → ``> [!TYPE]``
    - ``<details class="lake-collapse">`` HTML → ``:::fold{{title="..."}}``
    """
    if not md_text:
        return md_text

    md_text = _YUQUE_CALLOUT_RE.sub(_convert_callout_block, md_text)
    md_text = _YUQUE_FOLD_RE.sub(_convert_fold_block, md_text)
    return md_text
