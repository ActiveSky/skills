# Skills

[English](README.md) · 简体中文

个人维护的 [Agent Skills](https://agentskills.io/) 集合，适用于 Claude Code、Codex、Gemini CLI 等支持开放 skill 格式的智能体。每个 skill 是 [`skills/`](skills/) 下的一个独立目录，入口文件为 `SKILL.md`。

## 安装

安装单个 skill：

```shell
npx skills add ActiveSky/skills --skill yuque-cli --global
```

安装本仓库全部 skill：

```shell
npx skills add ActiveSky/skills --global
```

安装到所有受支持的智能体（而不只是当前检测到的那个）：

```shell
npx skills add ActiveSky/skills --skill yuque-cli --global --agent '*'
```

skill 只在 `~/.agents/skills/` 存一份，再链接到各智能体的 skill 目录（Windows 上使用目录联接），改动源文件会立即对所有智能体生效。只有确实需要独立副本时才加 `--copy`。

## 可用 skill

| Skill | 说明 | 前置依赖 |
| --- | --- | --- |
| [`yuque-cli`](skills/yuque-cli/SKILL.md) | 通过内置的 `yuque-cli` 3.5.0 读写语雀知识库与文档。采用 cookie 认证，无需付费的语雀 API Token。 | `uv` + `skills/yuque-cli/bootstrap.ps1` |
| [`lark-plus`](skills/lark-plus/SKILL.md) | 飞书官方 28 个 skill 的统一入口（文档、云空间、多维表格、表格、消息、日历、邮件、任务、会议、知识库、OKR、审批等）。依赖官方 `lark-cli`；内置快照由 `larksuite/cli` release 自动同步。 | `lark-cli` |

## 内置 CLI（vendored）

`yuque-cli` skill 把 PyPI 包 [`yuque-cli` 3.5.0](https://pypi.org/project/yuque-cli/) 的源码放在 [`skills/yuque-cli/vendor/`](skills/yuque-cli/vendor/)。上游包的元数据没有声明作者或许可证；来源、署名和本地修改见 [`THIRD_PARTY_NOTICES.md`](skills/yuque-cli/THIRD_PARTY_NOTICES.md)。

安装 skill 后，先初始化 Python 环境：

```powershell
cd ~/.agents/skills/yuque-cli
./bootstrap.ps1
./scripts/yuque.ps1 auth status
```

本地优化：

- `--parent ""` 把文档放到目录树顶层；`--parent <uuid>` 放到指定目录下。
- 大正文更新使用 `content_modified=true`，并对 Lake 文档或超过 30k 字符的正文改走 Lake HTML/ASL，修复“只更新标题、正文不变”的静默失败。
- Playwright 改为懒加载；只有 `auth login` 需要它。
- 补充 `yuque --json doc get ...`（全局选项放在子命令前）的用法。

## 内置飞书 skills

`lark-plus` 把官方 [`larksuite/cli`](https://github.com/larksuite/cli) 的 skills 内置在 `skills/lark-plus/lark-*/` 下。快照由 [`.github/workflows/sync-lark-plus.yml`](.github/workflows/sync-lark-plus.yml) 从上游最新 release 自动同步；同步的 tag 和 commit 记录在 `skills/lark-plus/UPSTREAM_VERSION`。上游使用 MIT 许可证，见 [`skills/lark-plus/UPSTREAM_LICENSE`](skills/lark-plus/UPSTREAM_LICENSE)。

本地同步与校验：

```powershell
./skills/lark-plus/scripts/sync-lark-skills.ps1 -Tag v1.0.98
./skills/lark-plus/scripts/validate-lark-plus.ps1
```

## 仓库结构

```text
.
├── README.md
├── README.zh-CN.md
├── LICENSE
├── .github/
│   └── workflows/
│       └── sync-lark-plus.yml
└── skills/
    ├── yuque-cli/
    │   ├── SKILL.md
    │   ├── bootstrap.ps1 / bootstrap.sh
    │   ├── requirements.txt
    │   ├── THIRD_PARTY_NOTICES.md
    │   ├── scripts/
    │   │   ├── yuque.py
    │   │   ├── yuque.ps1
    │   │   └── yuque.sh
    │   └── vendor/
    │       └── yuque_cli/  (vendored 3.5.0, 13 files)
    └── lark-plus/
        ├── SKILL.md
        ├── UPSTREAM_VERSION
        ├── UPSTREAM_LICENSE
        ├── lark-*/  (28 vendored official skills)
        └── scripts/
            ├── sync-lark-skills.ps1
            └── validate-lark-plus.ps1
```

## 新增 skill

1. 创建 `skills/<skill-name>/SKILL.md`，YAML frontmatter 至少包含 `name` 和 `description`。description 决定触发时机，要写清“做什么”和“什么时候用”。
2. 保持 `SKILL.md` 聚焦。大段参考资料放 `references/`，可复用的确定性脚本放 `scripts/`。
3. 提交并推送后重新安装：`npx skills add ActiveSky/skills --global --agent '*'`。

## 许可证

本仓库自己的代码与文档使用 [MIT](LICENSE)。vendored 的 `yuque-cli` 源码单独署名于 [`skills/yuque-cli/THIRD_PARTY_NOTICES.md`](skills/yuque-cli/THIRD_PARTY_NOTICES.md)；上游包未声明许可证。内置的飞书 skills 来自 [`larksuite/cli`](https://github.com/larksuite/cli)，按 MIT 许可证使用，见 [`skills/lark-plus/UPSTREAM_LICENSE`](skills/lark-plus/UPSTREAM_LICENSE)。
