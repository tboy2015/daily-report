#!/usr/bin/env python3
"""
Daily Report MCP Server
提供日报生成所需的工具：收集 git 提交、收集对话记录、保存日报、发送邮件
"""

import json
import os
import re
import subprocess
import glob
import sys
import io
import contextlib
from datetime import datetime
from typing import List, Dict, Optional, Any

from mcp.server.fastmcp import FastMCP

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from mailer import load_config, send_daily_report

mcp = FastMCP("daily-report")

CONFIG_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.json"))

# 内置兜底项目名映射（用户可在配置文件的 project_name_map 中覆盖或扩展）
_BUILTIN_PROJECT_NAME_MAP = {
    "anbp": "研发平台-成果中心",
    "ANBP": "研发平台-成果中心",
    "achievement-center-console-dev": "研发平台-成果中心",
    "platform-management-ui": "研发平台-门户管理",
    "allinone": "一体化项目",
    "iot": "物联网威胁监测告警平台",
    "IoT-Threat-Capture-Monitoring-Alerting": "物联网威胁监测告警平台",
    "IoT-Threat-Capture-Monitoring-Alerting-front": "物联网威胁监测告警平台",
    "dms-project": "DMS 项目",
    "dw-production-command-center": "数字化生产指挥中心",
    "ipd-pm-platform": "研发平台-IPD 项目协同",
    "dm-mcp-server": "达梦 MCP 工具",
    "mysql2dm-spring-boot-starter": "MySQL 转达梦适配组件",
}


def _load_config() -> dict:
    """加载配置文件，返回合并后的配置字典。"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_work_dir() -> str:
    cfg = _load_config()
    raw = cfg.get("paths", {}).get("work_dir") or os.environ.get("DAILY_WORK_DIR", "")
    return os.path.expanduser(raw) if raw else os.path.expanduser("~/work")


def _get_projects_dir() -> str:
    cfg = _load_config()
    raw = cfg.get("paths", {}).get("projects_dir") or ""
    return os.path.expanduser(raw) if raw else os.path.expanduser("~/.claude/projects")


def _get_user_info() -> dict:
    cfg = _load_config()
    u = cfg.get("user", {})
    return {
        "name": u.get("name", "日报"),
        "greeting": u.get("greeting") or u.get("name", ""),
        "company": u.get("company", ""),
        "department": u.get("department", ""),
        "phone": u.get("phone", ""),
        "email": u.get("email", ""),
    }


def _get_project_name_map() -> dict:
    cfg = _load_config()
    merged = dict(_BUILTIN_PROJECT_NAME_MAP)
    merged.update(cfg.get("project_name_map", {}))
    return merged



def _run_git_command(repo_path, cmd):
    """在指定仓库运行 git 命令"""
    try:
        if isinstance(cmd, list) and cmd and cmd[0] == "git":
            cmd = ["git", "-c", "core.quotepath=false", *cmd[1:]]
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def _display_project_name(name: str) -> str:
    """返回日报中使用的中文项目名。"""
    if not name:
        return "未命名项目"

    normalized = name.strip()

    # 剥离工作目录前缀（路径转连字符形式）
    work_dir = _get_work_dir()
    work_prefix = work_dir.lstrip("/").replace("/", "-")
    if normalized.startswith("-" + work_prefix + "-"):
        normalized = normalized[len(work_prefix) + 2:]
    elif normalized.startswith(work_prefix + "-"):
        normalized = normalized[len(work_prefix) + 1:]

    pmap = _get_project_name_map()

    if normalized in pmap:
        return pmap[normalized]

    lower = normalized.lower()
    if lower in pmap:
        return pmap[lower]

    for key, value in pmap.items():
        if key.lower() in lower:
            return value

    return normalized


def _extract_text(value) -> str:
    """从 Claude JSONL 的多种 content 结构中提取可读文本。"""
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, list):
        parts = []
        for item in value:
            text = _extract_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts)

    if isinstance(value, dict):
        if value.get("type") == "text" and value.get("text"):
            return str(value["text"])
        if value.get("text"):
            return str(value["text"])
        if value.get("content"):
            return _extract_text(value["content"])
        if value.get("message"):
            return _extract_text(value["message"])

    return ""


def _is_effective_user_message(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    ignored_prefixes = (
        "/clear",
        "/help",
        "/exit",
        "/compact",
        "<command-message>",
        "<persisted-output>",
        "Base directory for this skill:",
        "total ",
    )
    if stripped.startswith(ignored_prefixes):
        return False

    ignored_fragments = (
        "<command-name>/daily-report</command-name>",
        "Full output saved to:",
        "工具结果",
        "日报生成与发送 Skill",
        "{{#each projects}}",
    )
    return not any(fragment in stripped for fragment in ignored_fragments)


def _find_git_repos(root_dir: str = None):
    """递归发现工作目录下的 git 仓库。"""
    if root_dir is None:
        root_dir = _get_work_dir()
    repos = []
    if not os.path.exists(root_dir):
        return repos

    for current_dir, dirnames, _ in os.walk(root_dir):
        hidden_or_build_dirs = {
            ".git",
            "node_modules",
            "target",
            "dist",
            "build",
            ".idea",
            ".vscode",
        }
        dirnames[:] = [
            name for name in dirnames
            if name not in hidden_or_build_dirs and not name.startswith(".")
        ]

        git_dir = os.path.join(current_dir, ".git")
        if os.path.isdir(git_dir):
            repo_name = os.path.basename(current_dir)
            repos.append((repo_name, current_dir))
            dirnames[:] = []

    return sorted(repos, key=lambda item: item[1])


def _send_report_email(report_path: str) -> str:
    """直接调用邮件模块发送日报，避免通过 shell 或 python 子进程发送。"""
    try:
        config = load_config()
        with contextlib.redirect_stdout(io.StringIO()):
            send_daily_report(report_path, config)
        recipients = ", ".join(config.get("to_emails", []))
        return f"邮件发送成功: {recipients}"
    except SystemExit as e:
        return f"邮件发送失败: {e}"
    except Exception as e:
        return f"邮件发送失败: {e}"


def _resolve_reports_dir() -> str:
    """
    Resolve a writable reports directory.

    Priority:
    1) Env var DAILY_REPORTS_DIR
    2) Config file paths.reports_dir
    3) Default: output/daily-reports inside the repo
    """
    env_dir = os.environ.get("DAILY_REPORTS_DIR")
    cfg_dir = _load_config().get("paths", {}).get("reports_dir", "")
    candidates = []
    if env_dir:
        candidates.append(env_dir)
    if cfg_dir:
        candidates.append(os.path.expanduser(cfg_dir))
    candidates.append(os.path.abspath(os.path.join(SCRIPT_DIR, "..", "output", "daily-reports")))

    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            test_path = os.path.join(candidate, ".write-test")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_path)
            return candidate
        except Exception:
            continue

    cwd_fallback = os.path.abspath(os.path.join(os.getcwd(), "daily-reports"))
    os.makedirs(cwd_fallback, exist_ok=True)
    return cwd_fallback


def _render_template(text: str, ctx: dict) -> str:
    """轻量模板渲染器，支持三种语法：
    - {{var}}              简单变量替换
    - {{#each list}}...{{/each}}   循环，每项可用 {{field}} 或 {{this}}（标量）
    - {{^var}}...{{/var}}  当 var 为空/假时渲染（inverted section）
    """
    # {{#each key}}...{{/each}}
    each_re = re.compile(r'\{\{#each ([^}]+)\}\}(.*?)\{\{/each\}\}', re.DOTALL)

    def expand_each(m):
        key = m.group(1).strip()
        block = m.group(2)
        items = ctx.get(key) or []
        parts = []
        for item in items:
            child_ctx = {**ctx, **(item if isinstance(item, dict) else {'this': str(item)})}
            parts.append(_render_template(block, child_ctx))
        return ''.join(parts)

    text = each_re.sub(expand_each, text)

    # {{^var}}...{{/var}}
    inv_re = re.compile(r'\{\{\^([^}]+)\}\}(.*?)\{\{/\1\}\}', re.DOTALL)

    def expand_inverted(m):
        key = m.group(1).strip()
        block = m.group(2)
        return _render_template(block, ctx) if not ctx.get(key) else ''

    text = inv_re.sub(expand_inverted, text)

    # {{var}}
    def expand_var(m):
        val = ctx.get(m.group(1).strip())
        return str(val) if val is not None else m.group(0)

    return re.sub(r'\{\{([^#/\^][^}]*)\}\}', expand_var, text)


def _format_cn_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%Y年%m月%d日")


def _repo_activity(repo_name: str, repo_path: str, date_str: str):
    since = f"{date_str} 00:00"
    until = f"{date_str} 23:59"

    # 使用 COMMIT: 分隔符，同时输出 commit 信息和对应文件列表
    raw = _run_git_command(
        repo_path,
        [
            "git",
            "log",
            f"--since={since}",
            f"--until={until}",
            "--format=COMMIT:%H|%s",
            "--name-only",
            "-n",
            "50",
        ],
    )
    if not raw or raw.startswith("ERROR"):
        return None

    # 解析每条 commit 的独立文件列表
    commit_blocks: List[Dict] = []
    current: Optional[Dict] = None
    for line in raw.splitlines():
        if line.startswith("COMMIT:"):
            if current is not None:
                commit_blocks.append(current)
            parts = line[7:].split("|", 1)
            current = {
                "hash": parts[0],
                "subject": parts[1] if len(parts) > 1 else "",
                "files": [],
            }
        elif line.strip() and current is not None:
            current["files"].append(line.strip())
    if current is not None:
        commit_blocks.append(current)

    if not commit_blocks:
        return None

    all_files = sorted({f for c in commit_blocks for f in c["files"]})
    subjects = [c["subject"] for c in commit_blocks]
    return {
        "repo": repo_name,
        "path": repo_path,
        "display_name": _display_project_name(repo_name),
        "subjects": subjects,
        "files": all_files,
        "commit_blocks": commit_blocks,  # 每条 commit 含独立文件列表
    }



def _extract_summary_from_subject(subject: Optional[str]) -> str:
    """从 commit message 提取概括，去除 conventional commit 前缀（含 scope）"""
    if not subject or not isinstance(subject, str):
        return "完成代码调整"
    # 剥离 feat:、fix:、feat(scope):、fix(scope):、feat(scope)!: 等前缀
    cleaned = re.sub(
        r'^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\([^)]*\))?!?:\s*',
        '',
        subject.strip()
    )
    cleaned = cleaned.strip() or subject.strip()
    if len(cleaned) > 50:
        cleaned = cleaned[:50] + "..."
    return cleaned


def _identify_work_type(subjects: Optional[List[str]], files: Optional[List[str]]) -> Dict[str, float]:
    """识别工作类型并返回优先级。

    分类互斥原则：
    - 有明确前端/后端文件时，直接归为前端/后端，不再叠加"功能开发"
    - "配置更新"/"文档整理"仅在没有代码文件时单独出现，否则忽略
    - "问题修复"直接返回，不与其他类型叠加
    - "功能开发"为兜底分类，当无法判断前/后端时使用
    """
    if not subjects or not isinstance(subjects, (list, tuple)):
        subjects = []
    if not files or not isinstance(files, (list, tuple)):
        files = []

    try:
        file_text = "\n".join(str(f) for f in files).lower()
        subject_text = "\n".join(str(s) for s in subjects).lower()
    except Exception:
        return {}

    # 问题修复优先：直接返回，不与其他类型叠加
    if any(kw in subject_text for kw in ["fix", "bug", "修复", "bugfix"]):
        return {"问题修复": 1.0}

    has_java = "src/main/java" in file_text or any(
        str(f).endswith(".java") for f in files if isinstance(f, str)
    )
    has_frontend = any(m in file_text for m in [
        ".vue", ".tsx", ".jsx",
        "src/views/", "src/components/", "src/pages/",
    ])

    # 有代码文件（java 或 前端）时，归为前端/后端，不叠加配置/文档
    if has_java and has_frontend:
        return {"前端开发": 0.9, "后端开发": 0.8}
    if has_frontend:
        return {"前端开发": 0.9}
    if has_java:
        return {"后端开发": 0.8}

    # 无明确代码文件时：先按文件类型判断（配置/文档），再按 commit message 兜底
    config_markers = ["pom.xml", "package.json", "application.yml", "application.properties", "docker-compose"]
    code_files = [f for f in files if isinstance(f, str)
                  and not f.endswith(".md")
                  and not any(m in f for m in config_markers)]

    if not code_files:
        if any(m in file_text for m in config_markers):
            return {"配置更新": 0.7}
        doc_files = [f for f in files if isinstance(f, str) and f.endswith(".md")]
        if doc_files:
            return {"文档整理": 0.5}

    # 从 commit message 推断（有代码文件但不是 java/vue 的情况）
    if any(kw in subject_text for kw in ["页面", "组件", "ui", "frontend", "前端"]):
        return {"前端开发": 0.9}
    if any(kw in subject_text for kw in ["接口", "服务", "后端", "service", "backend"]):
        return {"后端开发": 0.8}

    # 兜底：通用功能开发
    return {"功能开发": 0.7}


def _extract_detailed_work_items(activity: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    逐条 commit 处理，生成工作项。每条 commit 独立确定工作类型和描述，
    避免含 fix 的 commit 污染其他 commit 的分类。

    输出：{ "前端开发": ["描述1", "描述2"], "后端开发": [...], ... }
    """
    if not activity or not isinstance(activity, dict):
        return {}

    commit_blocks = activity.get("commit_blocks")

    # 向后兼容：无 commit_blocks 时降级处理
    if not commit_blocks:
        subjects = activity.get("subjects", [])
        files = activity.get("files", [])
        if not isinstance(subjects, (list, tuple)):
            subjects = []
        if not isinstance(files, (list, tuple)):
            files = []
        commit_blocks = [{"hash": "", "subject": s, "files": files} for s in subjects]

    result: Dict[str, List[str]] = {}

    for commit in commit_blocks:
        subject = commit.get("subject", "")
        files = commit.get("files", [])
        if not isinstance(files, (list, tuple)):
            files = []
        if not subject:
            continue

        # 针对单条 commit 独立判断工作类型，避免 fix 提交影响其他提交的分类
        work_types = _identify_work_type([subject], files)
        if not work_types:
            work_types = {"功能开发": 0.7}
        work_type = max(work_types, key=work_types.get)

        result.setdefault(work_type, []).append(_extract_summary_from_subject(subject))

    return result



def _build_daily_report(date_str: str) -> str:
    cn_date = _format_cn_date(date_str)
    user = _get_user_info()

    activities = []
    for repo_name, repo_path in _find_git_repos():
        activity = _repo_activity(repo_name, repo_path, date_str)
        if activity:
            activities.append(activity)

    # 组装 projects 数据
    projects = []
    for i, activity in enumerate(activities, 1):
        work_items = _extract_detailed_work_items(activity)
        projects.append({
            "index": str(i),
            "name": activity["display_name"],
            "categories": [
                {"category": cat, "items": items}
                for cat, items in work_items.items()
            ],
        })

    defaults = _load_config().get("defaults", {})

    # 组装 plans 数据
    default_plans = defaults.get("plans", [
        "开展当日开发功能的单元测试、联调测试和回归验证",
        "验证前后端交互逻辑、异常处理和部署配置的正确性",
        "根据测试反馈修复问题，优化用户交互体验和性能表现",
        "完成代码审查，补充必要的接口说明和交付文档",
    ])
    plans = [{"plan": p} for p in default_plans] if activities else [{"plan": "暂无"}]

    # 组装 milestones 数据
    primary = activities[0] if activities else None
    if primary:
        cleaned = [_extract_summary_from_subject(s) for s in primary["subjects"][:3] if s]
        completed = "、".join(cleaned) if cleaned else "项目功能开发"
        if len(completed) > 80:
            completed = completed[:80] + "..."
        milestones = [{
            "project": primary["display_name"],
            "module": defaults.get("milestone_module", "核心业务模块"),
            "stage": defaults.get("milestone_stage", "开发阶段"),
            "percent": str(defaults.get("milestone_percent", "50")),
            "completed": completed,
            "next_step": defaults.get("milestone_next_step", "功能测试、Bug 修复、代码审查和用户反馈优化"),
            "risk": defaults.get("milestone_risk", "跨模块文件操作的性能、稳定性和部署环境差异需进一步验证"),
        }]
    else:
        milestones = [{
            "project": "暂无",
            "module": "—",
            "stage": "—",
            "percent": "—",
            "completed": "当日无记录",
            "next_step": "暂无",
            "risk": "暂无",
        }]

    ctx = {
        "日期": cn_date,
        "greeting": user["greeting"] or user["name"],
        "name": user["name"],
        "company": user["company"],
        "department": user["department"],
        "phone": user["phone"],
        "email": user["email"],
        "projects": projects,
        "plans": plans,
        "milestones": milestones,
    }

    template_path = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "templates", "report-template.md"))
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    return _render_template(template, ctx)


def _collect_git(date_str: str) -> str:
    """内部：收集 git 提交"""
    since = f"{date_str} 00:00"
    until = f"{date_str} 23:59"

    repos = _find_git_repos()

    results = []
    for repo_name, repo_path in repos:
        commits = _run_git_command(
            repo_path,
            [
                "git",
                "log",
                f"--since={since}",
                f"--until={until}",
                "--format=%H|%s|%ad",
                "--date=short",
                "-n",
                "50",
            ],
        )
        if commits and not commits.startswith("ERROR") and commits.strip():
            files = _run_git_command(
                repo_path,
                [
                    "git",
                    "log",
                    f"--since={since}",
                    f"--until={until}",
                    "--name-only",
                    "--format=",
                ],
            )
            changed_files = "\n".join(
                sorted({line.strip() for line in files.splitlines() if line.strip()})
            )
            stats = _run_git_command(
                repo_path,
                [
                    "git",
                    "log",
                    f"--since={since}",
                    f"--until={until}",
                    "--stat",
                    "--oneline",
                    "-n",
                    "20",
                ],
            )
            results.append({
                "repo": repo_name,
                "display_name": _display_project_name(repo_name),
                "path": repo_path,
                "commits": commits,
                "changed_files": changed_files,
                "stats": stats,
            })

    if not results:
        return f"{date_str} 无任何 git 提交记录"

    output = f"=== {date_str} Git 提交汇总 ===\n\n"
    for r in results:
        output += f"【项目: {r['display_name']}】\n"
        output += f"仓库: {r['repo']}\n"
        output += f"路径: {r['path']}\n"
        output += f"提交:\n{r['commits']}\n"
        output += f"变更文件:\n{r['changed_files']}\n"
        output += f"变更统计:\n{r['stats']}\n"
        output += "-" * 40 + "\n\n"
    return output


def _collect_conversations(date_str: str) -> str:
    """内部：收集对话记录"""
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    projects_dir = _get_projects_dir()

    results = []
    if os.path.exists(projects_dir):
        for project_dir in glob.glob(f"{projects_dir}/*"):
            if not os.path.isdir(project_dir):
                continue
            project_name = os.path.basename(project_dir)
            jsonl_files = glob.glob(os.path.join(project_dir, "*.jsonl"))
            for jf in jsonl_files:
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(jf)).date()
                    if mtime != target_date:
                        continue
                    with open(jf, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    user_messages = []
                    for line in lines:
                        try:
                            msg = json.loads(line)
                            if msg.get("toolUseResult") or msg.get("isMeta"):
                                continue

                            is_user = msg.get("type") == "user" or msg.get("role") == "user"
                            message = msg.get("message")
                            if isinstance(message, dict):
                                is_user = is_user or message.get("role") == "user"

                            if is_user:
                                content = (
                                    msg.get("content")
                                    if "content" in msg
                                    else message.get("content") if isinstance(message, dict) else ""
                                )
                                if isinstance(content, list) and any(
                                    isinstance(item, dict) and item.get("type") == "tool_result"
                                    for item in content
                                ):
                                    continue
                                text = _extract_text(content)
                                if _is_effective_user_message(text):
                                    user_messages.append(text)
                        except Exception:
                            continue
                    if user_messages:
                        results.append({
                            "project": project_name,
                            "display_name": _display_project_name(project_name),
                            "file": os.path.basename(jf),
                            "messages": user_messages
                        })
                except Exception:
                    continue

    if not results:
        return f"{date_str} 无 Claude 对话记录"

    output = f"=== {date_str} Claude 对话记录 ===\n\n"
    for r in results:
        output += f"【项目: {r['display_name']}】\n"
        output += f"来源: {r['project']} / {r['file']}\n"
        for i, msg in enumerate(r["messages"][:50], 1):
            preview = msg[:500].replace("\n", " ")
            output += f"  {i}. {preview}{'...' if len(msg) > 500 else ''}\n"
        output += "-" * 40 + "\n\n"
    return output


@mcp.tool()
def generate_daily_report(date: str = None, send_email: bool = True) -> str:
    """一键生成日报，默认保存并发送邮件，返回状态和完整日报正文。"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    content = _build_daily_report(date_str)

    reports_dir = _resolve_reports_dir()
    report_path = os.path.join(reports_dir, f"{date_str}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    if send_email:
        status = _send_report_email(report_path)
    else:
        status = "按要求未发送邮件"

    return f"日报已保存: {report_path}\n{status}\n\n{content}"


@mcp.tool()
def collect_git_commits(date: str = None) -> str:
    """收集指定日期范围内所有 git 仓库的提交记录"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    return _collect_git(date_str)


@mcp.tool()
def collect_claude_conversations(date: str = None) -> str:
    """收集指定日期范围内 Claude Code 的对话记录"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    return _collect_conversations(date_str)


@mcp.tool()
def get_daily_data(date: str = None) -> str:
    """一键获取当天的所有工作数据（git 提交 + Claude 对话记录），用于生成日报"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    git_data = _collect_git(date_str)
    conv_data = _collect_conversations(date_str)
    return f"{git_data}\n\n{conv_data}"


@mcp.tool()
def save_daily_report(content: str, date: str = None) -> str:
    """保存日报内容到文件"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")

    reports_dir = _resolve_reports_dir()
    report_path = os.path.join(reports_dir, f"{date_str}.md")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"日报已保存: {report_path}"


@mcp.tool()
def send_daily_report_email(report_path: str = None) -> str:
    """发送日报邮件"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    report_path = report_path or os.path.join(_resolve_reports_dir(), f"{date_str}.md")

    return _send_report_email(report_path)



@mcp.tool()
def get_email_config() -> str:
    """获取当前邮件配置状态"""
    if not os.path.exists(CONFIG_PATH):
        return "邮件配置不存在，请先调用 configure_email 配置"

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    safe = {k: v for k, v in config.items() if k != "smtp_password"}
    safe["smtp_password"] = "*" * 8 if config.get("smtp_password") else "未设置"
    return json.dumps(safe, ensure_ascii=False, indent=2)


@mcp.tool()
def configure_email(
    smtp_server: str,
    smtp_user: str,
    smtp_password: str,
    from_email: str,
    to_emails: list,
    smtp_port: int = 587,
    use_tls: bool = True,
    use_ssl: bool = False
) -> str:
    """配置邮件发送参数（保留已有的用户信息和路径配置）"""
    config = _load_config()
    config.update({
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "from_email": from_email,
        "to_emails": to_emails,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
    })

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return f"邮件配置已保存到: {CONFIG_PATH}"




if __name__ == "__main__":
    mcp.run(transport="stdio")
