# 新电脑部署指南

## 前置条件

- [Claude Code](https://claude.ai/code) 已安装并登录
- Python 3.10+（见下方安装说明）
- Git

---

## 步骤一：克隆仓库

将仓库放到 `~/.claude/skills/` 下，Claude Code 可以直接识别：

```bash
# macOS / Linux
git clone <repo-url> ~/.claude/skills/daily-report

# Windows（PowerShell）
git clone <repo-url> "$env:USERPROFILE\.claude\skills\daily-report"
```

---

## 步骤二：安装 Python 依赖

有两种方式，推荐 **方案 A（uv）**，更轻量，不需要提前安装 Python。

---

### 方案 A：uv（推荐）

uv 是一个独立的 Python 包管理器，自带 Python 运行时，无需手动安装 Python。

**安装 uv：**

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装完后重新打开终端，无需额外操作，uv 会在运行时自动下载依赖。

> 步骤四注册 MCP 时需使用对应的 uv 命令，见下方说明。

---

### 方案 B：pip（已有 Python）

**先确认 Python 可用：**

```
# macOS / Linux
python3 --version

# Windows
py --version
```

如果提示"命令未找到"或打开了 Microsoft Store，说明 Python 未安装。  
前往 `https://www.python.org/downloads/` 下载安装，**安装时必须勾选 "Add python.exe to PATH"**，然后重新打开终端。

**安装依赖：**

```bash
# macOS / Linux
python3 -m pip install mcp

# Windows
py -m pip install mcp
```

---

## 步骤三：填写配置文件

```bash
# macOS / Linux
cp config.example.json config.json

# Windows（PowerShell）
Copy-Item config.example.json config.json
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

**Windows 路径写法：** JSON 中反斜杠需转义，推荐直接用正斜杠：
```json
"work_dir": "C:/Users/你的用户名/work/code"
```
> ⚠️ 不能写 `"C:\Users\..."` —— 单反斜杠在 JSON 里是非法转义符，会导致整个配置文件解析失败、所有配置项失效。

**自定义项目中文名**（可选）：将仓库目录名映射为业务名：

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

**方案 A（uv）：**

```bash
# macOS / Linux
claude mcp add daily-report --scope user -- uv run ~/.claude/skills/daily-report/scripts/mcp-server.py

# Windows（cmd/PowerShell）—— 用硬编码路径，不要用 $env: 变量
claude mcp add daily-report --scope user -- uv run "C:\Users\你的用户名\.claude\skills\daily-report\scripts\mcp-server.py"
```

**方案 B（pip）：**

```bash
# macOS / Linux
claude mcp add daily-report --scope user -- python3 ~/.claude/skills/daily-report/scripts/mcp-server.py

# Windows（cmd/PowerShell）—— 用硬编码路径，不要用 $env: 变量
claude mcp add daily-report --scope user -- py "C:\Users\你的用户名\.claude\skills\daily-report\scripts\mcp-server.py"
```

> **Windows 注意：** 必须用硬编码的绝对路径，`$env:USERPROFILE` 只在 PowerShell 脚本中展开，直接传给 `claude` 命令时不会展开，会导致服务器启动失败。
>
> **`--scope user` 说明：** 不加此参数默认注册到当前项目目录，只有在该目录下才生效。`--scope user` 让它全局可用。

验证注册成功：

```bash
claude mcp list
```

输出中出现 `daily-report` 即可。

---

## 步骤五：注册 Skill

```bash
# macOS / Linux
cp ~/.claude/skills/daily-report/SKILL.md ~/.claude/skills/daily-report.md

# Windows（cmd）
copy "C:\Users\你的用户名\.claude\skills\daily-report\SKILL.md" "C:\Users\你的用户名\.claude\skills\daily-report.md"
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

只需编辑 `templates/report-template.md`，保存后下次生成即生效，无需改代码。

模板支持的变量：`{{日期}}`、`{{greeting}}`、`{{name}}`、`{{company}}`、`{{department}}`、`{{phone}}`、`{{email}}`、`{{#each projects}}`、`{{#each plans}}`、`{{#each milestones}}`。

---

## 常见问题

**`pip` 不是内部命令**  
用 `py -m pip install mcp`（Windows）或 `python3 -m pip install mcp`（macOS/Linux）代替。

**`py` 也找不到**  
Python 未安装，参考步骤二中的"安装 Python"。

**MCP 工具无法调用**  
运行 `claude mcp list` 确认 `daily-report` 状态为 enabled；若为 disabled，检查 Python 路径是否正确，可用 `py scripts/mcp-server.py` 手动运行看报什么错。

**Windows 上 MCP 服务器路径错误**  
注册时不要用 `$env:USERPROFILE`，它不会在命令行中展开。用完整的绝对路径，如 `C:\Users\theo\.claude\skills\daily-report\scripts\mcp-server.py`。

**MCP 只在某个目录下生效**  
注册时漏了 `--scope user`，导致只注册到了项目级配置。重新运行注册命令并加上 `--scope user`。

**邮件发送失败**  
QQ 邮箱需在"设置 → 账户"中开启 SMTP 并生成授权码（非登录密码）；企业邮箱联系管理员确认 SMTP 地址和端口。

**扫描不到 git 提交**  
检查 `config.json` 中 `paths.work_dir` 是否指向代码根目录，该目录下需包含 `.git` 子目录（或其子目录中有 `.git`）。
