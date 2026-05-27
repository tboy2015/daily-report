---
name: daily-report
description: 自动生成每日工作日报，汇总当天的 git 提交记录和 Claude Code 对话内容，按固定模板生成日报，默认保存到 ~/Documents/daily-reports/YYYY-MM-DD.md 并发送到邮箱，同时输出正文。
user-invocable: true
allowed-tools: [
  "mcp__daily-report__generate_daily_report",
  "mcp__daily-report__get_email_config"
]
---

# 日报生成与发送 Skill

自动生成每日工作日报，从 git 提交记录和 Claude Code 对话记录中提取工作内容，严格按照固定模板生成日报，并默认保存、发送邮件、在对话中输出正文。

---

## 核心原则

### 1. 数据收集范围

- 仅处理当天（00:00 - 23:59）的数据
- 扫描配置文件 `paths.work_dir` 下的所有 git 仓库（默认 `~/work`）
- 扫描配置文件 `paths.projects_dir` 下的当天对话记录（默认 `~/.claude/projects`）

### 2. 模板严格约束

**必须严格按照用户指定模板输出，禁止任何格式改动。**

模板文件位置：`templates/report-template.md`（相对于 skill 目录）

### 3. 默认输出方式

- 默认调用 `generate_daily_report(date, send_email=true)`，由 MCP 内部完成采集、生成、保存、发送邮件，然后在对话中输出返回的日报正文
- 只有用户明确说“不发送”“仅生成”“只输出”时，才不调用发送工具
- 绝对禁止为了采集数据而使用 Bash、shell、终端命令、数组、`cd`、管道、`grep`、`head`、`sort`、`git log` 等外部命令；必须使用 daily-report MCP 工具
- 绝对禁止读取或解析 Claude Code 的 tool-results 文件、`/tmp` 临时文件、MCP 结果落盘文件；MCP 工具返回值已经在上下文中，必须直接基于返回文本归纳
- 绝对禁止为了统计行数、提交数、文件数而调用 `jq`、`wc`、`sed`、`tail`、`awk`、`cat`、`python` 等命令；需要数量时只能从 MCP 返回文本中粗略归纳，日报不需要精确到文件总数
- 若 MCP 工具不可用，直接告知用户“daily-report MCP 工具不可用”，不要退回 Bash 方案

---

## 工作流程

### Step 1: 一键收集当天数据

必须调用 daily-report MCP 工具：

1. 默认只调用 `generate_daily_report(date, send_email=true)`：一键生成、保存、发送并返回日报正文
2. 只有用户明确要求排查数据源时，才调用 `get_email_config` 或其他诊断工具

不要使用 Bash 手写扫描命令。MCP 工具内部会递归扫描配置文件指定的工作目录下所有 git 仓库，并读取配置文件指定的 projects 目录下当天对话记录。

### Step 2: 识别有效工作内容

`generate_daily_report` 会在 MCP 内部参考：

- git commit message
- git changed files
- Claude Code 用户需求、修改指令、测试反馈
- 仓库路径、模块路径、文件名

直接输出 `generate_daily_report` 返回的日报正文和保存/发送状态，不要再做二次分析。日报追求“精简且不缺主要事项”，不要输出类似“4670 个文件、1106 个 Java 文件”这类机械统计。

### Step 3: 合并并归纳工作内容

**按项目分组**，将同一仓库的 git 提交和同一工作目录的对话记录合并。

项目名称必须使用中文业务名，不使用英文仓库名。若 MCP 返回类似 `中文名（repo）`，日报中只写中文名；若没有明确映射，再用“中文名（英文仓库名）”兜底。

常用项目名映射：

| 英文仓库/简称 | 日报项目名称 |
|--------------|-------------|
| anbp / ANBP | 成就中心 |
| achievement-center-console-dev | 成就中心 |
| platform-management-ui | 平台管理 |
| allinone | 全网诉求与资源管理中心 |
| iot | 物联网平台 |
| IoT-Threat-Capture-Monitoring-Alerting | 物联网威胁监测告警平台 |
| IoT-Threat-Capture-Monitoring-Alerting-front | 物联网威胁监测告警平台 |
| dms-project | DMS 项目 |
| dw-production-command-center | 数字化生产指挥中心 |
| ipd-pm-platform | IPD 项目管理平台 |
| dm-mcp-server | 达梦 MCP 工具 |
| mysql2dm-spring-boot-starter | MySQL 转达梦适配组件 |

对每个项目，按工作类型分类归纳（根据变更文件路径、commit message、对话内容推断）：

| 分类标识 | 判断依据 |
|---------|---------|
| 后端开发 | 变更文件在 `src/main/java/`、`service/`、`mapper/`、`controller/`、`entity/`、`dto/` 等目录；或 commit message 含"接口"、"服务"、"Mapper"、"数据库"等 |
| 前端开发 | 变更文件在 `src/main/resources/static/`、`src/views/`、`src/components/`、`*.vue`、`.tsx`、`.jsx` 等；或 commit message 含"页面"、"组件"、"UI"、"样式"等 |
| 开发工具 | commit message 或对话含"MCP"、"脚本"、"工具"、"配置"、"环境"、"IDE"等 |
| 文档整理 | 变更文件为 `*.md`、`*.txt`、`README`、文档类 |
| 问题修复 | commit message 含"fix"、"修复"、"bug"、"解决"等 |
| 其他 | 无法归类的统一放此项 |

**每个分类 bullet 的写法要求：**
- 必须明确：做了什么（动作）+ 做在哪（模块）+ 达成结果
- 禁止模糊表述："进行了相关工作"、"完成了一些任务"
- 推荐表述："完成 XXX 模块开发"、"修复 XXX bug"、"优化 XXX 逻辑"
- 精简但不遗漏：优先合并同一功能链路中的前端、后端、配置、测试、修复内容；不要只写最后一次提交或最后一个对话
- 对同一项目建议输出 2-5 条分类 bullet，覆盖主要工作面；若内容很多，按”功能开发 / 前端开发 / 后端开发 / 配置与联调 / 问题修复”合并

### 工作内容详细化说明

从 2026年05月07日 开始，日报的工作内容采用详细化格式：

**功能开发和前端开发工作项** 现在会展开为多行描述，包含以下维度：
- 功能概括：完成的具体功能或模块
- 实现方式：采用的技术方案和架构
- 技术栈：涉及的主要技术和框架
- 核心逻辑：关键的业务逻辑和处理方式
- 代码量：新增或修改的代码行数（~表示近似值）

**其他工作类型**（配置更新、问题修复、文档整理等）仍保持简洁的单行格式，简明扼要地说明工作内容。

这样的改进让工作日报既能展示关键工作的深度和复杂度，又不会使日报篇幅过长。参考示例见 `examples/sample-report-enriched.md`。

### Step 4: 推导明日工作计划

根据今日工作内容，为每个活跃项目推导明日计划：

| 今日工作类型 | 明日计划推导 |
|-------------|-------------|
| 功能开发中 | 继续完成功能开发，进行单元测试 |
| 功能开发完成 | 功能测试、代码审查、文档编写 |
| Bug 修复 | 验证修复结果、回归测试 |
| 环境搭建/初始化 | 开始核心功能开发 |
| 设计/调研 | 开始具体实现 |

明日工作计划输出为**统一列表**（不按项目分组）。

### Step 5: 推导重点项目里程碑

根据项目进展判断：

| 阶段 | 范围 | 判断依据 |
|-----|------|---------|
| 启动阶段 | 0-30% | 配置、初始化、调研 |
| 开发阶段 | 30-70% | 核心功能开发中 |
| 测试阶段 | 70-90% | 测试、Bug修复、优化 |
| 交付阶段 | 90-100% | 文档、审查、部署 |

里程碑信息输出为**统一列表**（不按项目编号），格式：
- `项目名 - 模块名：阶段（百分比%）`
- `已完成：具体完成情况`
- `下一步：即将开展的工作`
- `风险点：潜在风险或需关注事项`

### Step 6: 生成、保存、发送并输出日报

严格按照 `~/.claude/skills/daily-report/templates/report-template.md` 中的模板生成。

默认调用 `generate_daily_report(date, send_email=true)` 保存到 `~/Documents/daily-reports/YYYY-MM-DD.md` 并发送邮件，然后直接在对话中输出完整日报正文。

只有用户明确要求不发送时，调用 `generate_daily_report(date, send_email=false)`，跳过邮件发送。

**若当天无任何提交和对话记录，生成一份空模板，工作内容部分填写"当日无记录"。**

### 模板约束规则（必须严格遵守）

1. **分隔线固定**：头部和尾部使用 `-----------------------------------`（35个连字符），禁止使用 `---`
2. **日期格式**：使用中文日期，如 `2026年04月21日`，月份和日期不足两位补零
3. **今日工作内容**：每个项目独立成组，按 `1、项目名称：xxx` 编号，项目名必须使用中文业务名，项目下按工作类型分 bullet
4. **明日工作计划**：统一列表，每项以 `· ` 开头，不按项目分组编号
5. **重点项目里程碑**：统一列表，格式固定为 `项目 - 模块：阶段（百分比）`，然后是 `已完成`、`下一步`、`风险点`
6. **无内容占位**：若某天无记录，对应位置填写"当日无记录"或"暂无"，禁止删除章节
7. **落款固定**：必须包含公司名称、部门、姓名、电话、邮箱，每项独立一行
8. **禁止增减章节**：必须包含「日报日期」「今日工作内容」「明日（下周）工作计划」「重点项目里程碑情况」四大章节

---

## 邮件发送

默认发送邮件，调用 `generate_daily_report(date, send_email=true)`。

若配置文件不存在，提示用户先配置邮件信息。

---

## 使用方式

### 新机器初始化（首次使用必做）

```bash
cp config.example.json config.json
# 编辑 config.json，填写姓名、公司、邮箱 SMTP 信息、代码目录路径
```

`config.json` 已加入 `.gitignore`，不会被提交。

### 基本用法

```
/daily-report
```

### 默认：保存并发送邮件

```
/daily-report
```

生成日报正文，保存文件，发送邮件，并输出正文。

### 仅生成不发送

```
/daily-report 不发送邮件
```

### 配置邮件信息

```
/daily-report config
```

---

## 实现逻辑

```
1. 确定日期范围（当天 00:00 - 23:59）
2. 扫描 config.paths.work_dir 下所有 git 仓库当天提交
3. 扫描 config.paths.projects_dir 下当天对话记录
4. 按项目分组，按工作类型分类归纳
5. 推导明日工作计划（统一列表）
6. 推导重点项目里程碑（统一列表）
7. 按强制模板填充日报正文
8. 默认调用 generate_daily_report 保存并发送邮件
9. 在对话中输出完整日报正文
```
