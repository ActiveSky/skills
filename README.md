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
npx skills add ActiveSky/skills --skill yuque-cli --global --agent '*'
```

Skills are stored once in `~/.agents/skills/` and linked into each agent's skill directory (directory junctions on Windows), so editing the source updates every agent at once. Pass `--copy` only if you deliberately want independent copies.

## Available skills

| Skill | Description | Requires |
| --- | --- | --- |
| [`yuque-cli`](skills/yuque-cli/SKILL.md) | Read and write Yuque (语雀) knowledge bases and documents through a vendored `yuque-cli` 3.5.0 CLI. Uses cookie-based authentication, so no paid Yuque API token is needed. | `uv` + `skills/yuque-cli/bootstrap.ps1` |
| [`lark-plus`](skills/lark-plus/SKILL.md) | Single-entry router for the official 28 Lark/Feishu skills (docs, Drive, Base, Sheets, IM, calendar, mail, tasks, meetings, wiki, OKR, approvals, and more). Uses the official `lark-cli`; the vendored snapshot is synced from `larksuite/cli` releases. | `lark-cli` |

## Vendored CLI

The `yuque-cli` skill vendors the Python package [`yuque-cli` 3.5.0](https://pypi.org/project/yuque-cli/) under [`skills/yuque-cli/vendor/`](skills/yuque-cli/vendor/). The upstream package metadata does not declare an author or license; see [`THIRD_PARTY_NOTICES.md`](skills/yuque-cli/THIRD_PARTY_NOTICES.md) for attribution and the list of local changes.

After installing the skill, bootstrap its Python environment:

```powershell
cd ~/.agents/skills/yuque-cli
./bootstrap.ps1
./scripts/yuque.ps1 auth status
```

Local optimizations:

- `--parent ""` creates a document at the TOC top level; `--parent <uuid>` places it under a directory.
- Large document updates use `content_modified=true` and Lake HTML/ASL for Lake-backed docs or bodies over 30k characters, fixing the silent “title updated, body unchanged” failure.
- Playwright is lazy-imported; only `auth login` needs it.
- `yuque --json doc get ...` (global flag before the subcommand) is documented.

## Vendored Lark/Feishu skills

`lark-plus` vendors the official [`larksuite/cli`](https://github.com/larksuite/cli) skills under `skills/lark-plus/lark-*/`. The snapshot is refreshed from the latest upstream release by [`.github/workflows/sync-lark-plus.yml`](.github/workflows/sync-lark-plus.yml); the synced tag and commit are recorded in `skills/lark-plus/UPSTREAM_VERSION`. The upstream project is MIT-licensed; see [`skills/lark-plus/UPSTREAM_LICENSE`](skills/lark-plus/UPSTREAM_LICENSE).

Sync and validate locally:

```powershell
./skills/lark-plus/scripts/sync-lark-skills.ps1 -Tag v1.0.98
./skills/lark-plus/scripts/validate-lark-plus.ps1
```

## Repository layout

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

## Adding a skill

1. Create `skills/<skill-name>/SKILL.md` with YAML frontmatter containing `name` and `description`. The description is the trigger — state what the skill does and when to use it.
2. Keep `SKILL.md` focused. Move large reference material into `references/` and deterministic helpers into `scripts/`.
3. Commit, push, then reinstall: `npx skills add ActiveSky/skills --global --agent '*'`.

## License

[MIT](LICENSE) for this repository's own code and documentation. The vendored `yuque-cli` source is attributed separately in [`skills/yuque-cli/THIRD_PARTY_NOTICES.md`](skills/yuque-cli/THIRD_PARTY_NOTICES.md); its upstream package does not declare a license. The vendored Lark/Feishu skills come from [`larksuite/cli`](https://github.com/larksuite/cli) and are used under the MIT license; see [`skills/lark-plus/UPSTREAM_LICENSE`](skills/lark-plus/UPSTREAM_LICENSE).
