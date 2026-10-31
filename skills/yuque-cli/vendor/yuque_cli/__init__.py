"""yuque-cli: 语雀命令行客户端。"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yuque-cli")
except PackageNotFoundError:
    # Vendored copy: keep the upstream version visible when the package is not
    # installed via pip/uv.
    __version__ = "3.5.0"
