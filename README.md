# skills

个人 Agent Skills 集合，遵循 [Anthropic Skill 规范](https://agentskills.io/)：每个 skill 是 `skills/` 下的一个独立目录，内含 `SKILL.md`。

## 安装

```shell
npx skills add ActiveSky/skills --skill yuque-cli
```

或一次性安装全部：

```shell
npx skills add ActiveSky/skills
```

## 列表

| Skill | 说明 |
|---|---|
| `yuque-cli` | 通过本机 `yuque` 命令读写语雀知识库与文档（cookie 认证，免会员 Token） |
