# 日报工作内容详细化优化 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展日报中"功能开发"和"前端开发"工作项的描述，从技术细节、实现方式、技术栈、代码量等多个维度展现工作内容。

**Architecture:** 通过两个主要步骤实现：(1) 更新日报模板，为功能开发和前端开发设计多行展开格式；(2) 修改 MCP 服务的内容生成逻辑，增强从 git 和对话记录中提取工作细节的能力。

**Tech Stack:** Python 3, MCP (FastMCP), Handlebars 模板语言, 正则表达式

---

## 文件结构

### 需要修改的文件

1. **templates/report-template.md**
   - 当前：功能开发和前端开发为单行简洁描述
   - 修改：扩展为多行展开格式，包含实现方式、技术栈、代码量等子项
   - 影响：所有新生成的日报都会采用新格式

2. **scripts/mcp-server.py**
   - 当前：工作类型识别和内容提取都较为简洁
   - 修改：增强对功能开发和前端开发的工作细节提取
   - 影响：MCP 返回的日报数据会更丰富

### 相关的参考文件（不修改）

- examples/sample-report.md - 示例日报（参考用）
- output/daily-reports/2026-05-06.md - 最近一份日报（参考用）

---

## 实现任务

### Task 1: 更新日报模板文件

**Files:**
- Modify: `templates/report-template.md`

**背景:** 当前模板对功能开发和前端开发只有单行描述。需要扩展为支持多行展开，包含子项（功能概括、实现方式、技术栈、核心逻辑/功能、代码量等）。

- [ ] **Step 1: 读取当前模板文件，理解结构**

查看 `templates/report-template.md` 的完整内容，确认当前的 Handlebars 模板结构。

预期：理解当前如何通过 `{{#each categories}}` 遍历工作类型和 `{{category}}`、`{{description}}` 来渲染。

- [ ] **Step 2: 设计新的功能开发模板片段**

设计新的 Handlebars 片段，用于渲染功能开发工作项（多行展开）。新模板结构应包含：
- 功能概括
- 实现方式
- 技术栈
- 核心逻辑（或关键特性）
- 代码量信息

当前数据结构可能是：
```javascript
{
  category: "功能开发",
  description: "..."
}
```

新数据结构应该扩展为：
```javascript
{
  category: "功能开发",
  details: {
    summary: "完成 XXX 功能开发",
    approach: "基于 XXX 技术方案",
    techStack: "使用 XXX 框架和库",
    logic: "实现了 XXX 调用链",
    codeMetrics: "新增 X 个接口，修改 ~Y 行代码"
  }
}
```

或者用一个数组来存储多个子项：
```javascript
{
  category: "功能开发",
  items: [
    "完成 XXX 功能开发",
    "后端设计下载任务队列机制...",
    "前端集成文件流管理...",
    ...
  ]
}
```

**选择方案：** 使用数组方案，更灵活。每个 item 是一条子描述。

- [ ] **Step 3: 同样设计前端开发模板片段**

前端开发也需要扩展，包含：
- 功能概括
- 技术方案（框架版本、架构模式）
- 核心功能（交互、UX、视觉）
- 受影响的组件/文件
- 代码量

采用同样的数组方案。

- [ ] **Step 4: 修改 report-template.md**

使用 Handlebars 条件语句，判断 category 是否为"功能开发"或"前端开发"，如果是，则用新的多行展开格式渲染 items 数组；否则，保持原有的单行格式。

示例（Handlebars 语法）：
```handlebars
{{#each projects}}
{{index}}、项目名称：{{name}}
{{#each categories}}

{{#if (eq category "功能开发")}}
· 功能开发：
{{#each items}}
  - {{this}}
{{/each}}
{{else if (eq category "前端开发")}}
· 前端开发：
{{#each items}}
  - {{this}}
{{/each}}
{{else}}
· {{category}}：{{description}}
{{/if}}

{{/each}}
{{/each}}
```

注意：Handlebars 默认不支持 `eq` 帮助函数，需要在 MCP 服务中注册该帮助函数（参考 Task 2）。

完成后，验证语法正确（可以用文本检查）。

- [ ] **Step 5: Commit**

```bash
git add templates/report-template.md
git commit -m "refactor: expand template for detailed development work items"
```

---

### Task 2: 增强 MCP 服务的工作类型识别和内容提取

**Files:**
- Modify: `scripts/mcp-server.py`
- Test: 手动验证生成的日报数据结构

**背景:** MCP 服务需要识别工作类型，并为功能开发和前端开发生成更详细的内容。当前可能只有简洁的 category 和 description，需要扩展为包含 items 数组。

- [ ] **Step 1: 在 mcp-server.py 中注册 Handlebars eq 帮助函数**

在 MCP 服务中，需要一个 eq 帮助函数来支持 Handlebars 的条件判断。

添加代码（在 mcp-server.py 中适当位置）：

```python
def register_template_helpers():
    """注册 Handlebars 帮助函数"""
    # 为了支持 Handlebars 中的条件判断 {{#if (eq category "功能开发")}}
    # 这里需要在模板引擎中注册 eq 帮助函数
    # 如果使用 Jinja2 或其他模板引擎，注册方式会不同
    pass
```

**注意:** 需要确认当前使用的模板引擎（Handlebars / Jinja2 / 其他）。查看 mcp-server.py 中的模板渲染代码，确定注册方式。

如果当前使用的是 Python 的 Jinja2，则注册方式为：
```python
from jinja2 import Environment

env = Environment()
env.filters['eq'] = lambda a, b: a == b
```

或者使用 Handlebars 的 Python 实现（pybars3）：
```python
from pybars import Compiler

compiler = Compiler()

def register_helpers(handlebars):
    @handlebars.register_helper
    def eq(context, lhs, rhs):
        return lhs == rhs
```

- [ ] **Step 2: 识别当前的工作类型分类逻辑**

在 mcp-server.py 中找到工作类型识别的代码。通常会根据 commit message 或 changed files 来判断：
- "功能开发" - commit message 含"功能"、"开发"或 changed files 在某些目录（如 service、controller）
- "前端开发" - commit message 含"页面"、"组件"或 changed files 为 .vue、.tsx、.jsx
- 等等

找到该部分代码，记录下来。

预期找到的代码片段类似：
```python
def categorize_work(commit_message, changed_files):
    if any(kw in commit_message for kw in ["页面", "组件", "UI"]):
        return "前端开发"
    elif any(kw in commit_message for kw in ["功能", "接口", "服务"]):
        return "功能开发"
    # ...
```

- [ ] **Step 3: 增强内容提取函数，支持详细信息**

创建一个新的函数 `extract_detailed_work_items()`，用于从 git commit 和对话记录中提取详细的工作信息。

该函数应：
- 输入：commit 信息、changed files 列表、对话内容
- 输出：一个结构化的对象，包含 category、items（数组）
- items 中的每条信息应该包含：实现方式、技术栈、核心逻辑、代码量等

示例伪代码：

```python
def extract_detailed_work_items(commits, changed_files, conversations):
    """
    从 commit、changed files 和对话中提取详细工作内容
    
    Args:
        commits: [{"message": "...", "files": [...]}]
        changed_files: ["src/main/java/...", "src/views/..."]
        conversations: "对话内容文本"
    
    Returns:
        {
            "功能开发": [
                "完成 XXX 功能开发",
                "后端设计下载任务队列机制，基于 Spring Task...",
                "实现了 XXX 调用链",
                "新增 5 个接口，修改 ~600 行代码"
            ],
            "前端开发": [
                "完成 XXX 页面/组件开发",
                "使用 Vue 3 + TypeScript 重构...",
                ...
            ]
        }
    """
    result = {}
    
    # 1. 识别工作类型
    category = identify_category(commits, changed_files)
    
    # 2. 从 commit message 提取功能概括
    summary = extract_summary_from_commits(commits)
    
    # 3. 从 changed files 和对话内容提取技术细节
    tech_details = extract_tech_details(changed_files, conversations)
    
    # 4. 估算代码量
    code_metrics = estimate_code_metrics(changed_files)
    
    # 5. 组装为 items 数组
    items = [
        summary,
        tech_details["approach"],
        tech_details["tech_stack"],
        tech_details["logic"],
        code_metrics
    ]
    
    result[category] = items
    
    return result
```

- [ ] **Step 4: 实现 extract_summary_from_commits() 函数**

该函数从 commit message 中提取一句话的功能概括。

实现思路：
- 获取当天所有相关 commit 的 message
- 合并成一句话，提取主要功能关键词
- 格式化为"完成 XXX 功能开发"或"完成 XXX 页面更新"

示例代码：

```python
def extract_summary_from_commits(commits, category="功能开发"):
    """从 commit message 提取功能概括"""
    if not commits:
        return ""
    
    # 获取第一条和最后一条 commit message 的关键信息
    messages = [c.get("message", "") for c in commits]
    
    # 简单方案：取第一条 message 的第一行
    first_msg = messages[0].split('\n')[0] if messages else ""
    
    # 如果 message 以 "feat:" 开头，提取之后的部分
    if first_msg.startswith("feat:"):
        detail = first_msg.replace("feat:", "").strip()
        return f"完成{detail}开发"
    
    # 否则直接用 message
    return f"完成{first_msg}开发"
```

- [ ] **Step 5: 实现 extract_tech_details() 函数**

该函数从 changed files 和对话内容中提取技术细节。

实现思路：
- 从 changed files 识别技术栈（Java/Vue/Spring等）
- 从对话内容中识别关键技术词汇（如"队列"、"异步"、"组件"等）
- 组装成"实现方式"、"技术栈"、"核心逻辑"等

示例代码：

```python
def extract_tech_details(changed_files, conversations):
    """从 changed files 和对话内容提取技术细节"""
    details = {
        "approach": "",
        "tech_stack": "",
        "logic": ""
    }
    
    # 1. 识别文件类型，推断技术栈
    java_files = [f for f in changed_files if f.endswith('.java')]
    vue_files = [f for f in changed_files if f.endswith('.vue')]
    ts_files = [f for f in changed_files if f.endswith('.ts') or f.endswith('.tsx')]
    
    tech_list = []
    if java_files:
        tech_list.append("Java/Spring")
    if vue_files:
        tech_list.append("Vue")
    if ts_files:
        tech_list.append("TypeScript")
    
    details["tech_stack"] = f"技术栈：{'/'.join(tech_list) if tech_list else '多技术栈'}"
    
    # 2. 从对话内容中提取关键技术词汇
    # 这是一个简化版，实际可能需要更复杂的 NLP
    tech_keywords = {}
    if any(kw in conversations for kw in ["队列", "异步", "并发"]):
        tech_keywords["approach"] = "设计了队列/异步处理机制"
    
    if tech_keywords.get("approach"):
        details["approach"] = tech_keywords["approach"]
    
    # 3. 推导核心逻辑（这需要对话内容的解析）
    # 简化版：如果有"调用链"、"流程"等词，提取之
    if "调用链" in conversations:
        # 从对话中提取"调用链"后面的内容
        import re
        match = re.search(r"调用链[：:]\s*(.+?)(?:\n|$)", conversations, re.DOTALL)
        if match:
            chain = match.group(1).strip()
            details["logic"] = f"实现了{chain}调用链"
    
    return details
```

- [ ] **Step 6: 实现 estimate_code_metrics() 函数**

该函数估算代码量。

实现思路：
- 统计 changed files 的数量
- 使用 git diff --stat 或类似方法，估算新增/修改的行数
- 格式化为"新增 X 个接口/文件，修改 ~Y 行代码"

示例代码：

```python
def estimate_code_metrics(changed_files, repo_path=None):
    """估算代码量指标"""
    if not changed_files:
        return ""
    
    # 1. 统计文件数
    java_count = len([f for f in changed_files if f.endswith('.java')])
    vue_count = len([f for f in changed_files if f.endswith('.vue')])
    ts_count = len([f for f in changed_files if f.endswith('.ts') or f.endswith('.tsx')])
    
    total_files = len(changed_files)
    
    # 2. 简单估算行数（这需要实际 git diff 数据）
    # 这里先使用占位符，实际需要从 git diff --stat 获取
    estimated_lines = total_files * 50  # 每个文件平均 50 行改动
    
    # 3. 组装指标字符串
    metrics = f"涉及 {total_files} 个文件，新增/修改 ~{estimated_lines} 行代码"
    
    if java_count > 0:
        metrics += f"（Java 文件 {java_count} 个）"
    
    return metrics
```

- [ ] **Step 7: 修改 generate_daily_report() 函数**

找到 MCP 中生成日报的主函数（通常名为 `generate_daily_report` 或类似），修改其调用逻辑：

当前可能是：
```python
categories = categorize_work(commits, changed_files)
# 返回 {"category": "功能开发", "description": "..."}
```

修改为：
```python
# 对于功能开发和前端开发，调用增强版提取函数
if category in ["功能开发", "前端开发"]:
    detailed_items = extract_detailed_work_items(commits, changed_files, conversations)
    # 返回 {"category": "功能开发", "items": [...]}
else:
    # 保持现有的简洁格式
    description = categorize_work(commits, changed_files)
    # 返回 {"category": "...", "description": "..."}
```

- [ ] **Step 8: Commit**

```bash
git add scripts/mcp-server.py
git commit -m "feat: enhance work type detection and add detailed content extraction for development items"
```

---

### Task 3: 验证和测试

**Files:**
- Reference: `templates/report-template.md`
- Reference: `scripts/mcp-server.py`
- Test: 手动生成一份日报，验证输出格式

- [ ] **Step 1: 手动调用 MCP 生成一份测试日报**

运行命令（确保 MCP 服务已启动）：

```bash
# 在项目目录下，调用 generate_daily_report
python scripts/mcp-server.py
# 或通过 Claude Code 的 daily-report MCP 工具调用
```

预期：返回一份新格式的日报，功能开发和前端开发部分应该展开为多行。

- [ ] **Step 2: 验证模板渲染正确**

检查生成的日报：
- 是否有"二、今日工作内容"部分
- 是否正确展开了功能开发和前端开发
- 是否保留了其他工作类型的简洁格式
- 是否没有模板语法错误（如未渲染的 `{{}}` 符号）

- [ ] **Step 3: 验证数据结构正确**

检查 MCP 返回的 JSON 数据：
- 功能开发是否为 `{"category": "功能开发", "items": [...]}`
- 前端开发是否为 `{"category": "前端开发", "items": [...]}`
- items 数组中是否有 5-6 条子项（概括、方案、技术栈、逻辑/功能、代码量、其他）

- [ ] **Step 4: 检查边界情况**

- 如果某天只有功能开发没有前端开发，日报是否正确
- 如果没有功能开发和前端开发，日报是否降级为简洁格式
- 如果对话内容不足以提取细节，是否有合理的默认值

- [ ] **Step 5: Commit**

```bash
# 如果有测试用例或验证脚本，也要 commit
# git add tests/ (如有)
git commit -m "test: verify daily report enrichment output format and data structure"
```

---

### Task 4: 更新文档和示例

**Files:**
- Create/Modify: `examples/sample-report.md`（更新示例）
- Modify: `SKILL.md`（更新说明，如需）

- [ ] **Step 1: 生成新的示例日报**

基于新的模板和增强的内容提取，生成一份示例日报，保存到 `examples/sample-report-enriched.md`。

示例内容应该展示：
- 功能开发的详细格式（多行展开）
- 前端开发的详细格式（多行展开）
- 其他工作类型的简洁格式（保持不变）

示例日报大概像这样：

```markdown
各位领导：

以下为南网业务处唐标2026年05月07日工作日报，烦请领导查收指正。

-----------------------------------

一、日报日期：2026年05月07日

二、今日工作内容：

1、项目名称：成就中心

· 功能开发：
  - 完成组件文档批量下载功能核心开发
  - 后端设计下载任务队列机制，基于 Spring Task 实现异步处理，支持多文件并发下载
  - 前端集成文件流管理，使用 Blob + FormData 处理二进制数据传输
  - 贯通的三层调用链：业务页面（组件选择器）→ 文档服务（文件收集与记录）→ 下载管理模块（队列与传输）
  - 涉及 14 个文件，新增/修改 ~600 行代码

· 前端开发：
  - 更新业务页面组件和下载功能的交互逻辑
  - 使用 Vue 3 + TypeScript，基于 Composition API 重构下载选择器组件
  - 实现文件列表树形展示、多选操作、实时进度反馈，支持拖拽排序
  - 修改 6 个前端组件，新增下载管理 UI 模块、状态管理 store
  - 涉及 8 个文件，新增/修改 ~420 行代码
  - 集成进度条、错误提示、重试机制的用户交互反馈

· 配置更新：同步前后端依赖、构建配置和运行参数，保障功能开发后的编译与部署一致性

三、明日（下周）工作计划：
· 开展当日开发功能的单元测试、联调测试和回归验证
· 验证前后端交互逻辑、异常处理和部署配置的正确性
· 根据测试反馈修复问题，优化用户交互体验和性能表现
· 完成代码审查，补充必要的接口说明和交付文档

四、重点项目里程碑情况：
· 成就中心 - 组件文档模块：开发阶段（60%）
· 已完成：完成组件文档批量下载功能核心开发、更新前端 API、页面组件和交互逻辑
· 下一步：功能测试、Bug 修复、代码审查和用户反馈优化
· 风险点：跨模块文件操作的性能和稳定性需进一步验证

-----------------------------------
山东浪潮数字服务有限公司
交通服务事业部 - 南网业务处
唐标
Tel: 13707490673
E-mail: tangbiao@inspur.com
2026年05月07日
```

- [ ] **Step 2: 更新 SKILL.md 中的说明（如需）**

检查 `SKILL.md` 是否需要更新关于工作内容描述的说明。如果有关于"工作内容如何生成"的部分，可以添加说明：

> 工作内容中，"功能开发"和"前端开发"会自动展开为多行详细描述，包含实现方式、技术栈、代码量等信息。其他工作类型保持简洁格式。

- [ ] **Step 3: Commit**

```bash
git add examples/sample-report-enriched.md SKILL.md
git commit -m "docs: add enriched sample report and update skill documentation"
```

---

### Task 5: 集成测试和上线准备

**Files:**
- Reference: `output/daily-reports/`（存放生成的日报）
- Modify: `SKILL.md`（更新使用说明，如需）

- [ ] **Step 1: 生成 2-3 份真实日报进行集成测试**

在实际使用中（或通过模拟数据）生成 2-3 份日报，验证整个流程的正确性：
- git 数据采集正确
- 工作类型识别准确
- 内容提取详细度合理
- 模板渲染无误
- 文件保存成功

运行命令（根据实际 MCP 调用方式）：

```bash
# 假设通过 Claude Code 的 daily-report 技能调用
/daily-report
# 或手动运行 MCP 服务测试
python scripts/mcp-server.py
```

预期：生成的日报文件保存在 `output/daily-reports/` 中，格式正确，功能开发和前端开发部分展开详细。

- [ ] **Step 2: 人工审查生成的日报质量**

阅读生成的日报，评估：
- 工作内容描述是否更清楚、更有价值
- 技术细节是否准确和有意义
- 篇幅是否合理（30-50% 增长）
- 是否有冗余或不必要的信息

根据实际情况，可能需要微调内容提取逻辑。

- [ ] **Step 3: Commit 所有文件**

```bash
git add output/daily-reports/ (新生成的日报)
git commit -m "test: add integration test reports with enriched format"
```

- [ ] **Step 4: 准备上线清单**

确认以下内容已完成：
- [x] 模板更新 (Task 1)
- [x] MCP 服务增强 (Task 2)
- [x] 验证测试 (Task 3)
- [x] 文档示例更新 (Task 4)
- [x] 集成测试 (Task 5)
- [x] 无 merge conflicts
- [x] 所有 commit 信息清晰

---

## 总结

本实现计划分为 5 个主要阶段：

1. **Task 1**: 更新日报模板，为功能开发和前端开发设计多行展开格式
2. **Task 2**: 增强 MCP 服务的工作类型识别和内容提取能力
3. **Task 3**: 验证和测试新的日报格式和数据结构
4. **Task 4**: 更新文档和示例
5. **Task 5**: 集成测试和上线准备

完成后，日报的"功能开发"和"前端开发"工作项将包含更多技术细节，便于领导和相关方理解实际完成的技术工作。

