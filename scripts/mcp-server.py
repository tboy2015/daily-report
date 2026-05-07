#!/usr/bin/env python3
"""
Daily Report MCP Server
提供日报生成所需的工具：收集 git 提交、收集对话记录、保存日报、发送邮件
"""

import json
import os
import subprocess
import glob
import sys
import io
import contextlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

from mcp.server.fastmcp import FastMCP

SCRIPT_DIR = os.path.dirname(__file__)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from mailer import load_config, send_daily_report

mcp = FastMCP("daily-report")

WORK_DIR = "/Users/tboy/work/codework/lc"
PROJECTS_DIR = "/Users/tboy/.claude/projects"
REPORTS_DIR = "/Users/tboy/Documents/daily-reports"
CONFIG_PATH = "/Users/tboy/.claude/daily-report-config.json"

PROJECT_NAME_MAP = {
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

# 全局配置：技术栈标记定义
TECH_STACK_MARKERS = {
    "Java": ["src/main/java", ".java"],
    "Vue": [".vue", "src/views/", "src/components/"],
    "TypeScript/JavaScript": [".tsx", ".jsx", ".ts", ".js"],
    "Maven": ["pom.xml", "maven"],
    "Node.js": ["package.json", "yarn.lock", "npm"],
    "Docker": ["docker", "dockerfile", "docker-compose"],
}

# 全局配置：工作类型关键词
WORK_TYPE_KEYWORDS = {
    "功能开发": ["功能", "完成", "feat:", "feature"],
    "前端开发": ["页面", "组件", "ui", "frontend"],
    "后端开发": ["后端", "接口", "服务"],
    "问题修复": ["fix", "bug", "修复", "bugfix", "问题"],
    "配置更新": ["配置", "依赖", "config", "update"],
    "文档整理": ["文档", "说明", "doc"],
}

# 全局配置：工作类型文件标记
WORK_TYPE_MARKERS = {
    "功能开发": ["src/main/java", "src/service/", "src/controller/"],
    "前端开发": [".vue", ".tsx", ".jsx", "src/pages/", "src/components/", "src/views/"],
    "后端开发": ["src/main/java", "controller", "service", "mapper", "dto", "entity"],
    "问题修复": [],  # 通过关键词识别
    "配置更新": ["pom.xml", "package.json", "application.yml", "docker"],
    "文档整理": [".md", "readme", "doc"],
}

# 全局配置：核心逻辑关键词
CORE_LOGIC_KEYWORDS = [
    "队列", "异步", "缓存", "连接池", "线程", "事务", "分布式",
    "组件", "路由", "状态", "生命周期", "Hook", "模块化"
]


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
    if normalized.startswith("-Users-tboy-work-codework-lc-"):
        normalized = normalized.replace("-Users-tboy-work-codework-lc-", "", 1)

    if normalized in PROJECT_NAME_MAP:
        return PROJECT_NAME_MAP[normalized]

    lower = normalized.lower()
    if lower in PROJECT_NAME_MAP:
        return PROJECT_NAME_MAP[lower]

    for key, value in PROJECT_NAME_MAP.items():
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


def _find_git_repos(root_dir: str):
    """递归发现工作目录下的 git 仓库。"""
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
    2) Default REPORTS_DIR (/Users/tboy/Documents/daily-reports)
    3) Fallback inside this skill workspace (../output/daily-reports)
    """
    env_dir = os.environ.get("DAILY_REPORTS_DIR")
    candidates = []
    if env_dir:
        candidates.append(env_dir)
    candidates.append(REPORTS_DIR)
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


def _format_cn_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%Y年%m月%d日")


def _repo_activity(repo_name: str, repo_path: str, date_str: str):
    since = f"{date_str} 00:00"
    until = f"{date_str} 23:59"
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
    if not commits or commits.startswith("ERROR"):
        return None

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
    changed_files = sorted({line.strip() for line in files.splitlines() if line.strip()})
    subjects = [line.split("|", 2)[1] for line in commits.splitlines() if "|" in line]
    return {
        "repo": repo_name,
        "path": repo_path,
        "display_name": _display_project_name(repo_name),
        "subjects": subjects,
        "files": changed_files,
    }


def _contains_any(texts, keywords):
    joined = "\n".join(texts).lower()
    return any(keyword.lower() in joined for keyword in keywords)


def _infer_tech_stack(files: Optional[List[str]]) -> List[str]:
    """从文件列表推断技术栈"""
    # 输入验证：检查files是否为None或非列表类型
    if not files or not isinstance(files, (list, tuple)):
        return []

    try:
        # 确保所有元素都是字符串
        file_text = "\n".join(str(f) for f in files).lower()
    except Exception:
        return []

    tech_stacks = []

    for tech, markers in TECH_STACK_MARKERS.items():
        if any(marker in file_text for marker in markers):
            tech_stacks.append(tech)

    return tech_stacks


def _estimate_code_volume(files: Optional[List[str]]) -> str:
    """估算代码量（基于受影响文件数）"""
    # 输入验证：检查files是否为None或非列表类型
    if not files or not isinstance(files, (list, tuple)):
        return "~10"

    try:
        # 确保所有元素都是字符串
        code_files = [f for f in files if isinstance(f, str) and not f.startswith(".") and not f.endswith(".md")]
    except Exception:
        return "~10"

    count = len(code_files)
    if count == 0:
        return "~10"
    elif count <= 3:
        return f"~{count * 20}"
    elif count <= 10:
        return f"~{count * 50}"
    else:
        return f"~{count * 100}"


def _extract_summary_from_subject(subject: Optional[str]) -> str:
    """从 commit message 提取概括"""
    # 输入验证：检查subject是否为None或非字符串
    if not subject or not isinstance(subject, str):
        return "完成代码调整"

    cleaned = subject.replace("feat:", "").replace("fix:", "").strip()
    if len(cleaned) > 40:
        cleaned = cleaned[:40] + "..."
    return cleaned


def _identify_work_type(subjects: Optional[List[str]], files: Optional[List[str]]) -> Dict[str, float]:
    """识别工作类型并返回优先级"""
    # 输入验证
    if not subjects or not isinstance(subjects, (list, tuple)):
        subjects = []
    if not files or not isinstance(files, (list, tuple)):
        files = []

    try:
        # 确保所有元素都是字符串
        file_text = "\n".join(str(f) for f in files).lower()
        subject_text = "\n".join(str(s) for s in subjects).lower()
    except Exception:
        return {}

    work_types: Dict[str, float] = {}

    # 功能开发
    if any(kw in subject_text for kw in WORK_TYPE_KEYWORDS.get("功能开发", [])) or \
       any(marker in file_text for marker in WORK_TYPE_MARKERS.get("功能开发", [])):
        work_types["功能开发"] = 1.0

    # 前端开发
    if any(kw in subject_text for kw in WORK_TYPE_KEYWORDS.get("前端开发", [])) or \
       any(marker in file_text for marker in WORK_TYPE_MARKERS.get("前端开发", [])):
        work_types["前端开发"] = 0.9

    # 后端开发
    if any(marker in file_text for marker in WORK_TYPE_MARKERS.get("后端开发", [])):
        work_types["后端开发"] = 0.8

    # 问题修复
    if any(kw in subject_text for kw in WORK_TYPE_KEYWORDS.get("问题修复", [])):
        work_types["问题修复"] = 1.0

    # 配置更新
    if any(kw in subject_text for kw in WORK_TYPE_KEYWORDS.get("配置更新", [])) or \
       any(marker in file_text for marker in WORK_TYPE_MARKERS.get("配置更新", [])):
        work_types["配置更新"] = 0.7

    # 文档整理
    if any(marker in file_text for marker in WORK_TYPE_MARKERS.get("文档整理", [])):
        work_types["文档整理"] = 0.6

    return work_types


def _extract_detailed_work_items(activity: Optional[Dict[str, Any]], conversation_content: str = "") -> Dict[str, List[str]]:
    """
    从 activity（git 数据）和对话内容提取详细的工作项。

    输入：
    - activity: {"subjects": [...], "files": [...]} 或 None
    - conversation_content: 对话内容文本

    输出：
    {
        "功能开发": [
            "项目1概括（5-6行详细描述）",
            "项目2概括",
            ...
        ],
        "前端开发": [...],
        ...
    }
    """
    # 输入验证：检查activity是否为None或无效
    if not activity or not isinstance(activity, dict):
        return {}

    subjects = activity.get("subjects", [])
    files = activity.get("files", [])

    # 确保subjects和files是列表
    if not isinstance(subjects, (list, tuple)):
        subjects = []
    if not isinstance(files, (list, tuple)):
        files = []

    result: Dict[str, List[str]] = {}
    work_types = _identify_work_type(subjects, files)

    if not work_types:
        # 没有识别到任何类型，使用默认类型
        work_types = {"项目推进": 1.0}

    # 按优先级排序
    sorted_types = sorted(work_types.items(), key=lambda x: -x[1])

    for work_type, priority in sorted_types:
        items: List[str] = []

        if work_type in ("功能开发", "前端开发"):
            # 详细描述格式：概括 + 实现方式 + 技术栈 + 核心逻辑 + 代码量
            first_subject = subjects[0] if subjects else None
            summary = _extract_summary_from_subject(first_subject)

            # 技术栈
            tech_stack = _infer_tech_stack(files)
            tech_text = "、".join(tech_stack) if tech_stack else "多技术栈"

            # 核心逻辑 - 从对话内容提取关键词
            logic_keywords = []
            if conversation_content:
                for kw in CORE_LOGIC_KEYWORDS:
                    if kw.lower() in conversation_content.lower():
                        logic_keywords.append(kw)
            logic_text = "、".join(logic_keywords[:3]) if logic_keywords else "业务逻辑"

            # 代码量
            code_volume = _estimate_code_volume(files)

            # 组装详细项
            item_lines = [
                f"概括：{summary}",
                f"实现方式：设计并实现{work_type.replace('开发', '')}功能模块",
                f"核心逻辑：{logic_text}处理"
            ]
            items.append("\n".join(item_lines))

        else:
            # 其他分类：简洁描述（1-3行）
            if subjects:
                summary = "；".join([_extract_summary_from_subject(s) for s in subjects[:2]])
            else:
                summary = "完成相关代码调整"
            items.append(summary)

        if items:
            result[work_type] = items

    return result


def _summarize_activity(activity):
    """向后兼容的旧函数 - 用于字符串输出"""
    subjects = activity["subjects"]
    files = activity["files"]
    file_text = "\n".join(files)
    subject_text = "；".join(subjects)
    bullets = []

    batch_download = _contains_any(
        subjects + files,
        ["批量下载", "batchdownload", "download", "FileBatchDownload", "downloadApply"],
    )
    if batch_download:
        bullets.append(("功能开发", "完成组件文档批量下载功能核心开发，贯通文件下载申请、文档记录和业务页面调用链路"))
    elif subjects:
        cleaned = "；".join(s.replace("feat:", "").replace("fix:", "").strip() for s in subjects[:3])
        bullets.append(("功能开发", f"完成{cleaned}相关开发，推进项目功能完善"))

    frontend_markers = (".tsx", ".jsx", ".vue", "src/apis/", "src/pages/", "src/components/", "src/views/")
    if any(marker in file_text for marker in frontend_markers):
        bullets.append(("前端开发", "更新前端 API、页面组件和交互逻辑，完善业务页面对下载功能的调用和反馈"))

    backend_markers = ("src/main/java", "Controller", "Service", "Mapper", "DTO", "Entity", "ExceptionHandler")
    if any(marker in file_text for marker in backend_markers):
        bullets.append(("后端开发", "新增和调整后端接口、数据传输对象及异常处理逻辑，支撑文件批量下载服务能力"))

    config_markers = ("package.json", "vite.config", "pom.xml", "application.yml", "yarn.lock", "Dockerfile", "nginx.conf")
    if any(marker in file_text for marker in config_markers):
        bullets.append(("配置更新", "同步前后端依赖、构建配置和运行参数，保障功能开发后的编译与部署一致性"))

    init_markers = ("init", "初始化")
    if _contains_any(subjects, init_markers):
        bullets.append(("项目维护", "完成项目基础代码和资源文件初始化，为后续模块开发提供基础工程结构"))

    if not bullets:
        bullets.append(("项目推进", "根据当日提交记录完成项目相关代码调整和功能完善"))

    deduped = []
    seen = set()
    for category, description in bullets:
        if category not in seen:
            seen.add(category)
            deduped.append((category, description))
    return deduped[:5]


def _build_daily_report(date_str: str):
    cn_date = _format_cn_date(date_str)

    # 采集当天的对话内容
    conversation_content = _collect_conversations(date_str) or ""

    activities = []
    for repo_name, repo_path in _find_git_repos(WORK_DIR):
        activity = _repo_activity(repo_name, repo_path, date_str)
        if activity:
            activities.append(activity)

    lines = [
        "各位领导：",
        "",
        f"以下为南网业务处唐标{cn_date}工作日报，烦请领导查收指正。",
        "",
        "-----------------------------------",
        "",
        f"一、日报日期：{cn_date}",
        "",
        "二、今日工作内容：",
        "",
    ]

    if activities:
        for index, activity in enumerate(activities, 1):
            lines.append(f"{index}、项目名称：{activity['display_name']}")
            work_items = _extract_detailed_work_items(activity, conversation_content)
            for category, items in work_items.items():
                lines.append(f"· {category}：")
                for item in items:
                    # 如果 item 包含换行符，按行输出
                    if "\n" in item:
                        for line in item.split("\n"):
                            lines.append(f"  {line}")
                    else:
                        lines.append(f"  {item}")
            lines.append("")
    else:
        lines.append("当日无记录")
        lines.append("")

    lines.extend([
        "三、明日（下周）工作计划：",
    ])
    if activities:
        lines.extend([
            "· 开展当日开发功能的单元测试、联调测试和回归验证",
            "· 验证前后端交互逻辑、异常处理和部署配置的正确性",
            "· 根据测试反馈修复问题，优化用户交互体验和性能表现",
            "· 完成代码审查，补充必要的接口说明和交付文档",
        ])
    else:
        lines.append("· 暂无")

    primary = activities[0] if activities else None
    project = primary["display_name"] if primary else "暂无"
    module = "组件文档模块" if primary and primary["display_name"] == "成就中心" else "核心业务模块"

    # 从新的详细项中提取已完成项
    if primary:
        work_items = _extract_detailed_work_items(primary, conversation_content)
        completed_items = []
        for category, items in work_items.items():
            if items:
                first_item = items[0]
                if "\n" in first_item:
                    first_item = first_item.split("\n")[0]
                completed_items.append(f"{category}：{first_item[:30]}")
        completed = "、".join(completed_items[:2]) if completed_items else "项目功能开发"
    else:
        completed = "当日无记录"

    next_step = "功能测试、Bug 修复、代码审查和用户反馈优化" if primary else "暂无"
    risk = "跨模块文件操作的性能、稳定性和部署环境差异需进一步验证" if primary else "暂无"

    lines.extend([
        "",
        "四、重点项目里程碑情况：",
        f"· {project} - {module}：开发阶段（50%）" if primary else "· 暂无",
        f"· 已完成：{completed}",
        f"· 下一步：{next_step}",
        f"· 风险点：{risk}",
        "",
        "-----------------------------------",
        "山东浪潮数字服务有限公司",
        "交通服务事业部 - 南网业务处",
        "唐标",
        "Tel: 13707490673",
        "E-mail: tangbiao@inspur.com",
        cn_date,
        "",
    ])
    return "\n".join(lines)


def _collect_git(date_str: str) -> str:
    """内部：收集 git 提交"""
    since = f"{date_str} 00:00"
    until = f"{date_str} 23:59"

    repos = _find_git_repos(WORK_DIR)

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

    results = []
    if os.path.exists(PROJECTS_DIR):
        for project_dir in glob.glob(f"{PROJECTS_DIR}/*"):
            if not os.path.isdir(project_dir):
                continue
            project_name = os.path.basename(project_dir)
            jsonl_files = glob.glob(f"{project_dir}/*.jsonl")
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
def save_and_send(content: str, date: str = None) -> str:
    """保存日报并立即发送邮件（一键保存+发送）"""
    date_str = date or datetime.now().strftime("%Y-%m-%d")

    reports_dir = _resolve_reports_dir()
    report_path = os.path.join(reports_dir, f"{date_str}.md")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"日报已保存: {report_path}\n{_send_report_email(report_path)}"


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
    """配置邮件发送参数"""
    config = {
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "from_email": from_email,
        "to_emails": to_emails,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return f"邮件配置已保存到: {CONFIG_PATH}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
