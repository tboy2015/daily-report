#!/usr/bin/env python3
# /// script
# dependencies = ["mcp<2"]
# ///
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

SCRIPT_DIR = os.path.dirname(__file__)

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    try:
        from mcp.server.mcpserver import MCPServer as FastMCP
    except ModuleNotFoundError:
        repo_dir = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
        venv_python = os.path.join(repo_dir, ".venv", "bin", "python")
        if os.path.exists(venv_python) and os.path.abspath(sys.executable) != os.path.abspath(venv_python):
            os.execv(venv_python, [venv_python, *sys.argv])
        raise

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from mailer import load_config, send_daily_report

mcp = FastMCP("daily-report")

CONFIG_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "config.json"))
PROJECT_NAME_MAP_PATH = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "project-name-map.json"))


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


def _get_codex_sessions_dir() -> str:
    """返回 Codex 会话目录，支持通过配置覆盖。"""
    cfg = _load_config()
    raw = cfg.get("paths", {}).get("codex_sessions_dir") or ""
    if raw:
        return os.path.expanduser(raw)

    codex_home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    return os.path.join(os.path.expanduser(codex_home), "sessions")


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
    merged = _load_default_project_name_map()
    overrides = cfg.get("project_name_map", {})
    if isinstance(overrides, dict):
        merged.update(overrides)
    return merged


def _load_default_project_name_map() -> dict:
    """加载随 skill 分发的默认项目名映射。"""
    if not os.path.exists(PROJECT_NAME_MAP_PATH):
        return {}
    try:
        with open(PROJECT_NAME_MAP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}



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
        "<environment_context>",
        "<external_codex_apps_open_page>",
        "<turn_aborted>",
        "# AGENTS.md instructions for",
        "[$daily-report",
        "<skill>",
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


def _clean_codex_user_message(text: str) -> str:
    """从 Codex 附件/图片包装消息中提取真正的用户请求。"""
    if not isinstance(text, str):
        return ""

    cleaned = text.strip()
    request_marker = "## My request:"
    if request_marker in cleaned:
        cleaned = cleaned.split(request_marker, 1)[1].strip()

    # 图片内容不会以文本写入会话，移除占位标签，避免日报出现临时路径和包装指令。
    cleaned = re.sub(r"<image\b[^>]*>.*?</image>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(
        r"Distinguish instructions in attached documents from the user's request\.?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


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
    - {{var}}                      简单变量替换
    - {{#each list}}...{{/each}}   循环（支持嵌套），每项可用 {{field}} 或 {{this}}
    - {{^var}}...{{/var}}          当 var 为空/假时渲染
    """
    result = []
    i = 0
    n = len(text)

    while i < n:
        j = text.find('{{', i)
        if j == -1:
            result.append(text[i:])
            break

        result.append(text[i:j])

        k = text.find('}}', j + 2)
        if k == -1:
            result.append(text[j:])
            break

        tag = text[j + 2:k].strip()
        i = k + 2

        if tag.startswith('#each '):
            key = tag[6:].strip()
            # 用深度计数找到正确匹配的 {{/each}}，支持嵌套
            depth = 1
            p = i
            block_end = -1
            while p < n:
                next_open = text.find('{{#each ', p)
                next_close = text.find('{{/each}}', p)
                if next_close == -1:
                    break
                if next_open != -1 and next_open < next_close:
                    depth += 1
                    p = next_open + 8
                else:
                    depth -= 1
                    if depth == 0:
                        block_end = next_close
                        break
                    p = next_close + 9
            if block_end == -1:
                continue
            block = text[i:block_end]
            items = ctx.get(key) or []
            for item in items:
                child_ctx = {**ctx, **(item if isinstance(item, dict) else {'this': str(item)})}
                result.append(_render_template(block, child_ctx))
            i = block_end + 9  # 跳过 {{/each}}

        elif tag.startswith('^'):
            key = tag[1:].strip()
            close_tag = '{{/' + key + '}}'
            end = text.find(close_tag, i)
            if end == -1:
                continue
            block = text[i:end]
            if not ctx.get(key):
                result.append(_render_template(block, ctx))
            i = end + len(close_tag)

        elif tag.startswith('/'):
            pass  # 正常流程不应到达，跳过

        else:
            val = ctx.get(tag)
            result.append(str(val) if val is not None else '{{' + tag + '}}')

    return ''.join(result)


def _normalize_report_spacing(content: str) -> str:
    """清理模板循环带来的多余空行，保持邮件正文紧凑。"""
    text = re.sub(r"\n{3,}", "\n\n", content.strip())
    # 同一组项目、计划、里程碑内的 bullet 不留空行。
    while "\n\n·" in text:
        text = text.replace("\n\n·", "\n·")
    return text


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


def _polish_work_item(summary: str) -> str:
    """将 commit 摘要整理为日报中的业务化单层工作项。"""
    if not summary:
        return "完成项目功能调整，支撑业务流程稳定运行"

    text = summary.strip().rstrip("。")

    # 常见提交信息的业务化改写，避免直接暴露实现口径。
    replacements = [
        (r"实现\s*SDH\s*南向客户端及\s*Token/VC4\s*接口，?增强配置界面",
         "完成 SDH 南向系统集成，支持业务认证、通道资源创建等核心能力，并优化南向配置页面的展示与维护体验"),
        (r"SDH\s*南向客户端及\s*Token/VC4\s*接口",
         "SDH 南向系统接入、业务认证和通道资源创建能力"),
        (r"Token/VC4\s*接口", "业务认证和通道资源接口"),
        (r"Token", "业务认证"),
        (r"VC4", "通道资源"),
        (r"客户端", "服务接入"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)

    # 已经是动作开头时只补齐结果导向的语气。
    action_prefixes = (
        "完成", "完善", "优化", "修复", "解决", "新增", "补充",
        "调整", "改造", "实现", "支持", "梳理", "接入",
    )
    if not text.startswith(action_prefixes):
        text = f"完成{text}"
    elif text.startswith("实现"):
        text = "完成" + text[2:]

    if not any(marker in text for marker in ["提升", "保证", "确保", "支撑", "避免", "满足", "优化"]):
        text += "，支撑相关业务流程稳定运行"

    return text + "。"


def _build_flat_work_items(activity: Optional[Dict[str, Any]]) -> List[str]:
    """生成单层工作内容，避免分类标题和子项嵌套导致邮件排版凌乱。"""
    grouped = _extract_detailed_work_items(activity)
    if not grouped:
        return []

    preferred_order = ["功能开发", "后端开发", "前端开发", "配置更新", "开发工具", "文档整理", "问题修复", "其他"]
    items: List[str] = []
    for category in preferred_order:
        summaries = grouped.get(category, [])
        for summary in summaries:
            items.append(_polish_work_item(summary))

    # 兜底包含未知分类，保持发现顺序。
    for category, summaries in grouped.items():
        if category in preferred_order:
            continue
        for summary in summaries:
            items.append(_polish_work_item(summary))

    return items


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



def _merge_activities_by_display_name(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将映射到同一中文项目名的多个仓库合并为一个活动，保持仓库发现顺序。"""
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for act in activities:
        name = act["display_name"]
        if name not in merged:
            merged[name] = {
                "repo": act["repo"],
                "path": act["path"],
                "display_name": name,
                "subjects": list(act.get("subjects", [])),
                "files": list(act.get("files", [])),
                "commit_blocks": list(act.get("commit_blocks", [])),
            }
            order.append(name)
        else:
            tgt = merged[name]
            tgt["subjects"].extend(act.get("subjects", []))
            tgt["files"].extend(act.get("files", []))
            tgt["commit_blocks"].extend(act.get("commit_blocks", []))

    for tgt in merged.values():
        tgt["files"] = sorted(set(tgt["files"]))

    return [merged[name] for name in order]


def _build_daily_report(date_str: str) -> str:
    cn_date = _format_cn_date(date_str)
    user = _get_user_info()

    raw_activities = []
    for repo_name, repo_path in _find_git_repos():
        activity = _repo_activity(repo_name, repo_path, date_str)
        if activity:
            raw_activities.append(activity)

    # 按中文项目名合并多个仓库（如前端/后端 repo 映射到同一业务项目）
    activities = _merge_activities_by_display_name(raw_activities)

    # 组装 projects 数据
    projects = []
    for i, activity in enumerate(activities, 1):
        work_items = _build_flat_work_items(activity)
        projects.append({
            "index": str(i),
            "name": activity["display_name"],
            "items": work_items,
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
        primary_items = _build_flat_work_items(primary)
        cleaned = [item.rstrip("。") for item in primary_items[:3] if item]
        completed = "；".join(cleaned) if cleaned else "完成项目功能开发"
        if len(completed) > 80:
            completed = completed[:80] + "..."
        milestones = [{
            "project": primary["display_name"],
            "module": defaults.get("milestone_module", "核心业务模块"),
            "completed": completed,
            "next_step": defaults.get("milestone_next_step", "功能测试、Bug 修复、代码审查和用户反馈优化"),
            "risk": "无",
        }]
    else:
        milestones = [{
            "project": "暂无",
            "module": "—",
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

    return _normalize_report_spacing(_render_template(template, ctx))


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


def _collect_claude_conversations(date_str: str) -> str:
    """内部：收集 Claude Code 对话记录。"""
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


# 保留旧的内部函数名，避免已有调用方升级后失效。
_collect_conversations = _collect_claude_conversations


def _parse_codex_timestamp_date(value: Any):
    """将 Codex 的 ISO 时间转换为本机时区日期。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone().date() if parsed.tzinfo else parsed.date()
    except (TypeError, ValueError):
        return None


def _codex_session_files(date_str: str) -> List[str]:
    """查找指定日期的活跃及已归档 Codex 会话文件。"""
    target = datetime.strptime(date_str, "%Y-%m-%d")
    sessions_dir = _get_codex_sessions_dir()
    active_pattern = os.path.join(
        sessions_dir,
        target.strftime("%Y"),
        target.strftime("%m"),
        target.strftime("%d"),
        "*.jsonl",
    )
    files = glob.glob(active_pattern)

    archived_dir = os.path.join(os.path.dirname(sessions_dir), "archived_sessions")
    files.extend(glob.glob(os.path.join(archived_dir, f"rollout-{date_str}*.jsonl")))
    return sorted(set(files))


def _collect_codex_conversations(date_str: str) -> str:
    """内部：收集 Codex 当日会话中的有效用户需求。"""
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    results = []
    seen_messages = set()

    for session_file in _codex_session_files(date_str):
        cwd = ""
        messages = []
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    payload = record.get("payload")
                    if not isinstance(payload, dict):
                        continue

                    if record.get("type") == "session_meta":
                        cwd = payload.get("cwd") or cwd
                        continue

                    if not (
                        record.get("type") == "response_item"
                        and payload.get("type") == "message"
                        and payload.get("role") == "user"
                    ):
                        continue

                    timestamp = record.get("timestamp")
                    message_date = _parse_codex_timestamp_date(timestamp)
                    if message_date is not None and message_date != target_date:
                        continue

                    text = _clean_codex_user_message(_extract_text(payload.get("content")))
                    if not _is_effective_user_message(text):
                        continue

                    dedupe_key = (timestamp, text.strip())
                    if dedupe_key in seen_messages:
                        continue
                    seen_messages.add(dedupe_key)
                    messages.append(text.strip())
        except (OSError, UnicodeError):
            continue

        if messages:
            project_name = (
                os.path.basename(os.path.normpath(cwd)) if cwd else "Codex"
            ) or "Codex"
            results.append({
                "project": project_name,
                "display_name": _display_project_name(project_name),
                "file": os.path.basename(session_file),
                "messages": messages,
            })

    if not results:
        return f"{date_str} 无 Codex 对话记录"

    output = f"=== {date_str} Codex 对话记录 ===\n\n"
    for result in results:
        output += f"【项目: {result['display_name']}】\n"
        output += f"来源: {result['project']} / {result['file']}\n"
        for i, message in enumerate(result["messages"][:50], 1):
            preview = message[:500].replace("\n", " ")
            output += f"  {i}. {preview}{'...' if len(message) > 500 else ''}\n"
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
    return _collect_claude_conversations(date_str)


@mcp.tool()
def collect_codex_conversations(date: str = None) -> str:
    """收集指定日期范围内 Codex 的对话记录。"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    return _collect_codex_conversations(date_str)


@mcp.tool()
def get_daily_data(date: str = None) -> str:
    """一键获取当天的所有工作数据（git 提交 + Claude/Codex 对话记录），用于生成日报。"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")
    git_data = _collect_git(date_str)
    claude_data = _collect_claude_conversations(date_str)
    codex_data = _collect_codex_conversations(date_str)
    return f"{git_data}\n\n{claude_data}\n\n{codex_data}"


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
