# Codex 适配说明

本仓库同时支持 Claude Code 和 Codex。Codex 通过仓库内的插件清单加载 `daily-report` Skill 与同名 MCP 服务。

## 前置条件

1. 安装 [uv](https://docs.astral.sh/uv/)。
2. 复制 `config.example.json` 为 `config.json`，填写用户信息、代码扫描目录和 SMTP 配置。Codex 对话默认从 `~/.codex/sessions`（含归档会话）读取，也可通过 `paths.codex_sessions_dir` 覆盖。

MCP 服务由 Codex 插件通过 `scripts/codex-mcp-launcher.sh` 启动。启动器兼容终端与 macOS 桌面应用不同的 PATH 环境，并使用 `uv` 根据脚本头部声明自动准备依赖。

## 安装到 Codex

将本仓库作为本地 Codex 插件源加入一个 marketplace，随后安装 `daily-report` 插件。安装或更新插件后，请完全退出并重新打开 Codex，再新建一个任务，使新的 Skill 和 MCP 工具生效。

插件加载成功后，可以直接输入：

```text
生成并发送今天的工作日报
```

仅生成、不发送邮件：

```text
生成今天的工作日报，但不要发送邮件
```

## 插件结构

- `.codex-plugin/plugin.json`：Codex 插件清单
- `.mcp.json`：本地 MCP 服务启动配置
- `skills/daily-report/SKILL.md`：Codex 技能入口
- `scripts/mcp-server.py`：Claude Code 与 Codex 共用的 MCP 实现

## 排查

如果 Codex 提示 `daily-report MCP 工具不可用`：

1. 运行 `codex mcp get daily-report`。如果输出的是手工注册的旧路径（例如
   `~/.claude/skills/daily-report/scripts/mcp-server.py`），它会与插件内同名 MCP
   服务冲突。运行 `codex mcp remove daily-report` 删除这个旧的全局注册；不要再用
   `codex mcp add` 注册本插件。
2. 确认 `uv --version` 可正常执行。
3. 在仓库根目录运行 `uv run scripts/mcp-server.py`，确认服务可以启动。
4. 重新安装插件，完全退出并重新打开 Codex，再新建任务重试；已运行的 Codex 后台服务和旧任务不会自动获得新加载的 MCP 工具。

`codex mcp list` 只显示手工写入 Codex 全局配置的 MCP 服务，不显示插件随附的
MCP 服务。因此不要以列表中缺少 `daily-report` 判断插件安装失败；插件状态应使用
`codex plugin list` 检查。
