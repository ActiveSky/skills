from __future__ import annotations

import json
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Callable, Optional

import httpx
import typer

from . import __version__, auth, config, output, session
from .appdata import AppDataError
from .appdata import repo_id as appdata_repo_id
from .appdata import doc_id as appdata_doc_id
from .appdata import group_id as appdata_group_id
from .client import Client, _extract_paragraphs, find_selections
from .errors import AuthExpired, YuqueError
from .inputs import BodyInputError, resolve_body
from .session import SessionError
from .urls import RepoRef, DocRef, UrlParseError, parse_repo_ref, parse_doc_ref


@dataclass
class AppState:
    json: bool = False
    yes: bool = False
    verbose: bool = False
    host: str | None = None


app = typer.Typer(no_args_is_help=True, add_completion=False, help="语雀命令行客户端")
auth_app = typer.Typer(no_args_is_help=True, help="登录态管理")
repo_app = typer.Typer(no_args_is_help=True, help="知识库（repo）")
doc_app = typer.Typer(no_args_is_help=True, help="文档（doc）")
comment_app = typer.Typer(no_args_is_help=True, help="评论（comment）")
review_app = typer.Typer(no_args_is_help=True, help="文档评审（review）")
space_app = typer.Typer(no_args_is_help=True, help="空间（space）")
app.add_typer(auth_app, name="auth")
app.add_typer(repo_app, name="repo")
app.add_typer(doc_app, name="doc")
app.add_typer(comment_app, name="comment")
app.add_typer(review_app, name="review")
app.add_typer(space_app, name="space")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    json_out: Annotated[bool, typer.Option("--json", help="输出原始 JSON")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="跳过所有确认")] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="打印内部 HTTP 请求")
    ] = False,
    host: Annotated[
        str | None,
        typer.Option("--host", help="语雀站点 host（覆盖 YUQUE_HOST 环境变量）"),
    ] = None,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version", "-V", callback=_version_callback, is_eager=True, help="显示版本"
        ),
    ] = None,
) -> None:
    ctx.obj = AppState(json=json_out, yes=yes, verbose=verbose, host=host)


# -- 公共辅助 ---------------------------------------------------------------


@contextmanager
def cli_errors():
    try:
        yield
    except AuthExpired as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(2)
    except (YuqueError, SessionError, UrlParseError, AppDataError, BodyInputError, auth.PlaywrightUnavailable) as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(1)


def build_client(state: AppState, host_hint: str | None = None) -> Client:
    sess = session.load(config.session_file())
    hooks: dict[str, list[Callable[..., Any]]] = {}
    if state.verbose:

        def _log(request: httpx.Request) -> None:
            typer.secho(f"→ {request.method} {request.url}", fg="bright_black", err=True)

        hook: Callable[..., Any] = _log
        hooks["request"] = [hook]
    # trust_env=False：默认直连，绕开 *_proxy 环境变量（如本地 Clash 的 socks5 代理）——
    # 避免请求被本地代理拦截，也免去 SOCKS 需 socksio 的崩溃。如需经代理访问，移除此参数并装 httpx[socks]。
    http = httpx.Client(timeout=30.0, event_hooks=hooks, trust_env=False)
    # --host 显式指定优先；否则从 URL 提取的 host 作为 fallback
    return Client(http, sess, base_url=config.base_url(state.host or host_hint))


def _pager(text: str) -> None:
    """当 stdout 是终端时通过 less 分页显示，否则直接输出。"""
    if sys.stdout.isatty():
        try:
            subprocess.run(["less", "-FRX"], input=text, text=True)
        except FileNotFoundError:
            typer.echo(text)
    else:
        typer.echo(text)


def _emit(state: AppState, data, human: str) -> None:
    _pager(output.dumps(data) if state.json else human)


def _confirm(state: AppState, message: str) -> None:
    if state.yes:
        return
    if not sys.stdin.isatty():
        raise YuqueError("需要确认但当前为非交互环境；如确定请加 --yes")
    if not typer.confirm(message):
        raise typer.Abort()


def _resolve_repo_ref(
    url: str | None, space: str | None, repo: str | None
) -> "RepoRef":
    """从 url 或 --space/--repo 解析知识库引用，二者互斥。"""
    has_url = url is not None
    has_opts = space is not None or repo is not None
    if has_url and has_opts:
        raise YuqueError("URL 与 --space/--repo 不能同时使用，请选择其一")
    if has_opts and (space is None or repo is None):
        raise YuqueError("--space 和 --repo 必须同时提供")
    if not has_url and not has_opts:
        raise YuqueError("请提供 URL 或指定 --space 和 --repo")
    if has_url:
        assert url is not None
        return parse_repo_ref(url)
    assert space is not None and repo is not None
    return RepoRef(space=space, repo=repo)


def _resolve_doc_ref(
    url: str | None, space: str | None, repo: str | None
) -> "DocRef":
    """从 url 或 --space/--repo 解析文档引用，二者互斥。使用 --space/--repo 时 url 仅作为 slug。"""
    has_url = url is not None
    has_opts = space is not None and repo is not None
    if has_opts:
        if has_url:
            return DocRef(space=space, repo=repo, slug=url)  # type: ignore[arg-type]
        raise YuqueError("使用 --space/--repo 时需提供文档 slug 作为位置参数")
    if space is not None or repo is not None:
        raise YuqueError("--space 和 --repo 必须同时提供")
    if has_url:
        return parse_doc_ref(url)
    raise YuqueError("请提供 URL 或指定 --space 和 --repo")


def _read_body(body: Optional[str], file: Optional[str]) -> Optional[str]:
    return resolve_body(
        body, file, stdin=sys.stdin, stdin_isatty=sys.stdin.isatty()
    )


# -- auth -------------------------------------------------------------------


def _prompt_cookie() -> str:
    typer.echo(
        "请粘贴目标域名的完整 cookie 串"
        "（浏览器 DevTools → Application → Cookies，或 document.cookie）：",
        err=True,
    )
    return typer.prompt("cookie")


_BROWSER_OPTIONS = [
    {
        "key": "1",
        "name": "Google Chrome",
        "url": "chrome://inspect/debugging#remote-debugging",
        "app": "Google Chrome",
    },
    {
        "key": "2",
        "name": "Microsoft Edge",
        "url": "edge://inspect/debugging#remote-debugging",
        "app": "Microsoft Edge",
    },
]


def _prompt_browser_for_cdp() -> str:
    """未探测到 CDP 时询问用户选择浏览器并打开远程调试页面；返回浏览器名称。"""
    import platform

    typer.secho("未检测到本地浏览器远程调试端口，请选择要使用的浏览器：", fg="yellow", err=True)
    for opt in _BROWSER_OPTIONS:
        typer.echo(f"  {opt['key']}. {opt['name']} ({opt['url']})", err=True)

    if not sys.stdin.isatty():
        typer.secho("非交互环境无法选择浏览器，请手动开启 Chrome 远程调试后重试", fg="red", err=True)
        raise typer.Exit(1)

    choice = typer.prompt("请选择", type=str, default="1")
    selected = next((o for o in _BROWSER_OPTIONS if o["key"] == choice), None)
    if selected is None:
        raise typer.Abort()

    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", "-a", selected["app"], selected["url"]], check=False)
    elif system == "Windows":
        subprocess.run(["start", "", selected["url"]], shell=True, check=False)
    else:
        subprocess.run(["xdg-open", selected["url"]], check=False)

    return selected["name"]


_CDP_DONE_MSG = "建议及时关闭浏览器远程调试端口，避免安全风险"
_CDP_MAX_RETRIES = 3


def _try_all_cdp_urls(base: str, state: AppState) -> dict[str, str] | None:
    """遍历所有可用的 CDP WS 地址，返回第一个能取到登录态的结果；都不行则 None。"""
    for ws_url in auth.all_cdp_websocket_urls(verbose=state.verbose):
        try:
            return auth.cookies_via_cdp(base, ws_url, verbose=state.verbose)
        except auth.CdpUnavailable as exc:
            if state.verbose:
                typer.secho(f"[CDP] 尝试 {ws_url} 失败：{exc}", fg="bright_black", err=True)
    return None


def _try_cdp_login(base: str, state: AppState) -> dict:
    """尝试 CDP 获取 cookie；失败后打开浏览器并持续轮询直至成功或超时。"""
    # 首次尝试：可能已经开启
    if state.verbose:
        typer.secho("[CDP] 开始探测本地浏览器远程调试...", fg="bright_black", err=True)
    cookies = _try_all_cdp_urls(base, state)
    if cookies is not None:
        host = state.host or config.host()
        typer.secho(f"已通过 CDP 从浏览器获取 {host} 登录态", fg="green", err=True)
        typer.secho(_CDP_DONE_MSG, fg="yellow", err=True)
        return cookies
    if state.verbose:
        typer.secho("[CDP] 未探测到可用调试端口，将引导用户开启浏览器远程调试", fg="bright_black", err=True)

    # 打开浏览器引导开启远程调试
    browser_name = _prompt_browser_for_cdp()
    typer.secho(
        f"等待 {browser_name} 远程调试开启，Ctrl+C 可中断...",
        fg="yellow", err=True,
    )

    # 轮询直至成功或超时
    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    tick = 0
    retries = 0
    try:
        while retries < _CDP_MAX_RETRIES:
            # 用 spinner 替代 sleep，视觉上不卡死
            for _ in range(10):
                char = spinner[tick % len(spinner)]
                sys.stderr.write(f"\r  {char} 等待浏览器远程调试...")
                sys.stderr.flush()
                time.sleep(0.2)
                tick += 1
            retries += 1
            cookies = _try_all_cdp_urls(base, state)
            if cookies is not None:
                sys.stderr.write("\r" + " " * 40 + "\r")
                sys.stderr.flush()
                host = state.host or config.host()
                typer.secho(f"已通过 CDP 从浏览器获取 {host} 登录态", fg="green", err=True)
                typer.secho(_CDP_DONE_MSG, fg="yellow", err=True)
                return cookies
            if state.verbose:
                sys.stderr.write("\r" + " " * 60 + "\r")
                sys.stderr.flush()
                typer.secho(
                    f"[CDP] 仍未探测到可用端口，继续等待...（{retries}/{_CDP_MAX_RETRIES}）",
                    fg="bright_black", err=True,
                )
        # 超时：给出明确的下一步指示
        sys.stderr.write("\r" + " " * 40 + "\r")
        sys.stderr.flush()
        raise YuqueError(
            "浏览器远程调试连接超时。请检查：\n"
            "  1. 浏览器是否已开启远程调试？\n"
            "     在浏览器地址栏打开 chrome://inspect/#remote-debugging 配置\n"
            "  2. 如无法使用 CDP，可用 --manual 手动粘贴 cookie 登录\n"
            "  3. 或使用 --cookie 直接提供 cookie 串"
        )
    except KeyboardInterrupt:
        sys.stderr.write("\r" + " " * 40 + "\r")
        sys.stderr.flush()
        raise


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    manual: Annotated[
        bool, typer.Option("--manual", help="交互式粘贴 cookie")
    ] = False,
    cookie: Annotated[
        Optional[str], typer.Option("--cookie", help="直接提供 cookie 串完成登录")
    ] = None,
    cdp: Annotated[
        bool,
        typer.Option(
            "--cdp",
            help="通过 Chrome DevTools Protocol 从已运行的浏览器中获取 cookie",
        ),
    ] = False,
) -> None:
    """登录：默认通过 Playwright 浏览器窗口登录；也可用 --cdp / --cookie / --manual。"""
    with cli_errors():
        state: AppState = ctx.obj
        base = config.base_url(state.host)
        if cookie is not None:
            cookies = auth.cookies_via_manual(lambda: cookie)
        elif manual:
            cookies = auth.cookies_via_manual(_prompt_cookie)
        elif cdp:
            try:
                cookies = _try_cdp_login(base, state)
            except KeyboardInterrupt:
                typer.echo("", err=True)
                raise typer.Exit(1)
        else:
            try:
                cookies = auth.cookies_via_playwright(base, verbose=state.verbose)
            except KeyboardInterrupt:
                typer.echo("", err=True)
                raise typer.Exit(1)
        sess = session.Session(cookies)
        sess.require_session()
        session.save(sess, config.session_file())
    typer.echo(f"已登录，会话保存在 {config.session_file()}")


@auth_app.command("status")
def auth_status(ctx: typer.Context) -> None:
    """显示当前登录身份（GET /api/mine）。"""
    state: AppState = ctx.obj
    with cli_errors():
        user = build_client(state).mine()
        _emit(state, user, output.render_user(user))


@auth_app.command("logout")
def auth_logout(ctx: typer.Context) -> None:
    """清除本地保存的会话。"""
    path = config.session_file()
    if path.exists():
        path.unlink()
        typer.echo("已退出登录（已清除本地会话）")
    else:
        typer.echo("当前未登录")


# -- repo -------------------------------------------------------------------


@repo_app.command("list")
def repo_list(ctx: typer.Context) -> None:
    """列出我的知识库（GET /api/mine/books）。"""
    state: AppState = ctx.obj
    with cli_errors():
        repos = build_client(state).mine_repos()
        _emit(state, repos, output.render_repos(repos))


@repo_app.command("get")
def repo_get(
    ctx: typer.Context,
    url: UrlArg = None,
    space: SpaceOpt = None,
    repo: RepoOpt = None,
) -> None:
    """获取指定知识库的信息（GET /api/books/{id}/overview）。"""
    state: AppState = ctx.obj
    with cli_errors():
        ref = _resolve_repo_ref(url, space, repo)
        client = build_client(state, host_hint=ref.host)
        repo_id = client.resolve_repo_id(ref.space, ref.repo)
        data = client.repo_overview(repo_id)
        docs = client.repo_docs(repo_id)
        if state.json:
            data["docs"] = docs
        _emit(state, data, output.render_repo_overview(data, docs))


@repo_app.command("toc")
def repo_toc(
    ctx: typer.Context,
    url: UrlArg = None,
    space: SpaceOpt = None,
    repo: RepoOpt = None,
) -> None:
    """获取知识库的文档目录树（大纲视图）。"""
    state: AppState = ctx.obj
    with cli_errors():
        ref = _resolve_repo_ref(url, space, repo)
        client = build_client(state, host_hint=ref.host)
        toc = client.repo_toc(ref.space, ref.repo)
        if state.json:
            typer.echo(output.dumps(toc))
        else:
            typer.echo(output.render_toc(toc))


# -- doc --------------------------------------------------------------------

UrlArg = Annotated[Optional[str], typer.Argument(help="目标 URL 或去 host 的路径形态")]
SpaceOpt = Annotated[Optional[str], typer.Option("--space", help="语雀 space（团队/个人空间标识）")]
RepoOpt = Annotated[Optional[str], typer.Option("--repo", help="知识库标识（repo slug）")]
BodyOpt = Annotated[Optional[str], typer.Option("--body", "-b", help="内联正文")]
FileOpt = Annotated[
    Optional[str], typer.Option("--file", "-F", help="从文件读正文（- 表示 stdin）")
]
PublicOpt = Annotated[
    Optional[bool],
    typer.Option("--public/--private", help="可见性；不给则继承知识库默认/保持原值"),
]
ParentOpt = Annotated[
    Optional[str],
    typer.Option("--parent", "-p", help="父目录节点 UUID（从 repo toc 获取）"),
]


@doc_app.command("list")
def doc_list(ctx: typer.Context, url: UrlArg) -> None:
    """列出知识库下的文档。"""
    state: AppState = ctx.obj
    with cli_errors():
        assert url is not None
        ref = parse_repo_ref(url)
        client = build_client(state, host_hint=ref.host)
        repo_id = client.resolve_repo_id(ref.space, ref.repo)
        docs = client.repo_docs(repo_id)
        _emit(state, docs, output.render_docs(docs))


@doc_app.command("get")
def doc_get(ctx: typer.Context, url: UrlArg) -> None:
    """取文档正文：默认干净 Markdown；--json 出详情（含段落结构）。"""
    state: AppState = ctx.obj
    with cli_errors():
        assert url is not None
        ref = parse_doc_ref(url)
        client = build_client(state, host_hint=ref.host)
        if state.json:
            app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
            detail = client.doc_detail(ref.slug, appdata_repo_id(app_data))
            doc_meta = app_data.get("doc", {})
            book_meta = app_data.get("book", {})
            lake_body = detail.get("content") or detail.get("body_asl") or detail.get("body", "")
            combined = {
                "doc": detail,
                "doc_version_id": doc_meta.get("doc_version_id"),
                "book": {
                    "id": book_meta.get("id") or appdata_repo_id(app_data),
                    "slug": ref.repo,
                },
                "paragraphs": _extract_paragraphs(lake_body) if lake_body else [],
            }
            typer.echo(output.dumps(combined))
        else:
            typer.echo(client.doc_markdown(ref.space, ref.repo, ref.slug))


@doc_app.command("create")
def doc_create(
    ctx: typer.Context,
    url: UrlArg = None,
    space: SpaceOpt = None,
    repo: RepoOpt = None,
    title: Annotated[Optional[str], typer.Option("--title", "-t", help="文档标题")] = None,
    slug: Annotated[Optional[str], typer.Option("--slug", help="文档 slug（省略则自动生成）")] = None,
    public: PublicOpt = None,
    parent: ParentOpt = None,
    body: BodyOpt = None,
    file: FileOpt = None,
) -> None:
    """在知识库中创建文档。"""
    state: AppState = ctx.obj
    with cli_errors():
        ref = _resolve_repo_ref(url, space, repo)
        text = _read_body(body, file)
        if title is None:
            if text and text.strip():
                title = text.strip().split("\n")[0]
            else:
                raise YuqueError("--title 为必填项，或通过 --body/--file/stdin 提供正文以自动提取标题")
        client = build_client(state, host_hint=ref.host)
        app_data = client.repo_page_app_data(ref.space, ref.repo)
        repo_id = appdata_repo_id(app_data)
        group_id = appdata_group_id(app_data)
        pub = None if public is None else (1 if public else 0)
        created = client.create_doc(
            repo_id=repo_id, title=title, body=text, slug=slug, public=pub,
            target_uuid=parent, group_id=group_id,
        )
        url_out = f"{config.base_url(state.host or ref.host)}/{ref.space}/{ref.repo}/{created.get('slug', '')}"
        _emit(state, created, f"已创建：{url_out}")


PublishOpt = Annotated[
    bool, typer.Option("--publish", help="更新后自动发布文档")
]


@doc_app.command("update")
def doc_update(
    ctx: typer.Context,
    url: UrlArg = None,
    space: SpaceOpt = None,
    repo: RepoOpt = None,
    title: Annotated[Optional[str], typer.Option("--title", "-t", help="新标题")] = None,
    public: PublicOpt = None,
    parent: ParentOpt = None,
    body: BodyOpt = None,
    file: FileOpt = None,
    publish: PublishOpt = False,
) -> None:
    """更新文档（先取后合并：未给的字段保持原值）。"""
    state: AppState = ctx.obj
    with cli_errors():
        if title is None and public is None and parent is None and body is None and file is None:
            raise YuqueError(
                "没有要更新的字段（至少给 --title / --parent / 正文 / --public|--private 之一）"
            )
        ref = _resolve_doc_ref(url, space, repo)
        client = build_client(state, host_hint=ref.host)
        app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
        doc_id = appdata_doc_id(app_data)
        group_id = appdata_group_id(app_data)
        meta = app_data.get("doc", {})
        new_title = title if title is not None else meta.get("title", "")
        if body is not None or file is not None:
            new_body = _read_body(body, file) or ""
        else:
            new_body = client.doc_markdown(ref.space, ref.repo, ref.slug)
        new_public = (1 if public else 0) if public is not None else meta.get("public")
        updated = client.update_doc(
            doc_id=doc_id, title=new_title, body=new_body, public=new_public,
            target_uuid=parent, group_id=group_id, doc_format=meta.get("format"),
        )
        url_out = f"{config.base_url(state.host or ref.host)}/{ref.space}/{ref.repo}/{ref.slug}"
        _emit(state, updated, f"已更新：{url_out}")

        if publish:
            client.publish_doc(doc_id)
            _emit(state, {}, "已发布")
        elif sys.stdin.isatty() and typer.confirm("是否发布该文档？"):
            client.publish_doc(doc_id)
            _emit(state, {}, "已发布")


@doc_app.command("authors")
def doc_authors(
    ctx: typer.Context,
    url: UrlArg = None,
    space: SpaceOpt = None,
    repo: RepoOpt = None,
) -> None:
    """获取文档的协作者信息。"""
    state: AppState = ctx.obj
    with cli_errors():
        ref = _resolve_doc_ref(url, space, repo)
        client = build_client(state, host_hint=ref.host)
        app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
        detail = client.doc_detail(ref.slug, appdata_repo_id(app_data))
        _emit(state, detail, output.render_doc_authors(detail))


@doc_app.command("delete")
def doc_delete(ctx: typer.Context, url: UrlArg) -> None:
    """删除文档（软删，可在回收站恢复）。"""
    state: AppState = ctx.obj
    with cli_errors():
        assert url is not None
        ref = parse_doc_ref(url)
        client = build_client(state, host_hint=ref.host)
        app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
        doc_id = appdata_doc_id(app_data)
        title = app_data.get("doc", {}).get("title", ref.slug)
        _confirm(state, f"确认删除文档「{title}」？（软删，可在回收站恢复）")
        result = client.delete_doc(doc_id)
        _emit(state, result, "已删除（可在回收站恢复）")


@doc_app.command("publish")
def doc_publish(ctx: typer.Context, url: UrlArg) -> None:
    """发布文档（使文档更新对所有人可见）。"""
    state: AppState = ctx.obj
    with cli_errors():
        assert url is not None
        ref = parse_doc_ref(url)
        client = build_client(state, host_hint=ref.host)
        app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
        doc_id = appdata_doc_id(app_data)
        result = client.publish_doc(doc_id)
        _emit(state, result, "已发布")


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}


def _infer_attach_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return "image" if ext in _IMAGE_EXTS else "attachment"


@doc_app.command("upload")
def doc_upload(
    ctx: typer.Context,
    url: UrlArg,
    files: Annotated[
        list[str],
        typer.Argument(help="本地文件路径，可多个"),
    ],
    attach_type: Annotated[
        Optional[str],
        typer.Option(
            "--type",
            help="文件类型：image / attachment（默认根据扩展名推断）",
        ),
    ] = None,
    alt: Annotated[
        Optional[str],
        typer.Option("--alt", help="图片 alt 文本（默认取文件名）"),
    ] = None,
) -> None:
    """上传图片或附件到文档，输出对应 markdown 片段。"""
    state: AppState = ctx.obj
    with cli_errors():
        if attach_type is not None and attach_type not in ("image", "attachment"):
            raise YuqueError("--type 必须为 image 或 attachment")
        assert url is not None
        ref = parse_doc_ref(url)
        client = build_client(state, host_hint=ref.host)
        app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
        doc_id = appdata_doc_id(app_data)
        results: list[dict] = []
        for fp in files:
            path = Path(fp)
            if not path.is_file():
                raise YuqueError(f"文件不存在：{fp}")
            resolved_type = attach_type or _infer_attach_type(fp)
            data = client.upload_attach(doc_id, str(path), resolved_type)
            results.append(data)
        if state.json:
            _emit(state, results, "")
        else:
            for i, data in enumerate(results):
                file_path = files[i]
                url_out = data.get("url", "")
                filename = data.get("filename", Path(file_path).name)
                resolved_type = attach_type or _infer_attach_type(file_path)
                if resolved_type == "image":
                    alt_text = alt or Path(file_path).stem
                    typer.echo(f"![{alt_text}]({url_out})")
                else:
                    typer.echo(f"[{filename}]({url_out})")


# -- comment ----------------------------------------------------------------


@comment_app.command("list")
def comment_list(ctx: typer.Context, url: UrlArg) -> None:
    """列出文档的评论。"""
    state: AppState = ctx.obj
    with cli_errors():
        assert url is not None
        ref = parse_doc_ref(url)
        client = build_client(state, host_hint=ref.host)
        _, doc_id = client.resolve_doc_ids(ref.space, ref.repo, ref.slug)
        items = client.comments(doc_id)
        _emit(state, items, output.render_comments(items))


SelectionOpt = Annotated[
    Optional[str],
    typer.Option("--selection", "-s", help="划词评论的 selection JSON（如提供则为划词评论）"),
]
TextOpt = Annotated[
    Optional[str],
    typer.Option("--text", help="划词评论的目标文本，CLI 自动构造 selection（替代 --selection）"),
]
IndexOpt = Annotated[
    Optional[int],
    typer.Option("--index", "-n", help="多匹配时指定第几个（从 1 开始）"),
]
MentionOpt = Annotated[
    Optional[list[str]],
    typer.Option("--mention", "-m", help="@ 提及的用户 login（可多次使用），login 信息可通过 doc authors 查看"),
]
ReviewerOpt = Annotated[
    Optional[list[str]],
    typer.Option("--reviewer", "-r", help="评审人名称，支持模糊搜索（可多次使用）"),
]
CcOpt = Annotated[
    Optional[list[str]],
    typer.Option("--cc", help="抄送人名称，支持模糊搜索（可多次使用）"),
]


@comment_app.command("create")
def comment_create(
    ctx: typer.Context,
    url: UrlArg,
    body: BodyOpt = None,
    file: FileOpt = None,
    selection: SelectionOpt = None,
    text_opt: TextOpt = None,
    index: IndexOpt = None,
    mention: MentionOpt = None,
) -> None:
    """给文档添加评论。带 --text 或 --selection 时为划词评论。"""
    state: AppState = ctx.obj
    with cli_errors():
        assert url is not None
        ref = parse_doc_ref(url)
        text = _read_body(body, file)
        if not text:
            raise YuqueError("评论正文不能为空（用 --body 或 --file/-）")
        if text_opt is not None and selection is not None:
            raise YuqueError("--text 和 --selection 不能同时使用")
        client = build_client(state, host_hint=ref.host)
        _, doc_id = client.resolve_doc_ids(ref.space, ref.repo, ref.slug)
        mention_group_id: int | None = None
        if mention is not None:
            app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
            mention_group_id = appdata_group_id(app_data)
        if text_opt is not None:
            app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
            detail = client.doc_detail(ref.slug, appdata_repo_id(app_data))
            content = detail.get("content") or detail.get("body_asl") or ""
            matches = find_selections(content, text_opt)
            if not matches:
                raise YuqueError(f"文档中未找到「{text_opt}」")
            if len(matches) == 1 or index is not None:
                idx = (index or 1) - 1
                if idx < 0 or idx >= len(matches):
                    raise YuqueError(f"--index 超出范围（1-{len(matches)}）")
                sel = matches[idx]
            else:
                if not sys.stdin.isatty():
                    raise YuqueError(
                        f"文档中有 {len(matches)} 处匹配「{text_opt}」，"
                        f"非交互环境请用 --index 指定"
                    )
                typer.secho(
                    f"⚠ 文档中有 {len(matches)} 处匹配「{text_opt}」：\n",
                    fg="yellow", err=True,
                )
                for i, m in enumerate(matches):
                    sr = m["selection_range"]
                    ctx_text = sr["start"]["text"]
                    s = sr["start"]["offset"]
                    e = sr["end"]["offset"]
                    before = ctx_text[max(0, s - 10):s]
                    after = ctx_text[e:e + 10]
                    typer.echo(f"  {i + 1}. …{before} → {text_opt} ← {after}…", err=True)
                typer.echo("", err=True)
                choice = typer.prompt("请选择序号", type=int, default=1)
                if choice < 1 or choice > len(matches):
                    raise typer.Abort()
                sel = matches[choice - 1]
            created = client.create_comment(doc_id=doc_id, body=text, selection=sel, mention=mention, group_id=mention_group_id)
        elif selection is not None:
            try:
                sel = json.loads(selection)
            except json.JSONDecodeError as exc:
                raise YuqueError(f"--selection JSON 解析失败：{exc}") from exc
            created = client.create_comment(doc_id=doc_id, body=text, selection=sel, mention=mention, group_id=mention_group_id)
        else:
            created = client.create_comment(doc_id=doc_id, body=text, mention=mention, group_id=mention_group_id)
        _emit(state, created, f"已评论（id={created.get('id', '')}）")


@comment_app.command("delete")
def comment_delete(
    ctx: typer.Context,
    comment_id: Annotated[int, typer.Argument(help="评论 id（从 comment list 获取）")],
) -> None:
    """删除一条评论。"""
    state: AppState = ctx.obj
    with cli_errors():
        client = build_client(state)
        _confirm(state, f"确认删除评论 {comment_id}？")
        result = client.delete_comment(comment_id)
        _emit(state, result, "已删除评论")


@comment_app.command("finish")
def comment_finish(
    ctx: typer.Context,
    comment_id: Annotated[int, typer.Argument(help="评论 id（从 comment list 获取）")],
) -> None:
    """完成（关闭）一条评论。"""
    state: AppState = ctx.obj
    with cli_errors():
        client = build_client(state)
        _confirm(state, f"确认完成评论 {comment_id}？")
        result = client.finish_comment(comment_id)
        _emit(state, result, "已完成评论")


# -- review ------------------------------------------------------------------


@review_app.command("create")
def review_create(
    ctx: typer.Context,
    url: UrlArg = None,
    space: SpaceOpt = None,
    repo: RepoOpt = None,
    name: Annotated[str, typer.Option("--name", "-n", help="评审名称")] = "文档评审",
    description: Annotated[
        Optional[str], typer.Option("--description", "-d", help="评审描述")
    ] = None,
    reviewer: ReviewerOpt = None,
    cc: CcOpt = None,
) -> None:
    """创建文档评审。"""
    state: AppState = ctx.obj
    with cli_errors():
        ref = _resolve_doc_ref(url, space, repo)
        client = build_client(state, host_hint=ref.host)
        app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
        doc_id = appdata_doc_id(app_data)
        group_id = appdata_group_id(app_data)

        if not reviewer:
            raise YuqueError("至少需要指定一个评审人（--reviewer）")

        approver_ids: list[int] = []
        for raw_name in reviewer or []:
            users = client.search_users("Doc", doc_id, group_id, raw_name)
            if not users:
                raise YuqueError(f"未找到评审人「{raw_name}」，请检查名称是否正确")
            approver_ids.append(users[0]["id"])

        cc_ids: list[int] = []
        for raw_name in cc or []:
            users = client.search_users("Doc", doc_id, group_id, raw_name)
            if not users:
                raise YuqueError(f"未找到抄送人「{raw_name}」，请检查名称是否正确")
            cc_ids.append(users[0]["id"])

        result = client.create_review(
            target_id=doc_id,
            name=name,
            description=description or "",
            approver_ids=approver_ids,
            cc_ids=cc_ids,
        )
        url_out = (
            f"{config.base_url(state.host or ref.host)}"
            f"/{ref.space}/{ref.repo}/{ref.slug}"
        )
        _emit(
            state,
            result,
            output.render_review(
                result, url_out,
                approver_names=reviewer,
                cc_names=cc,
            ),
        )


@review_app.command("approve")
def review_approve(
    ctx: typer.Context,
    review_id: Annotated[int, typer.Argument(help="评审 id（从 review create 返回值获取）")],
) -> None:
    """通过评审。"""
    state: AppState = ctx.obj
    with cli_errors():
        client = build_client(state)
        result = client.approve_review(review_id)
        _emit(state, result, f"已通过评审（id={review_id}）")


@review_app.command("unapprove")
def review_unapprove(
    ctx: typer.Context,
    review_id: Annotated[int, typer.Argument(help="评审 id（从 review list 获取）")],
) -> None:
    """不通过评审。"""
    state: AppState = ctx.obj
    with cli_errors():
        client = build_client(state)
        result = client.unapprove_review(review_id)
        _emit(state, result, f"已拒绝评审（id={review_id}）")


@review_app.command("cancel")
def review_cancel(
    ctx: typer.Context,
    review_id: Annotated[int, typer.Argument(help="评审 id（从 review list 获取）")],
) -> None:
    """取消评审。"""
    state: AppState = ctx.obj
    with cli_errors():
        client = build_client(state)
        result = client.cancel_review(review_id)
        _emit(state, result, f"已取消评审（id={review_id}）")
@review_app.command("list")
def review_list(
    ctx: typer.Context,
    url: UrlArg = None,
    space: SpaceOpt = None,
    repo: RepoOpt = None,
) -> None:
    """获取文档的所有评审。"""
    state: AppState = ctx.obj
    with cli_errors():
        ref = _resolve_doc_ref(url, space, repo)
        client = build_client(state, host_hint=ref.host)
        app_data = client.doc_page_app_data(ref.space, ref.repo, ref.slug)
        doc_id = appdata_doc_id(app_data)
        reviews = client.list_reviews("Doc", doc_id)
        _emit(state, reviews, output.render_reviews(reviews))
# -- space ------------------------------------------------------------------


@space_app.command("list")
def space_list(ctx: typer.Context) -> None:
    """列出所有可访问的空间（个人空间 + 组织/团队）。"""
    state: AppState = ctx.obj
    with cli_errors():
        client = build_client(state)
        user = client.mine()
        spaces: list[dict] = [
            {
                "id": user.get("id"),
                "login": user.get("login", ""),
                "name": user.get("name", ""),
            }
        ]
        for g in client.groups():
            target = g.get("target", {})
            spaces.append(
                {
                    "id": target.get("id", g.get("id")),
                    "login": target.get("login", ""),
                    "name": g.get("title") or target.get("name", ""),
                }
            )
        _emit(state, spaces, output.render_spaces(spaces))
