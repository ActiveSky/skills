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
| [`yuque-cli`](skills/yuque-cli/SKILL.md) | 通过本机 `yuque` 命令读写语雀知识库与文档。采用 cookie 认证，无需付费的语雀 API Token。 | `uv tool install yuque-cli` |

## 仓库结构

```text
.
├── README.md
├── README.zh-CN.md
├── LICENSE
└── skills/
    └── yuque-cli/
        └── SKILL.md
```

## 新增 skill

1. 创建 `skills/<skill-name>/SKILL.md`，YAML frontmatter 至少包含 `name` 和 `description`。description 决定触发时机，要写清“做什么”和“什么时候用”。
2. 保持 `SKILL.md` 聚焦。大段参考资料放 `references/`，可复用的确定性脚本放 `scripts/`。
3. 提交并推送后重新安装：`npx skills add ActiveSky/skills --global --agent '*'`。

## 许可证

[MIT](LICENSE)
