# Third-party notices

This skill vendors the Python package **yuque-cli 3.5.0** from PyPI:

- Package: https://pypi.org/project/yuque-cli/
- Vendored files: `vendor/yuque_cli/*.py` (13 files, ~2,755 lines)
- Upstream metadata does not declare an author, license, homepage, or project URL. This copy is included with attribution to the PyPI package for internal skill use. If you are the upstream author and want different attribution or removal, please open an issue in this repository.

## Local changes in the vendored copy

- `__init__.py`: fall back to version `3.5.0` when the package is not installed via PyPI.
- `client.py`: add `content_modified=true` to document updates; for Lake-backed documents and bodies larger than 30k characters, send Lake HTML/ASL instead of Markdown. This fixes the silent “title updated, body unchanged” behavior.
- `auth.py`: lazy-import Playwright so `repo`/`doc` commands work without the browser dependency; `auth login` still requires Playwright.
