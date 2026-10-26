# Skills

English · [简体中文](README.zh-CN.md)

A personal collection of [Agent Skills](https://agentskills.io/) for Claude Code, Codex, Gemini CLI, and other agents that support the open skill format. Each skill is a self-contained directory under [`skills/`](skills/) with a `SKILL.md` entry point.

## Installation

Install a single skill:

```shell
npx skills add ActiveSky/skills --skill yuque-cli --global
```

Install every skill in this repository:

```shell
npx skills add ActiveSky/skills --global
```

Install into every supported agent (not just the currently detected one):

```shell
npx skills add ActiveSky/skills --skill yuque-cli --global --agent '*' --copy
```

Skills are placed in `~/.agents/skills/` and linked into each agent's skill directory. Pass `--copy` when symlinks are unavailable or undesirable (for example on Windows without developer mode).

## Available skills

| Skill | Description | Requires |
| --- | --- | --- |
| [`yuque-cli`](skills/yuque-cli/SKILL.md) | Read and write Yuque (语雀) knowledge bases and documents through the local `yuque` CLI. Uses cookie-based authentication, so no paid Yuque API token is needed. | `uv tool install yuque-cli` |

## Repository layout

```text
.
├── README.md
├── README.zh-CN.md
├── LICENSE
└── skills/
    └── yuque-cli/
        └── SKILL.md
```

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with YAML frontmatter containing `name` and `description`. The description is the trigger — state what the skill does and when to use it.
2. Keep `SKILL.md` focused. Move large reference material into `references/` and deterministic helpers into `scripts/`.
3. Commit, push, then reinstall: `npx skills add ActiveSky/skills --global --agent '*' --copy`.

## License

[MIT](LICENSE)
