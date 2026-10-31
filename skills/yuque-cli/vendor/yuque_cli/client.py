from __future__ import annotations

import json
import pathlib
import re
import secrets
import urllib.parse
from typing import Any

import httpx

from . import appdata
from .errors import ApiError, AuthExpired
from .lake_converter import _needs_lake_conversion, markdown_to_lake, normalize_yuque_markdown
from .session import Session

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


def _random_id() -> str:
    return "u" + secrets.token_hex(4)


def _random_hash() -> str:
    return secrets.token_hex(32)


_INLINE_MENTION_RE = re.compile(r'@([\w一-鿿㐀-䶿·]+)')


def _parse_inline_mentions(text: str) -> list[str]:
    """从正文提取所有 @name 模式的用户名（去重，保持出现顺序）。"""
    seen: set[str] = set()
    result: list[str] = []
    for m in _INLINE_MENTION_RE.finditer(text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _build_mention_card(login: str, name: str, userid: int, span_id: str, base_url: str) -> tuple[str, str]:
    """构建 Lake mention 卡片，返回 (body_asl_card, body_html_span)。"""
    value_json = json.dumps(
        {"login": login, "name": name, "userid": userid, "workId": "", "id": span_id},
        ensure_ascii=False, separators=(",", ":"),
    )
    value = "data:" + urllib.parse.quote(value_json, safe="")
    card = (
        f'<card type="inline" name="mention" '
        f'data-login="{login}" data-name="{name}" data-userid="{userid}" '
        f'value="{value}"></card>'
    )
    span = f'<span id="{span_id}" class="ne-mention"><a href="{base_url}/{login}">@{name}</a></span>'
    return card, span


def _build_body_asl(text: str) -> tuple[str, str, str]:
    pid = _random_id()
    sid = _random_id()
    h = _random_hash()
    body_asl = (
        '<!doctype lake>'
        '<meta name="doc-version" content="1" />'
        '<meta name="viewport" content="adapt" />'
        f'<p data-lake-id="{pid}" id="{pid}">'
        f'<span data-lake-id="{sid}" id="{sid}">{text}</span>'
        f'</p>'
        f'<!{h}>'
    )
    return body_asl, pid, sid


def _build_body(text: str, pid: str, sid: str) -> str:
    return (
        '<div class="lake-content" typography="traditional">'
        f'<p id="{pid}" class="ne-p">'
        f'<span class="ne-text">{text}</span>'
        f'</p>'
        f'</div>'
    )


def _build_doc_lake_body(
    text: str, mention_map: dict[str, tuple[str, str, int]], base_url: str
) -> tuple[str, str]:
    """构建带内联 mention 的文档 Lake body，返回 (body_asl, body_html)。"""
    parts = _INLINE_MENTION_RE.split(text)
    pid = _random_id()
    h = _random_hash()

    body_asl = (
        '<!doctype lake>'
        '<meta name="doc-version" content="1" />'
        '<meta name="viewport" content="adapt" />'
        f'<p data-lake-id="{pid}" id="{pid}">'
    )
    body_html = (
        '<div class="lake-content" typography="traditional">'
        f'<p id="{pid}" class="ne-p">'
    )

    for i, part in enumerate(parts):
        if i % 2 == 0:
            # 偶数索引：普通文本
            if part:
                sid = _random_id()
                body_asl += f'<span data-lake-id="{sid}" id="{sid}">{_escape_xml(part)}</span>'
                body_html += f'<span class="ne-text">{_escape_xml(part)}</span>'
        else:
            # 奇数索引：@name 后面的名字
            if part in mention_map:
                login, name, userid = mention_map[part]
                span_id = _random_id()
                card, span = _build_mention_card(login, name, userid, span_id, base_url)
                body_asl += card
                body_html += span
            else:
                # 未找到用户，保留原文
                sid = _random_id()
                fallback = f"@{part}"
                body_asl += f'<span data-lake-id="{sid}" id="{sid}">{_escape_xml(fallback)}</span>'
                body_html += f'<span class="ne-text">{_escape_xml(fallback)}</span>'

    body_asl += f'</p><!{h}>'
    body_html += '</p></div>'
    return body_asl, body_html


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_comment_with_mentions(
    text: str, mentions: list[tuple[str, str, int]], base_url: str
) -> tuple[str, str]:
    """构建带 @ 提及的 Lake 评论，返回 (body_asl, body_html)。"""
    pid = _random_id()
    sid_space = _random_id()
    h = _random_hash()

    # 构建 mention 卡片
    cards_asl = ""
    spans_html = ""
    for login, name, userid in mentions:
        span_id = _random_id()
        card, span = _build_mention_card(login, name, userid, span_id, base_url)
        cards_asl += card
        spans_html += span

    # body_asl
    body_asl = (
        '<!doctype lake>'
        '<meta name="doc-version" content="1" />'
        '<meta name="viewport" content="adapt" />'
        f'<p data-lake-id="{pid}" id="{pid}">'
        f'{cards_asl}'
        f'<span data-lake-id="{sid_space}" id="{sid_space}"> </span>'
        f'</p>'
    )

    # body HTML: mention 段落
    body_html = '<div class="lake-content" typography="traditional">'
    body_html += (
        f'<p id="{pid}" class="ne-p">'
        f'{spans_html}'
        f'<span class="ne-text"> </span>'
        f'</p>'
    )

    # 如果有正文，再加一个段落
    if text:
        text_pid = _random_id()
        text_sid = _random_id()
        body_asl += (
            f'<p data-lake-id="{text_pid}" id="{text_pid}">'
            f'<span data-lake-id="{text_sid}" id="{text_sid}">{text}</span>'
            f'</p>'
        )
        body_html += (
            f'<p id="{text_pid}" class="ne-p">'
            f'<span class="ne-text">{text}</span>'
            f'</p>'
        )

    body_asl += f'<!{h}>'
    body_html += '</div>'

    return body_asl, body_html


def _html_to_text(html: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", "", html or "")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return text


def _extract_paragraphs(html: str) -> list[dict]:
    import re

    paras: list[dict] = []
    for pm in re.finditer(r'<p[^>]*\s+id="([^"]*)"[^>]*>(.*?)</p>', html, re.DOTALL):
        pid = pm.group(1)
        raw = pm.group(2)
        text = _html_to_text(raw)
        spans: list[dict] = []
        for sm in re.finditer(r'<span[^>]*\s+id="([^"]*)"[^>]*>(.*?)</span>', raw, re.DOTALL):
            spans.append({"id": sm.group(1), "text": _html_to_text(sm.group(2))})
        paras.append({"id": pid, "text": text, "spans": spans})
    return paras


_BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "blockquote"}


def _parse_lake_blocks(content: str) -> list[dict]:
    """解析 Lake HTML，提取所有块级元素及其 span 的文本和偏移。"""
    import re

    tag_alt = "|".join(sorted(_BLOCK_TAGS, key=len, reverse=True))
    block_re = re.compile(
        rf'<(?P<tag>{tag_alt})[^>]*\s+data-lake-id="(?P<bid>[^"]*)"[^>]*>'
        rf'(?P<body>.*?)'
        rf'</(?P=tag)>',
        re.DOTALL,
    )
    span_re = re.compile(
        r'<span[^>]*\s+data-lake-id="(?P<sid>[^"]*)"[^>]*>'
        r'(?P<text>.*?)'
        r'</span>',
        re.DOTALL,
    )

    def _parse(html: str) -> list[dict]:
        # 先找内层块（body 中不含其他块的视为叶子），让外层块的 text 由内层拼接
        blocks: list[dict] = []
        parts: list[tuple[int, int, dict | str]] = []  # (start, end, block_or_text)
        cursor = 0
        for bm in block_re.finditer(html):
            tag = bm.group("tag")
            if tag not in _BLOCK_TAGS:
                continue
            # 匹配前的纯文本
            if bm.start() > cursor:
                parts.append((cursor, bm.start(), html[cursor:bm.start()]))
            body = bm.group("body")
            inner_blocks = _parse(body)
            if inner_blocks:
                # body 含嵌套块 — 直接用内层块的 text 拼接
                all_text = "".join(b["text"] for b in inner_blocks)
                all_spans: list[dict] = []
                offset = 0
                for ib in inner_blocks:
                    for s in ib["spans"]:
                        all_spans.append(
                            {"span_id": s["span_id"], "text": s["text"], "offset": offset}
                        )
                        offset += len(s["text"])
                blocks.append(
                    {
                        "block_id": bm.group("bid"),
                        "text": all_text,
                        "spans": all_spans,
                    }
                )
            else:
                # 叶子块 — 直接提取 span
                spans: list[dict] = []
                offset = 0
                for sm in span_re.finditer(body):
                    span_text = _html_to_text(sm.group("text"))
                    spans.append(
                        {"span_id": sm.group("sid"), "text": span_text, "offset": offset}
                    )
                    offset += len(span_text)
                text = "".join(s["text"] for s in spans)
                blocks.append({"block_id": bm.group("bid"), "text": text, "spans": spans})
            cursor = bm.end()
        return blocks

    return _parse(content)


def find_selections(content: str, search_text: str) -> list[dict]:
    """在 Lake HTML 中搜索文本，返回匹配的 selection dict 列表。"""
    blocks = _parse_lake_blocks(content)
    results: list[dict] = []
    for block in blocks:
        for span in block["spans"]:
            pos = span["text"].find(search_text)
            while pos != -1:
                para_offset = span["offset"] + pos
                results.append(
                    {
                        "paragraph_id": block["block_id"],
                        "text_offset": para_offset,
                        "text": search_text,
                        "selection_range": {
                            "start": {
                                "id": span["span_id"],
                                "text": span["text"],
                                "offset": pos,
                                "paragraphId": block["block_id"],
                                "paragraphOffset": para_offset,
                            },
                            "end": {
                                "id": span["span_id"],
                                "text": span["text"],
                                "offset": pos + len(search_text),
                                "paragraphId": block["block_id"],
                                "paragraphOffset": para_offset + len(search_text),
                            },
                        },
                    }
                )
                pos = span["text"].find(search_text, pos + 1)
    return results


class Client:
    """语雀内部 web API 客户端。注入 httpx.Client 与 Session 以便测试。"""

    def __init__(
        self,
        http: httpx.Client,
        session: Session,
        *,
        base_url: str,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.http = http
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent

    # -- 底层请求 -----------------------------------------------------------

    def _headers(self, *, write: bool, referer: str | None) -> dict[str, str]:
        headers = {
            "Cookie": self.session.cookie_header,
            "User-Agent": self.user_agent,
            "Referer": referer or f"{self.base_url}/",
            "x-requested-with": "XMLHttpRequest",
        }
        if write:
            token = self.session.csrf_token
            if not token:
                raise ApiError("写操作缺少 CSRF token（yuque_ctoken）；请重新登录")
            headers["Content-Type"] = "application/json"
            headers["x-csrf-token"] = token
        return headers

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        write: bool = False,
        referer: str | None = None,
    ) -> httpx.Response:
        resp = self.http.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=self._headers(write=write, referer=referer),
        )
        if resp.status_code == 401:
            raise AuthExpired("登录态已失效（401）；请重新运行 yuque auth login")
        if resp.status_code >= 400:
            raise ApiError(
                f"请求失败 {resp.status_code} {method} {url}：{resp.text[:200]}",
                status_code=resp.status_code,
            )
        return resp

    @staticmethod
    def _data(resp: httpx.Response) -> Any:
        payload = resp.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # -- 用户 / 知识库 ------------------------------------------------------

    def mine(self) -> dict:
        return self._data(self._request("GET", f"{self.base_url}/api/mine"))

    def mine_repos(self) -> list[dict]:
        return self._data(self._request("GET", f"{self.base_url}/api/mine/books"))

    def groups(self) -> list[dict]:
        """用户所属的组织/团队列表（GET /api/mine/group_quick_links）。"""
        return self._data(self._request("GET", f"{self.base_url}/api/mine/group_quick_links"))

    def repo_overview(self, repo_id: int) -> dict:
        return self._data(
            self._request("GET", f"{self.base_url}/api/books/{repo_id}/overview")
        )

    def repo_docs(self, repo_id: int) -> list[dict]:
        all_docs: list[dict] = []
        offset = 0
        while True:
            page = self._data(
                self._request(
                    "GET", f"{self.base_url}/api/docs",
                    params={"book_id": repo_id, "offset": offset}
                )
            )
            if not page:
                break
            all_docs.extend(page)
            offset += len(page)
        return all_docs

    # -- 文档 ---------------------------------------------------------------

    def doc_markdown(self, space: str, repo: str, slug: str) -> str:
        url = f"{self.base_url}/{space}/{repo}/{slug}/markdown"
        raw = self._request(
            "GET",
            url,
            params={"plain": "true", "linebreak": "false", "anchor": "false"},
            referer=f"{self.base_url}/{space}/{repo}/{slug}",
        ).text
        return normalize_yuque_markdown(raw)

    def doc_detail(self, slug_or_id: str | int, repo_id: int) -> dict:
        return self._data(
            self._request(
                "GET",
                f"{self.base_url}/api/docs/{slug_or_id}",
                params={"book_id": repo_id, "include_contributors": "true"},
            )
        )

    def create_doc(
        self,
        *,
        repo_id: int,
        title: str,
        body: str | None,
        slug: str | None = None,
        public: int | None = None,
        target_uuid: str | None = None,
        group_id: int | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "book_id": repo_id,
            "title": title,
            "format": "markdown",
            "body": body or "",
        }
        if body:
            _use_lake = False
            if group_id is not None:
                mentions = _parse_inline_mentions(body)
                if mentions:
                    mention_map: dict[str, tuple[str, str, int]] = {}
                    for name in mentions:
                        users = self.search_users("Group", group_id, group_id, name)
                        if users:
                            u = users[0]
                            mention_map[name] = (u.get("login", name), u.get("name", name), u.get("id", 0))
                    if mention_map:
                        if _needs_lake_conversion(body):
                            body_html, body_asl = markdown_to_lake(
                                body, mention_map=mention_map, base_url=self.base_url,
                            )
                        else:
                            body_asl, body_html = _build_doc_lake_body(body, mention_map, self.base_url)
                        payload["format"] = "lake"
                        payload["body_asl"] = body_asl
                        payload["body"] = body_html
                        _use_lake = True
            if not _use_lake and _needs_lake_conversion(body):
                body_html, body_asl = markdown_to_lake(body)
                payload["format"] = "lake"
                payload["body_asl"] = body_asl
                payload["body"] = body_html
        if slug is not None:
            payload["slug"] = slug
        if public is not None:
            payload["public"] = public
        if target_uuid is not None:
            payload["insert_to_catalog"] = True
            payload["action"] = "prependChild"
            payload["target_uuid"] = target_uuid
        return self._data(
            self._request("POST", f"{self.base_url}/api/docs", json_body=payload, write=True)
        )

    def update_doc(
        self,
        *,
        doc_id: int,
        title: str,
        body: str,
        public: int | None = None,
        target_uuid: str | None = None,
        group_id: int | None = None,
        doc_format: str | None = None,
    ) -> dict:
        # Yuque's PUT /api/docs/{id} can silently ignore large Markdown bodies
        # on Lake-backed documents. Sending Lake HTML/ASL plus
        # content_modified=true is the reliable path for Lake docs and large
        # bodies; Markdown remains the default for small Markdown docs.
        payload: dict[str, Any] = {
            "title": title,
            "body": body,
            "format": "markdown",
            "content_modified": True,
        }
        force_lake = doc_format == "lake" or len(body) > 30000
        if body:
            mention_map: dict[str, tuple[str, str, int]] | None = None
            if group_id is not None:
                mentions = _parse_inline_mentions(body)
                if mentions:
                    mention_map = {}
                    for name in mentions:
                        users = self.search_users("Doc", doc_id, group_id, name)
                        if users:
                            u = users[0]
                            mention_map[name] = (u.get("login", name), u.get("name", name), u.get("id", 0))
                    if not mention_map:
                        mention_map = None
            if force_lake or _needs_lake_conversion(body):
                body_html, body_asl = markdown_to_lake(
                    body, mention_map=mention_map, base_url=self.base_url,
                )
                payload["format"] = "lake"
                payload["body"] = body_html
                payload["body_asl"] = body_asl
            elif mention_map:
                body_asl, body_html = _build_doc_lake_body(body, mention_map, self.base_url)
                payload["format"] = "lake"
                payload["body"] = body_html
                payload["body_asl"] = body_asl
        if public is not None:
            payload["public"] = public
        if target_uuid is not None:
            payload["insert_to_catalog"] = True
            payload["action"] = "prependChild"
            payload["target_uuid"] = target_uuid
        return self._data(
            self._request(
                "PUT", f"{self.base_url}/api/docs/{doc_id}", json_body=payload, write=True
            )
        )

    def delete_doc(self, doc_id: int) -> dict:
        return self._data(
            self._request("DELETE", f"{self.base_url}/api/docs/{doc_id}", write=True)
        )

    def publish_doc(self, doc_id: int) -> dict:
        return self._data(
            self._request(
                "PUT",
                f"{self.base_url}/api/docs/{doc_id}/publish",
                json_body={"force": False, "notify": False, "cover": None, "ignoreGlobalMessage": True},
                write=True,
            )
        )

    # -- 评论 ---------------------------------------------------------------

    def comments(self, doc_id: int) -> list[dict]:
        return self._data(
            self._request(
                "GET",
                f"{self.base_url}/api/comments",
                params={"commentable_id": doc_id, "commentable_type": "Doc"},
            )
        )

    def search_users(self, target_type: str, target_id: int, group_id: int, q: str) -> list[dict]:
        """模糊搜索用户（/api/users/complete）。"""
        return self._data(
            self._request(
                "GET",
                f"{self.base_url}/api/users/complete",
                params={"target_type": target_type, "target_id": target_id,
                        "group_id": group_id, "q": q},
            )
        )

    def create_comment(self, *, doc_id: int, body: str, selection: dict | None = None, mention: list[str] | None = None, group_id: int | None = None) -> dict:
        payload: dict[str, Any] = {
            "commentable_id": doc_id,
            "commentable_type": "Doc",
            "body": body,
        }
        if selection is not None:
            body_asl, pid, sid = _build_body_asl(body)
            payload["type"] = "WORDING_COMMENT"
            payload["format"] = "lake"
            payload["body_asl"] = body_asl
            payload["body"] = _build_body(body, pid, sid)
            payload["selection"] = selection
        if mention is not None:
            payload["mention"] = json.dumps(mention, ensure_ascii=False)
            # 解析用户真实姓名和 userid
            mention_tuples: list[tuple[str, str, int]] = []
            if group_id is not None:
                for login in mention:
                    users = self.search_users("Doc", doc_id, group_id, login)
                    if users:
                        u = users[0]
                        mention_tuples.append((login, u.get("name", login), u.get("id", 0)))
                    else:
                        mention_tuples.append((login, login, 0))
            else:
                mention_tuples = [(login, login, 0) for login in mention]
            # 将纯文本 body 升级为带 mention 卡片的 Lake 格式
            if selection is None:
                body_asl, body_html = _build_comment_with_mentions(body, mention_tuples, self.base_url)
                payload["format"] = "lake"
                payload["body_asl"] = body_asl
                payload["body"] = body_html
        return self._data(
            self._request(
                "POST", f"{self.base_url}/api/comments", json_body=payload, write=True
            )
        )

    def delete_comment(self, comment_id: int) -> dict:
        return self._data(
            self._request(
                "DELETE", f"{self.base_url}/api/comments/{comment_id}", write=True
            )
        )

    def finish_comment(self, comment_id: int) -> dict:
        return self._data(
            self._request(
                "POST", f"{self.base_url}/api/comments/finish",
                json_body={"commentId": comment_id}, write=True,
            )
        )

    # -- 评审 ---------------------------------------------------------------

    def create_review(
        self,
        *,
        target_id: int,
        name: str = "文档评审",
        description: str = "",
        approver_ids: list[int] | None = None,
        approver_department_ids: list[int] | None = None,
        cc_ids: list[int] | None = None,
        cc_department_ids: list[int] | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "target_type": "Doc",
            "target_id": target_id,
            "name": name,
            "approver_ids": approver_ids or [],
            "approver_department_ids": approver_department_ids or [],
            "cc_ids": cc_ids or [],
            "cc_department_ids": cc_department_ids or [],
        }
        if description:
            payload["description"] = description
        return self._data(
            self._request(
                "POST", f"{self.base_url}/api/reviews", json_body=payload, write=True
            )
        )

    def approve_review(self, review_id: int) -> dict:
        return self._data(
            self._request(
                "PUT",
                f"{self.base_url}/api/reviews/{review_id}/approval",
                json_body={"status": 1},
                write=True,
            )
        )

    def unapprove_review(self, review_id: int) -> dict:
        return self._data(
            self._request(
                "PUT",
                f"{self.base_url}/api/reviews/{review_id}/approval",
                json_body={"status": 2},
                write=True,
            )
        )

    def cancel_review(self, review_id: int) -> dict:
        return self._data(
            self._request(
                "PUT",
                f"{self.base_url}/api/reviews/{review_id}/cancel",
                json_body={"status": 2},
                write=True,
            )
        )
    def list_reviews(self, target_type: str, target_id: int) -> list[dict]:
        return self._data(
            self._request(
                "GET",
                f"{self.base_url}/api/getReviewsByTarget",
                params={"target_type": target_type, "target_id": target_id},
            )
        )
    # -- 上传 -----------------------------------------------------------------

    def upload_attach(self, doc_id: int, file_path: str, attach_type: str) -> dict:
        """上传图片或附件到文档。

        attach_type: ``"image"`` 或 ``"attachment"``。
        """
        ctoken = self.session.csrf_token
        if not ctoken:
            raise ApiError("写操作缺少 CSRF token（yuque_ctoken）；请重新登录")

        f_path = pathlib.Path(file_path)
        with f_path.open("rb") as f:
            resp = self.http.request(
                "POST",
                f"{self.base_url}/api/upload/attach",
                params={
                    "attachable_type": "Doc",
                    "attachable_id": doc_id,
                    "type": attach_type,
                    "ctoken": ctoken,
                },
                files={"file": (f_path.name, f)},
                headers={
                    "Cookie": self.session.cookie_header,
                    "User-Agent": self.user_agent,
                    "Referer": f"{self.base_url}/",
                    "x-requested-with": "XMLHttpRequest",
                    "x-csrf-token": ctoken,
                },
            )
        if resp.status_code == 401:
            raise AuthExpired("登录态已失效（401）；请重新运行 yuque auth login")
        if resp.status_code >= 400:
            raise ApiError(
                f"上传失败 {resp.status_code}：{resp.text[:200]}",
                status_code=resp.status_code,
            )
        return self._data(resp)

    # -- URL → id 解析（抓 appData） ----------------------------------------

    def repo_toc(self, space: str, repo: str) -> list[dict]:
        html = self._request("GET", f"{self.base_url}/{space}/{repo}").text
        return appdata.parse_app_data(html)["book"]["toc"]

    def doc_page_app_data(self, space: str, repo: str, slug: str) -> dict:
        html = self._request("GET", f"{self.base_url}/{space}/{repo}/{slug}").text
        return appdata.parse_app_data(html)

    def repo_page_app_data(self, space: str, repo: str) -> dict:
        html = self._request("GET", f"{self.base_url}/{space}/{repo}").text
        return appdata.parse_app_data(html)

    def resolve_repo_id(self, space: str, repo: str) -> int:
        html = self._request("GET", f"{self.base_url}/{space}/{repo}").text
        return appdata.repo_id(appdata.parse_app_data(html))

    def resolve_doc_ids(self, space: str, repo: str, slug: str) -> tuple[int, int]:
        data = self.doc_page_app_data(space, repo, slug)
        return appdata.repo_id(data), appdata.doc_id(data)
