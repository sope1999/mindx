"""mindx configuration - paths, file types, sync rules, and YAML config management."""

import copy
import os
from pathlib import Path
from typing import Optional

import yaml

# ── Defaults ────────────────────────────────────────────────
HOST = "127.0.0.1"
PORT = 5020
CONFIG_PATH = Path(__file__).parent / "config.yaml"

# ── File type classification defaults ───────────────────────
FILE_TYPES = {
    "MEMORY.md": "root_index",
    "AGENTS.md": "constitution",
    "SOUL.md": "constitution",
    "USER.md": "constitution",
    "IDENTITY.md": "constitution",
    "HEARTBEAT.md": "constitution",
    "TOOLS.md": "cheatsheet",
    "urls.md": "bookmarks",
    "项目开发工作规则.md": "manual",
    "任务工作规则.md": "manual",
    "项目开发管理方案.md": "manual",
    "memory/projects/_index.md": "project_index",
    "memory/archive/_index.md": "archive_index",
    # Project files
    "memory/projects/aviation/overview.md": "project_overview",
    "memory/projects/aviation/PROJECT_PROGRESS.md": "project_progress",
    "memory/projects/aviation/dev-sessions.md": "dev_sessions",
    "memory/projects/aviation/dev-sessions-old.md": "dev_sessions_old",
    # Tool L2 files
    "memory/tools/claude-code.md": "tool_l2",
    "memory/tools/opencode.md": "tool_l2",
    # Tool L3 files
    "memory/tools/full/claude-code.md": "tool_l3",
    "memory/tools/full/opencode.md": "tool_l3",
    # Tool standalone files
    "memory/tools/napcat.md": "tool_standalone",
    "memory/tools/ragflow.md": "tool_standalone",
    "memory/tools/search.md": "tool_standalone",
    "memory/tools/cron.md": "tool_standalone",
    "memory/tools/vcp.md": "tool_standalone",
    "memory/tools/system.md": "tool_standalone",
    "memory/tools/urls.md": "tool_standalone",
    "memory/tools/warning.md": "tool_standalone",
}

# ── Files to ignore ─────────────────────────────────────────
IGNORE_PATTERNS = [
    ".git", ".claude", ".learnings", ".openclaw",
    "*.pyc", "temp/*", "temp_docs/*",
    "docs/*", "warning/*",
]

# ── Sync rules (from MEMORY.md 收尾检查 table) ──────────────
SYNC_RULES = [
    {
        "trigger": "file_modified",
        "pattern": "memory/tools/system.md",
        "target": None,
        "action": "self_document",
        "reason": "系统环境变化 — 需确认版本/包信息是否已更新",
    },
    {
        "trigger": "file_modified",
        "pattern": "urls.md",
        "target": None,
        "action": "self_document",
        "reason": "新网址 — 确认已追加到 urls.md",
    },
    {
        "trigger": "file_modified",
        "pattern": "USER.md",
        "target": None,
        "action": "self_document",
        "reason": "飞鼠/小白信息变化 — 确认 USER.md 已更新",
    },
    {
        "trigger": "file_modified",
        "pattern": "memory/tools/full/claude-code.md",
        "target": "memory/tools/claude-code.md",
        "action": "l3_to_l2_sync",
        "reason": "L3 完整版变化 → L2 摘要可能需要同步",
    },
    {
        "trigger": "file_modified",
        "pattern": "memory/tools/full/opencode.md",
        "target": "memory/tools/opencode.md",
        "action": "l3_to_l2_sync",
        "reason": "L3 完整版变化 → L2 摘要可能需要同步",
    },
    {
        "trigger": "file_modified",
        "pattern": "memory/projects/aviation/overview.md",
        "target": "memory/projects/aviation/PROJECT_PROGRESS.md",
        "action": "project_sync",
        "reason": "overview 变更 → 检查 PROJECT_PROGRESS 状态是否需要更新",
    },
    {
        "trigger": "file_created",
        "pattern": "memory/projects/*/",
        "target": "MEMORY.md",
        "action": "index_update",
        "reason": "新项目创建 → MEMORY.md 项目表需要加行，_index.md 需要加行",
    },
    {
        "trigger": "file_deleted",
        "pattern": "memory/projects/*/",
        "target": "MEMORY.md",
        "action": "index_update",
        "reason": "项目删除 → MEMORY.md 和 _index.md 需要移除对应行",
    },
    {
        "trigger": "file_created",
        "pattern": "memory/tools/*.md",
        "target": "MEMORY.md",
        "action": "index_update",
        "reason": "新工具文件创建 → MEMORY.md 工具表需要加行",
    },
    {
        "trigger": "file_deleted",
        "pattern": "memory/tools/*.md",
        "target": "MEMORY.md",
        "action": "index_update",
        "reason": "工具文件删除 → MEMORY.md 工具表需要移除对应行",
    },
    {
        "trigger": "file_modified",
        "pattern": "memory/projects/aviation/dev-sessions.md",
        "target": "memory/projects/aviation/dev-sessions-old.md",
        "action": "sibling_sync",
        "reason": "dev-sessions 活跃任务变更 → 已完成任务需迁移到 dev-sessions-old",
    },
]


def _default_config() -> dict:
    """Return the default config structure."""
    return {
        "version": "1.0.0",
        "port": PORT,
        "projects": [],
    }


def load_config(path: Optional[Path] = None) -> dict:
    """Read config.yaml and return the config dict.

    Creates a default config file if none exists.
    """
    target = Path(path) if path else CONFIG_PATH
    if not target.exists():
        cfg = _default_config()
        _save_yaml(target, cfg)
        return cfg

    with open(target, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or _default_config()

    # Ensure required keys exist
    cfg.setdefault("version", "1.0.0")
    cfg.setdefault("port", PORT)
    cfg.setdefault("projects", [])
    return cfg


def save_config(config: dict, path: Optional[Path] = None) -> None:
    """Write config dict back to config.yaml."""
    target = Path(path) if path else CONFIG_PATH
    _save_yaml(target, config)


def _save_yaml(target: Path, config: dict) -> None:
    """Serialize config dict to a YAML file."""
    # Avoid writing project defaults into the file
    out = copy.deepcopy(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(target) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.dump(out, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
    os.replace(tmp, str(target))


def get_project_config(config: dict, name: str) -> Optional[dict]:
    """Find a project entry by name. Returns None if not found."""
    for proj in config.get("projects", []):
        if proj.get("name") == name:
            return proj
    return None


def add_project(config: dict, name: str, root: str) -> dict:
    """Add a project entry. Returns the project dict added."""
    root_path = Path(root).resolve()
    root_str = str(root_path)

    # Check for duplicate name
    existing = get_project_config(config, name)
    if existing:
        base = name
        n = 1
        while get_project_config(config, f"{base}({n})"):
            n += 1
        name = f"{base}({n})"

    # Check for duplicate root path
    for proj in config.get("projects", []):
        if Path(proj.get("root", "")).resolve() == root_path:
            return proj  # already exists, return existing

    proj = {"name": name, "root": root_str, "external_paths": [], "positions": {}, "file_classes": {}, "excluded_dirs": [], "display_mode": "full", "ref_roots": [], "active_root": None}
    config.setdefault("projects", []).append(proj)
    return proj


def remove_project(config: dict, name: str) -> bool:
    """Remove a project entry by name. Returns True if removed."""
    projects = config.get("projects", [])
    for i, proj in enumerate(projects):
        if proj.get("name") == name:
            projects.pop(i)
            return True
    return False
