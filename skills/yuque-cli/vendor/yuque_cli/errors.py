from __future__ import annotations


class YuqueError(Exception):
    """yuque-cli 的运行期错误基类。"""


class AuthExpired(YuqueError):
    """登录态失效（HTTP 401）。"""


class ApiError(YuqueError):
    """内部接口返回非预期状态码。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
