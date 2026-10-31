from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

import httpx

from .session import SESSION_COOKIE, parse_cookie_string

CDP_PORT = 9222
# 本地回环不应走代理；这些 host 在 CDP 连接时强制直连。
_NO_PROXY_HOSTS = ["127.0.0.1", "localhost", "::1"]
_WS_TIMEOUT = 5.0


class CdpUnavailable(Exception):
    """无法通过 Chrome 远程调试（CDP）抓到目标域名的会话 cookie。"""


class PlaywrightUnavailable(Exception):
    """无法通过 Playwright 获取目标域名的会话 cookie。"""


# -- 浏览器级 WebSocket 端点发现 -------------------------------------------


def default_devtools_port_files() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "Library/Application Support/Google/Chrome/DevToolsActivePort",
        home / "Library/Application Support/Google/Chrome Canary/DevToolsActivePort",
        home / "Library/Application Support/Chromium/DevToolsActivePort",
        home / "Library/Application Support/Microsoft Edge/DevToolsActivePort",
        home / ".config/google-chrome/DevToolsActivePort",
        home / ".config/chromium/DevToolsActivePort",
        home / ".config/microsoft-edge/DevToolsActivePort",
    ]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.extend([
            Path(local_appdata) / "Google/Chrome/User Data/DevToolsActivePort",
            Path(local_appdata) / "Microsoft/Edge/User Data/DevToolsActivePort",
        ])
    return candidates


def parse_devtools_active_port(text: str) -> tuple[int, str]:
    lines = text.splitlines()
    if not lines or not lines[0].strip().isdigit():
        raise CdpUnavailable("DevToolsActivePort 内容异常（缺少端口号）")
    port = int(lines[0].strip())
    ws_path = lines[1].strip() if len(lines) > 1 else ""
    return port, ws_path


def _all_devtools_port_infos() -> list[tuple[int, str]]:
    """读取所有浏览器的 DevToolsActivePort 文件，返回 [(端口, WS路径), ...]。"""
    infos: list[tuple[int, str]] = []
    for path in default_devtools_port_files():
        try:
            if path.is_file():
                infos.append(parse_devtools_active_port(path.read_text()))
        except Exception:
            continue
    return infos


def _ws_url_from_http(port: int, *, verbose: bool = False) -> Optional[str]:
    """经 /json/version 取浏览器级 WS 地址（仅远程调试完全开启时响应）。

    用 trust_env=False 绕开 *_proxy 环境变量——本地回环不该走代理。
    """
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        resp = httpx.get(url, timeout=1.0, trust_env=False)
        resp.raise_for_status()
        return resp.json().get("webSocketDebuggerUrl")
    except Exception as exc:
        if verbose:
            print(f"CDP HTTP 探测失败（{url}）：{exc!r}", file=sys.stderr)
        return None


def cdp_websocket_url(port: int = CDP_PORT, *, verbose: bool = False) -> Optional[str]:
    """发现本地浏览器级 WebSocket 调试地址；未启用远程调试则 None。

    优先从 DevToolsActivePort 文件获取 WS 地址（包含端口 + 路径，无需 HTTP 探测）。
    文件不存在时回退到 /json/version 在默认端口上探测。
    """
    # 1. 尝试从 DevToolsActivePort 文件获取 WS 地址（返回第一个可用的）
    for file_port, file_ws_path in _all_devtools_port_infos():
        if file_ws_path:
            ws_url = f"ws://127.0.0.1:{file_port}{file_ws_path}"
            if verbose:
                print(f"[CDP] 通过 DevToolsActivePort 获取到 WS 地址：{ws_url}", file=sys.stderr)
            return ws_url
        if verbose:
            print(f"[CDP] DevToolsActivePort 文件缺少 WS 路径（端口 {file_port}），尝试用文件端口探测", file=sys.stderr)
        http_url = _ws_url_from_http(file_port, verbose=verbose)
        if http_url is not None:
            return http_url

    # 2. 文件不存在或无效时，用默认端口的 /json/version 探测
    if verbose:
        print(f"[CDP] 尝试默认端口 {port} 的 /json/version", file=sys.stderr)
    http_url = _ws_url_from_http(port, verbose=verbose)
    if http_url and verbose:
        print(f"[CDP] 通过 /json/version（端口 {port}）获取到 WS 地址：{http_url}", file=sys.stderr)
    return http_url


def all_cdp_websocket_urls(port: int = CDP_PORT, *, verbose: bool = False) -> list[str]:
    """返回所有可用的浏览器级 WebSocket 调试地址（去重）。"""
    seen: set[str] = set()
    urls: list[str] = []

    def _add(url: str) -> None:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    for file_port, file_ws_path in _all_devtools_port_infos():
        if file_ws_path:
            _add(f"ws://127.0.0.1:{file_port}{file_ws_path}")
        else:
            http_url = _ws_url_from_http(file_port, verbose=verbose)
            if http_url:
                _add(http_url)

    http_url = _ws_url_from_http(port, verbose=verbose)
    if http_url:
        _add(http_url)

    if verbose:
        print(f"[CDP] 共发现 {len(urls)} 个调试地址：{urls}", file=sys.stderr)
    return urls


# -- cookie 过滤 ------------------------------------------------------------


def _domain_matches(cookie_domain: str, host: str) -> bool:
    d = cookie_domain.lstrip(".")
    return host == d or host.endswith("." + d)


def cookies_for_host(cdp_cookies: list[dict], host: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for cookie in cdp_cookies:
        if _domain_matches(str(cookie.get("domain", "")), host):
            out[cookie["name"]] = cookie["value"]
    return out


# -- WebSocket 取 cookie ----------------------------------------------------


def _storage_get_cookies(ws_url: str, *, verbose: bool = False) -> list[dict]:
    from websocket import create_connection

    if verbose:
        print(f"[CDP] 连接 WebSocket：{ws_url}", file=sys.stderr)
    # suppress_origin：Chrome 111+ 默认拒绝带 Origin 的 WS（除非 --remote-allow-origins）；
    # 不发 Origin 头即可连上，免去用户重启 Chrome 加该 flag。
    ws = create_connection(
        ws_url,
        timeout=_WS_TIMEOUT,
        http_no_proxy=_NO_PROXY_HOSTS,
        suppress_origin=True,
    )
    try:
        ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        if verbose:
            print("[CDP] 已发送 Storage.getCookies，等待响应...", file=sys.stderr)
        for _ in range(50):
            data = json.loads(ws.recv())
            if data.get("id") == 1:
                cookies = data.get("result", {}).get("cookies", [])
                if verbose:
                    print(f"[CDP] 收到 {len(cookies)} 个 cookie", file=sys.stderr)
                return cookies
        raise CdpUnavailable("CDP 未在预期内返回 cookie")
    finally:
        ws.close()
        if verbose:
            print("[CDP] WebSocket 已关闭", file=sys.stderr)


def cookies_via_cdp(base_url: str, ws_url: str, *, verbose: bool = False) -> dict[str, str]:
    """经浏览器级 WS 调 Storage.getCookies，过滤出目标域名 cookie 并校验登录态。"""
    host = urlsplit(base_url).hostname or base_url
    if verbose:
        print(f"[CDP] 目标 host：{host}，查找 {SESSION_COOKIE} cookie", file=sys.stderr)
    try:
        raw = _storage_get_cookies(ws_url, verbose=verbose)
    except CdpUnavailable:
        raise
    except Exception as exc:  # WS 连接/收发失败、端口已死等
        raise CdpUnavailable(f"CDP 抓取失败：{exc}") from exc
    if verbose:
        print(f"[CDP] 过滤匹配 {host} 的 cookie...", file=sys.stderr)
    cookies = cookies_for_host(raw, host)
    if verbose:
        print(f"[CDP] 匹配到 {len(cookies)} 个 cookie：{[k for k in cookies]}", file=sys.stderr)
    if SESSION_COOKIE not in cookies:
        if verbose:
            print(
                f"[CDP] 未找到 {SESSION_COOKIE}，"
                f"浏览器中该域名的 cookie 有：{[c['name'] for c in raw if _domain_matches(str(c.get('domain', '')), host)]}",
                file=sys.stderr,
            )
        raise CdpUnavailable(
            f"CDP 未取到 {host} 的 {SESSION_COOKIE}（请确认已在该 Chrome 登录该域名）"
        )
    return cookies


_PLAYWRIGHT_TIMEOUT = 300
_LOGIN_PATH_PATTERNS = ("/login", "/sign_in", "/signin")


def _is_login_url(url: str) -> bool:
    """判断当前 URL 是否为登录页面。"""
    from urllib.parse import urlparse

    path = urlparse(url).path.rstrip("/")
    return any(path.endswith(p) for p in _LOGIN_PATH_PATTERNS)


def _detect_proxy_args() -> list[str]:
    """从环境变量读取代理设置，返回 Chromium 的 --proxy-server / --proxy-bypass-list 参数。"""
    proxy = (os.environ.get("HTTPS_PROXY")
             or os.environ.get("https_proxy")
             or os.environ.get("HTTP_PROXY")
             or os.environ.get("http_proxy")
             or os.environ.get("ALL_PROXY")
             or os.environ.get("all_proxy"))
    if not proxy:
        return []
    args = [f"--proxy-server={proxy}"]
    no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    if no_proxy:
        args.append(f"--proxy-bypass-list={no_proxy}")
    return args


def _launch_persistent_context(pw, user_data_dir: str) -> object:
    """启动浏览器 persistent context；优先使用本地 Chrome，回退到自带 Chromium。"""
    base_args = {"user_data_dir": user_data_dir, "headless": False,
                 "args": ["--window-size=1024,768"] + _detect_proxy_args()}

    # 1. 优先系统 Chrome
    try:
        return pw.chromium.launch_persistent_context(channel="chrome", **base_args)
    except Exception:
        pass

    # 2. 回退 Playwright 自带 Chromium
    try:
        return pw.chromium.launch_persistent_context(**base_args)
    except Exception as exc:
        msg = str(exc)
        if "Executable doesn't exist" not in msg:
            raise PlaywrightUnavailable(f"启动浏览器失败：{msg}") from exc

        print("[Playwright] 首次使用，正在下载 Chromium 浏览器...", file=sys.stderr)
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
        return pw.chromium.launch_persistent_context(**base_args)


def cookies_via_playwright(base_url: str, *, verbose: bool = False) -> dict[str, str]:
    """启动 Playwright / Chromium，等待用户在浏览器中登录后返回会话 cookie。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PlaywrightUnavailable(
            "需要 Playwright 才能使用浏览器登录："
            "pip install playwright && python -m playwright install chromium"
        ) from exc

    host = urlsplit(base_url).hostname or base_url
    if verbose:
        print("[Playwright] 启动 Chromium 浏览器...", file=sys.stderr)

    pw = sync_playwright().start()
    try:
        user_data_dir = tempfile.mkdtemp(prefix="yuque-cli-pw-")
        browser = _launch_persistent_context(pw, user_data_dir)
        try:
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.evaluate("document.title = '请登录语雀 - 登录完成后将自动关闭'")

            if verbose:
                print(f"[Playwright] 导航至 {base_url}...", file=sys.stderr)
            page.goto(base_url)

            start = time.monotonic()
            while time.monotonic() - start < _PLAYWRIGHT_TIMEOUT:
                current_url = page.url
                on_login_page = _is_login_url(current_url)

                domain_cookies: dict[str, str] = {}
                for c in browser.cookies():
                    if _domain_matches(c.get("domain", ""), host):
                        domain_cookies[c["name"]] = c["value"]

                # 需要同时满足：有 _yuque_session 且不在登录页面
                if SESSION_COOKIE in domain_cookies and not on_login_page:
                    if verbose:
                        print(
                            f"[Playwright] 检测到登录态（url={current_url}），"
                            f"共 {len(domain_cookies)} 个 cookie",
                            file=sys.stderr,
                        )
                    return domain_cookies

                time.sleep(1)

            raise PlaywrightUnavailable(
                f"等待登录超时（{_PLAYWRIGHT_TIMEOUT}s），请在浏览器中手动登录语雀后再试"
            )
        finally:
            try:
                browser.close()
            except Exception:
                pass
            shutil.rmtree(user_data_dir, ignore_errors=True)
    finally:
        pw.stop()


def cookies_via_manual(prompt_fn: Callable[[], str]) -> dict[str, str]:
    return parse_cookie_string(prompt_fn())
