# 新电脑部署指南

## 前置条件

- [Claude Code](https://claude.ai/code) 已安装并登录
- Python 3.10+
- Git

---

## 步骤一：克隆仓库

将仓库放到任意目录，建议放在 `~/.claude/skills/` 下便于管理：

```bash
git clone <repo-url> ~/.claude/skills/daily-report
cd ~/.claude/skills/daily-report
```

---

## 步骤二：安装 Python 依赖

```bash
pip install mcp
```

> 如果系统有多个 Python，用 `pip3` 或 `python3 -m pip install mcp`。

---

## 步骤三：填写配置文件

```bash
cp config.example.json config.json
```

用编辑器打开 `config.json`，填写所有字段：

```json
{
  "user": {
    "name": "张三",
    "greeting": "南网业务处张三",
    "company": "XX 公司",
    "department": "XX 部门",
    "phone": "138xxxxxxxx",
    "email": "zhangsan@company.com"
  },
  "paths": {
    "work_dir": "~/work/code"
  },
  "smtp_server": "smtp.qq.com",
  "smtp_port": 587,
  "smtp_user": "zhangsan@qq.com",
  "smtp_password": "授权码（不是登录密码）",
  "from_email": "zhangsan@qq.com",
  "to_emails": ["leader@company.com"],
  "use_tls": true,
  "use_ssl": false
}
```

字段说明：

| 字段 | 说明 |
|------|------|
| `user.name` | 落款姓名 |
| `user.greeting` | 日报开头用语，如"南网业务处张三" |
| `paths.work_dir` | 存放所有 git 仓库的根目录，MCP 会递归扫描其下所有仓库 |
| `smtp_password` | QQ 邮箱用"授权码"，企业邮箱用密码或应用专用密码 |
| `to_emails` | 收件人列表，可填多个 |

**自定义项目中文名**（可选）：在 `config.json` 中加一节，将仓库目录名映射为业务名：

```json
"project_name_map": {
  "my-backend-repo": "XX 系统后端",
  "my-frontend-repo": "XX 系统前端"
}
```

**自定义日报默认文案**（可选）：

```json
"defaults": {
  "plans": [
    "开展当日开发功能的单元测试、联调测试和回归验证",
    "根据测试反馈修复问题，优化用户交互体验"
  ],
  "milestone_module": "核心业务模块",
  "milestone_stage": "开发阶段",
  "milestone_percent": "50",
  "milestone_next_step": "功能测试、Bug 修复、代码审查",
  "milestone_risk": "需进一步验证稳定性和部署环境差异"
}
```

---

## 步骤四：注册 MCP 服务

```bash
claude mcp add daily-report -- python3 ~/.claude/skills/daily-report/scripts/mcp-server.py
```

> Windows 路径示例：
> ```
> claude mcp add daily-report -- python C:\Users\你的用户名\.claude\skills\daily-report\scripts\mcp-server.py
> ```

验证注册成功：

```bash
claude mcp list
```

输出中应出现 `daily-report`。

---

## 步骤五：注册 Skill

将 `SKILL.md` 复制到 Claude Code 的 skills 目录：

```bash
# macOS / Linux
cp ~/.claude/skills/daily-report/SKILL.md ~/.claude/skills/daily-report.md

# Windows（PowerShell）
Copy-Item "$env:USERPROFILE\.claude\skills\daily-report\SKILL.md" "$env:USERPROFILE\.claude\skills\daily-report.md"
```

---

## 验证

重启 Claude Code，在对话中输入：

```
/daily-report 不发送邮件
```

看到日报正文输出即表示部署成功。

---

## 日常使用

| 命令 | 效果 |
|------|------|
| `/daily-report` | 生成当日日报，保存文件并发送邮件 |
| `/daily-report 不发送邮件` | 只生成和保存，不发邮件 |

日报保存在仓库的 `output/daily-reports/YYYY-MM-DD.md`（不进版本控制）。

---

## 调整日报格式

只需编辑 `templates/report-template.md`，保存后下次生成即生效。无需改代码。

模板支持的变量：`{{日期}}`、`{{greeting}}`、`{{name}}`、`{{company}}`、`{{department}}`、`{{phone}}`、`{{email}}`、`{{#each projects}}`、`{{#each plans}}`、`{{#each milestones}}`。

---

## 常见问题

**MCP 工具无法调用**  
运行 `claude mcp list` 确认 `daily-report` 状态为 enabled；若为 disabled，检查 Python 路径是否正确。

**邮件发送失败**  
QQ 邮箱需在"设置 → 账户"中开启 SMTP 并生成授权码；企业邮箱联系管理员确认 SMTP 地址和端口。

**扫描不到 git 提交**  
检查 `config.json` 中 `paths.work_dir` 是否指向代码根目录，该目录下需包含 `.git` 子目录（或其子目录中有 `.git`）。
