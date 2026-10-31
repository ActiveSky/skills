---
name: lark-plus
description: "飞书/Lark 全能入口：通过 lark-cli 操作飞书消息与群聊、云文档 Docx/Wiki、云空间 Drive、多维表格 Base、电子表格 Sheets、幻灯片 Slides、画板 Whiteboard、知识库 Wiki、日历与会议室、视频会议/纪要/逐字稿/妙记、邮箱、任务、OKR、审批、考勤、通讯录、妙搭应用与实时事件。用户提到飞书/Lark、lark-cli、feishu.cn/larksuite.com/doubao.com 的 /docx/ /wiki/ /base/ /sheets/ /slides/ /app/ 链接，或要求发飞书消息、查日程、整理会议纪要、读写飞书文档/表格时使用。不用于飞书小程序开发（opdev）或纯本地 Markdown 操作。"
---

# lark-plus：飞书官方 skills 统一路由

本 skill 聚合 `larksuite/cli` 官方 28 个 skill。**只加载当前任务需要的子技能，不要一次读完。**

## 硬性规则

1. 子技能优先级高于本路由；进入某个子技能后，按它的 `SKILL.md` 执行。
2. 认证、身份、权限、高风险确认、输出契约以 `lark-shared/SKILL.md` 为准。
3. 写入/删除前先确认用户意图；支持 `--dry-run` 的命令先 dry-run；退出码 10 是高风险确认门禁，不是错误。
4. `--file`、`--output`、`@file` 等路径参数只接受 CWD 下的相对路径。
5. 命令输出授权 URL 时，用 `lark-cli auth qrcode` 生成二维码，URL 与二维码一起展示。

## 路由表

### 平台与账号

| 意图 | 读取 |
|---|---|
| 登录/登出/授权/身份/scope/权限 | `lark-shared/SKILL.md` |
| 原生 OpenAPI（现有命令未覆盖） | `lark-openapi-explorer/SKILL.md` |
| 封装新的 lark-cli skill | `lark-skill-maker/SKILL.md` |

### 内容与文件

| 意图 | 读取 |
|---|---|
| 云文档 Docx / Wiki 内容读写、图片附件、思维笔记 | `lark-doc/SKILL.md` |
| 云空间 Drive：上传下载、文件夹、权限、评论、导入导出 | `lark-drive/SKILL.md` |
| 多维表格 Base：表/字段/记录/视图/仪表盘/表单/BaseApp | `lark-base/SKILL.md` |
| 电子表格 Sheets：单元格/公式/图表/透视表 | `lark-sheets/SKILL.md` |
| 幻灯片 Slides | `lark-slides/SKILL.md` |
| 画板 Whiteboard | `lark-whiteboard/SKILL.md` |
| 知识库 Wiki：空间/节点/成员 | `lark-wiki/SKILL.md` |
| 原生 Markdown 文件 | `lark-markdown/SKILL.md` |

### 沟通与协作

| 意图 | 读取 |
|---|---|
| 消息/群聊/聊天记录/交互卡片 | `lark-im/SKILL.md` |
| 邮箱 | `lark-mail/SKILL.md` |
| 日历/日程/会议室/忙闲 | `lark-calendar/SKILL.md` |
| 视频会议/纪要/逐字稿/妙记 | `lark-meeting/SKILL.md` |
| 任务/待办/清单 | `lark-task/SKILL.md` |
| 通讯录/open_id/找人 | `lark-contact/SKILL.md` |
| OKR | `lark-okr/SKILL.md` |
| 审批 | `lark-approval/SKILL.md` |
| 考勤 | `lark-attendance/SKILL.md` |

### 应用、事件与工作流

| 意图 | 读取 |
|---|---|
| 妙搭 Spark/Miaoda 应用开发与托管 | `lark-apps/SKILL.md` |
| 实时事件订阅/机器人 | `lark-event/SKILL.md` |
| 会议纪要汇总工作流 | `lark-workflow-meeting-summary/SKILL.md` |
| 日程待办摘要工作流 | `lark-workflow-standup-report/SKILL.md` |

### 别名

`lark-minutes`、`lark-note`、`lark-vc`、`lark-vc-agent` 是 `lark-meeting` 的转发入口，统一读 `lark-meeting/SKILL.md`。

## URL / token 路由

- `/docx/` 或 `/wiki/` 的文档内容 → `lark-doc`
- `/wiki/` 的空间/节点结构 → `lark-wiki`
- `/base/` 或 `/app/`（BaseApp） → `lark-base`
- `/sheets/` → `lark-sheets`
- `/slides/` → `lark-slides`
- `/app/app_`、`*.aiforce.cloud`、`/page/`（妙搭） → `lark-apps`
- 云空间文件/文件夹、导入导出 → `lark-drive`
- 无法判断链接类型 → 先用 `lark-cli drive +inspect` 或 `lark-cli drive +url-resolve`

## 跨域任务

按阶段依次加载，不要预加载：

- “把会议纪要整理成飞书文档”：`lark-meeting` → `lark-doc`
- “把 Excel 导入飞书并建表”：`lark-drive` → `lark-sheets` 或 `lark-base`
- “发消息并附文档链接”：`lark-doc` / `lark-drive` → `lark-im`
- “查日程并生成待办”：`lark-calendar` → `lark-task`

## 兜底

- 不确定命令：`lark-cli --help`、`lark-cli <domain> --help`、`lark-cli schema`
- 环境/登录异常：`lark-cli doctor`、`lark-cli auth status`
- 子技能内部说“先读 lark-shared”时，按它的指示读 `lark-shared/SKILL.md`，不要重复读。
