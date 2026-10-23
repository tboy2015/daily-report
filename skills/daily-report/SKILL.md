---
name: daily-report
description: 自动生成每日工作日报，汇总当天的 Git 提交记录以及 Claude Code、Codex 对话内容，按固定模板生成日报并可发送邮件。
allowed-tools:
  - mcp__daily_report__get_daily_data
  - mcp__daily_report__collect_codex_conversations
  - mcp__daily_report__save_daily_report
  - mcp__daily_report__send_daily_report_email
  - mcp__daily_report__get_email_config
---

# 日报生成与发送

完整工作流和格式约束位于 `../../SKILL.md`。执行日报任务前，必须完整读取该文件并严格遵循其中的全部要求。
