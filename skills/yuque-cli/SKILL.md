---
name: yuque-cli
description: 通过本机 `yuque` 命令读写语雀（Yuque）的个人知识库与文档。当用户提到语雀、yuque、yuque.com 链接、知识库、把笔记/周报/总结同步或归档到语雀、读取或修改语雀里的某篇文档、查看知识库目录结构、把 Markdown 导入语雀时使用。即使用户没说“语雀”二字，只要上下文涉及语雀里的内容或想让 AI 代读代写语雀文档，也应当使用本 skill。
---

# 语雀读写（yuque-cli）

本 skill 驱动的是 PyPI 版 `yuque-cli`：它用浏览器 cookie 调用语雀网页内部接口，因此**不需要语雀会员 Token**（官方 Open API 的个人 Token 是超级会员专属）。

## 环境前置

```powershell
yuque --version          # 应输出 3.x
yuque auth status        # 确认登录态
```

- 未安装：`uv tool install yuque-cli`
- 会话文件：`~/.config/yuque-cli/session.json`（Windows 下为 `C:\Users\<用户名>\.config\yuque-cli\session.json`），里面是**明文完整 cookie**

`auth status` 返回 401 时不要反复重试，让用户重新登录：

```powershell
yuque auth login          # Playwright 弹窗，必须真正进入工作台后再关窗口
```

CLI 只要看到 cookie 存在就会打印“已登录”，但服务端未必认。所以登录后一定要再跑一次 `yuque auth status` 验证，不要凭“已登录”这句话就继续。

## 地址格式：必须两段式

所有知识库地址写成 `<space>/<repo>`，文档写成 `<space>/<repo>/<doc-slug>`：

```powershell
yuque repo list                          # 拿到 repo slug
yuque doc list active_sky/jqxx           # 正确
yuque doc list jqxx                      # 报错：知识库地址应形如 {space}/{repo}
yuque doc get  active_sky/jqxx/<slug>
```

`space` 从 `auth status` 的 `space:` 字段读取（本机当前为 `active_sky`），不要凭记忆硬编码；用户可能切换账号或空间。文档 slug 从 `doc list` 获取，不要自己猜。

完整浏览器 URL（`https://www.yuque.com/active_sky/jqxx/xxxx`）和去 host 的路径形态等价，遇到用户直接贴链接时可以直接传入。

## 读操作

```powershell
yuque repo list                                    # 知识库列表
yuque repo get active_sky/jqxx                     # 单个知识库信息
yuque repo toc active_sky/jqxx                     # 目录树（找文档在哪一层）
yuque doc list active_sky/jqxx                     # 文档列表
yuque doc get  active_sky/jqxx/<slug>              # 正文，默认干净 Markdown
yuque doc get  active_sky/jqxx/<slug> --json       # 带段落结构等详情
```

给脚本或 AI 消费时用 `--json`；给人看或写进文件时用默认 Markdown。

## 写操作

```powershell
# 创建
yuque doc create active_sky/jqxx -t "周报 2026-W43" -F weekly.md --private

# 更新（先取后合并：没给的字段保持原值）
yuque doc update active_sky/jqxx/<slug> -F revised.md
yuque doc update active_sky/jqxx/<slug> -t "新标题"

# 删除（软删，进回收站可恢复）
yuque --yes doc delete active_sky/jqxx/<slug>
```

正文来源三选一（`--body` 与 `--file` 互斥）：`-b` 内联、`-F` 读文件、管道 stdin。长文一律先写本地文件再用 `-F`，避免命令行转义问题。

`--private` 建议显式给，避免文档继承知识库的公开设置。新建前若用户没指定知识库，先用 `repo list` 让用户确认目标，不要默认丢进“默认知识库”。

## 操作纪律

- **写之前先说清楚要去哪个库、文档标题是什么，等用户确认**。语雀是用户长期积累的正式笔记，误建一篇文档比多问一句代价大。
- 更新前先 `doc get` 读原文，再基于原文改。`doc update` 是“先取后合并”，但覆盖正文时仍可能丢掉用户手工改过的内容。
- 删除一律视为可恢复操作，但不要批量删；单篇删除前确认 slug 对应的是哪篇（看标题，不看位置）。
- 批量导入/迁移要分批，比如每批 5–10 篇，中间停顿。内部接口有风控，高频调用会被屏蔽。
- 不要把 `session.json` 的内容打印出来、写进仓库或发给外部服务；它等同于账号凭证。

## 已知坑

- `doc list`/`doc get` 只接受两段或三段地址，单给 repo slug 必报错。
- `auth login` 打印“已登录”不代表会话有效，必须用 `auth status` 复核。
- `--cdp` 要求 Chrome 以 `--remote-debugging-port` 启动；用户已有 Chrome 在跑时不要选它，用默认弹窗或 `--manual` / `--cookie`。
- Markdown 往返会被语雀的 Lake 格式规范化，例如 `-` 列表读回变成 `+`，代码块前后可能多空行。内容没丢，不要误判为写入失败。
- 这是网页内部接口，不是公开契约，语雀改版后可能失效。遇到大批量 401/403 先停手，让用户复查登录态，不要继续重试。

## 汇报方式

完成后说明：目标知识库、文档标题、操作类型（新建/更新/删除），并给出可点击的语雀链接（形如 `https://www.yuque.com/<space>/<repo>/<slug>`）。读操作则直接给结论，不要贴整篇原文，除非用户要求。
