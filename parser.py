"""Markdown parser: extract links, tables, and sync rules from memory tree files."""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Link:
    """A directed reference from one file to another."""
    source: str              # relative path from project root
    target: str              # relative path from project root (resolved)
    raw_target: str          # original link target from markdown
    anchor_text: str         # display text of the link
    link_type: str           # "md_link", "table_ref", "implicit"
    context: str             # surrounding context (table row, paragraph snippet)
    is_external: bool = False
    target_is_external: bool = False


@dataclass
class FileInfo:
    """Metadata about a tracked file."""
    path: str                          # relative from project root
    abs_path: Path
    file_type: str                     # classification label
    exists: bool
    size: int
    last_modified: Optional[datetime] = None
    links: List[Link] = field(default_factory=list)       # outgoing
    backlinks: List[Link] = field(default_factory=list)   # incoming


def strip_root(abs_path: Path, root: Path) -> str:
    """Convert absolute path to relative path from project root."""
    try:
        return str(abs_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(abs_path).replace("\\", "/")


def resolve_link_target(source_path: str, raw_target: str, project_root: Path) -> tuple[str, bool]:
    """Resolve a relative markdown link target against the source file's directory.

    Returns (resolved_path, is_external).  If the resolved path is NOT under
    project_root the target is marked external but the resolved absolute path is
    still returned as a string.
    """
    # Bug 27: UNC paths are always external
    if raw_target.startswith("//") or raw_target.startswith("\\\\"):
        return (raw_target, True)

    # Remove anchor fragments (#section)
    # Bug 24: Strip optional title ("title") before anchor removal
    raw_target = re.sub(r'\s+"[^"]*"$', '', raw_target)
    raw_target = re.sub(r"#[^)]*$", "", raw_target)
    if not raw_target:
        return source_path, False

    source_dir = (project_root / source_path).parent
    try:
        resolved = (source_dir / raw_target).resolve()
        # Check whether the resolved path lives under project_root
        try:
            resolved.relative_to(project_root.resolve())
            is_external = False
        except ValueError:
            is_external = True
        return strip_root(resolved, project_root), is_external
    except Exception:
        return raw_target, False


def extract_md_links(content: str, source_path: str, project_root: Path) -> List[Link]:
    """Extract all [text](path) markdown links from content."""
    links = []
    # Match [text](path) — handle both [→](path) and [text](path)
    pattern = re.compile(r"\[([^\]]*?)\]\(([^)]+)\)")
    for match in pattern.finditer(content):
        anchor = match.group(1).strip() or "→"
        raw_target = match.group(2).strip()
        if raw_target.startswith("http"):
            continue  # skip external URLs
        resolved, is_ext = resolve_link_target(source_path, raw_target, project_root)
        links.append(Link(
            source=source_path,
            target=resolved,
            raw_target=raw_target,
            anchor_text=anchor,
            link_type="external_link" if is_ext else "md_link",
            context=_get_context(content, match.start()),
            is_external=is_ext,
            target_is_external=is_ext,
        ))
    return links


def extract_table_rows(content: str) -> List[dict]:
    """Extract markdown table rows as list of dicts. Returns column headers as keys."""
    lines = content.split("\n")
    tables = []
    current_cols = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if "---" in stripped and "|" in stripped:
                # separator line — columns are set
                continue
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            if not current_cols:
                current_cols = cells
            else:
                if len(cells) == len(current_cols):
                    row = {current_cols[i]: cells[i] for i in range(len(cells))}
                    tables.append(row)
                else:
                    # Uneven columns — might be a new table
                    pass
        else:
            if in_table and not stripped:
                in_table = False
                current_cols = []
    return tables


def extract_checklist_rules(content: str) -> List[dict]:
    """Extract sync rules from 收尾检查 table (three columns: 发生了什么 | 更新哪个文件 | 更新什么)."""
    rules = []
    in_checklist = False
    lines = content.split("\n")
    cols = []
    for line in lines:
        stripped = line.strip()
        if "收尾检查" in stripped:
            in_checklist = True
            continue
        if in_checklist and stripped.startswith("|") and "---" not in stripped:
            cells = [c.strip() for c in stripped[1:-1].split("|")]
            if not cols:
                cols = cells
            elif len(cells) >= 3:
                rules.append({
                    "trigger": cells[0] if len(cells) > 0 else "",
                    "target": cells[1] if len(cells) > 1 else "",
                    "action": cells[2] if len(cells) > 2 else "",
                })
        elif in_checklist and not stripped:
            break
    return rules


def _get_context(content: str, pos: int, window: int = 80) -> str:
    """Get surrounding context for a match position."""
    start = max(0, pos - window)
    end = min(len(content), pos + window)
    ctx = content[start:end].replace("\n", " ")
    return ctx.strip()


def _classify_file(rel_path: str, file_types: Optional[dict] = None) -> str:
    """Classify a file by its relative path using heuristics.

    First checks the provided file_types mapping, then falls back to
    path-based auto-classification.
    """
    if file_types:
        label = file_types.get(rel_path)
        if label:
            return label

    # Auto-classify by path patterns
    if rel_path.startswith("memory/tools/full/"):
        return "tool_l3"
    if rel_path.startswith("memory/tools/"):
        return "tool_standalone"
    if rel_path.startswith("memory/projects/"):
        if "overview" in rel_path:
            return "project_overview"
        if "PROJECT_PROGRESS" in rel_path or "status" in rel_path:
            return "project_progress"
        if "dev-sessions" in rel_path:
            return "dev_sessions"
        return "project_file"
    if rel_path.startswith("memory/archive/"):
        return "archive_index"
    if rel_path.startswith("memory/") and rel_path.count("/") == 1:
        return "diary"
    if rel_path.endswith(".md"):
        return "root_doc"

    return "unknown"


def parse_file(abs_path: Path, project_root: Path, file_types: Optional[dict] = None) -> FileInfo:
    """Parse a single file and extract all its links."""
    rel_path = strip_root(abs_path, project_root)
    file_type = _classify_file(rel_path, file_types)

    exists = abs_path.exists()
    stat = abs_path.stat() if exists else None

    info = FileInfo(
        path=rel_path,
        abs_path=abs_path,
        file_type=file_type,
        exists=exists,
        size=stat.st_size if stat else 0,
        last_modified=datetime.fromtimestamp(stat.st_mtime) if stat else None,
    )

    if exists and abs_path.suffix == ".md":
        # Bug 22: Guard against OOM on very large files
        if stat and stat.st_size > 50 * 1024 * 1024:
            info.links = []
            return info
        try:
            content = abs_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            info.links = []
            return info
        except Exception:
            content = ""
        info.links = extract_md_links(content, rel_path, project_root)

    return info
