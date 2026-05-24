"""mindx MCP Server — Model Context Protocol interface for mindx knowledge graph.

Usage:
  python mcp_server.py

Register in Cursor/Claude Desktop:
  {
    "mcpServers": {
      "mindx": {
        "command": "python",
        "args": ["C:/SOFT/AI/mindx/mcp_server.py"]
      }
    }
  }
"""

import json
import asyncio
from pathlib import Path
from typing import Any

import requests
import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ── Config ──
CONFIG = None         # loaded from config.yaml
CURRENT_PROJECT = None
SERVER_URL = "http://127.0.0.1:5020"
PROJECT_ROOT = Path(__file__).parent  # C:\SOFT\AI\mindx


# ── State helpers ──────────────────────────────────────────────

def _load_config():
    """Load config.yaml once at startup."""
    global CONFIG
    config_path = PROJECT_ROOT / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f)


def _ensure_project():
    """Raise ValueError if no project is selected."""
    if CURRENT_PROJECT is None:
        raise ValueError("没有选择项目。请先调 list_projects 看可用项目，再调 switch_project")


def _get_project_root() -> Path:
    """Return the filesystem root Path for the currently active project."""
    for proj in CONFIG["projects"]:
        if proj["name"] == CURRENT_PROJECT:
            return Path(proj["root"])
    raise ValueError(f"项目 '{CURRENT_PROJECT}' 配置丢失")


# ── HTTP helpers ───────────────────────────────────────────────

def _http_get(endpoint: str, params: dict = None) -> dict:
    """GET request to Flask server. Returns JSON dict with '_error' key on failure."""
    try:
        r = requests.get(f"{SERVER_URL}{endpoint}", params=params or {}, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        return {"_error": "无法连接 mindx 服务 (127.0.0.1:5020)。请先启动 python server.py"}
    except Exception as e:
        return {"_error": f"请求失败: {e}"}


def _http_post(endpoint: str, data: dict) -> dict:
    """POST request to Flask server."""
    try:
        r = requests.post(f"{SERVER_URL}{endpoint}", json=data, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.ConnectionError:
        return {"_error": "无法连接 mindx 服务 (127.0.0.1:5020)。请先启动 python server.py"}
    except Exception as e:
        return {"_error": f"请求失败: {e}"}


# ── Tool implementations ──────────────────────────────────────

def tool_list_projects() -> dict:
    """列出 config.yaml 中所有配置的项目"""
    names = [p["name"] for p in CONFIG["projects"]]
    return {"projects": names}


def tool_switch_project(name: str) -> dict:
    """切换到指定项目。调用其他工具前必须先选择项目"""
    global CURRENT_PROJECT
    # Validate project exists in config first
    matched = None
    for proj in CONFIG["projects"]:
        if proj["name"] == name:
            matched = proj
            break
    if matched is None:
        available = [p["name"] for p in CONFIG["projects"]]
        return {"_error": f"项目 '{name}' 不存在。可用: {available}"}

    # Sync with Flask server so its active_project stays in sync
    result = _http_post("/api/projects/select", {"name": name})
    if "_error" in result:
        # Flask server unreachable — do NOT set CURRENT_PROJECT, otherwise
        # MCP thinks the switch succeeded but Flask still uses the old project.
        return {"_error": f"项目 '{name}' 本地验证通过，但远程服务切换失败: {result['_error']}"}
    if result.get("success") is False:
        msg = result.get("message") or result.get("error") or str(result)
        return {"_error": f"项目 '{name}' 远程切换失败: {msg}"}

    # Remote switch succeeded — update local state
    CURRENT_PROJECT = name
    return {"project": name, "root": matched["root"]}


def tool_list_files(name_pattern: str = None) -> dict:
    """列出当前项目所有文件"""
    _ensure_project()
    data = _http_get("/api/files")
    if "_error" in data:
        return data
    files = data if isinstance(data, list) else data.get("files", [])
    if name_pattern:
        files = [f for f in files if name_pattern.lower() in (f.get("path", "") or "").lower()]
    return {"files": files, "count": len(files)}


def tool_search_files(pattern: str) -> dict:
    """按名称搜索文件（大小写不敏感）"""
    _ensure_project()
    data = _http_get("/api/files")
    if "_error" in data:
        return data
    files = data if isinstance(data, list) else data.get("files", [])
    results = [f for f in files if pattern.lower() in (f.get("path", "") or "").lower()]
    return {"results": results, "count": len(results)}


def tool_get_file_content(path: str) -> dict:
    """读取文件内容"""
    _ensure_project()
    root = _get_project_root()
    target = (root / path).resolve()
    # Security: ensure resolved path is under project root
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {"_error": f"路径超出项目范围: {path}"}
    if not target.exists():
        return {"_error": f"文件不存在: {path}"}
    if not target.is_file():
        return {"_error": f"不是文件: {path}"}
    MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    file_size = target.stat().st_size
    if file_size > MAX_SIZE:
        return {"_error": f"File too large: {file_size} bytes (max {MAX_SIZE})"}
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = target.read_text(encoding="latin-1")
        except Exception as e:
            return {"_error": f"读取文件失败: {e}"}
    except Exception as e:
        return {"_error": f"读取文件失败: {e}"}
    return {"path": path, "content": content}


def tool_get_file_info(path: str) -> dict:
    """获取文件元数据"""
    _ensure_project()
    data = _http_get(f"/api/file/{path}")
    if "_error" in data:
        return data
    # Clean up: return only the useful metadata fields
    result = {
        "path": data.get("path", path),
        "type": data.get("type"),
        "exists": data.get("exists"),
        "size": data.get("size"),
        "last_modified": data.get("last_modified"),
        "links_count": len(data.get("links", [])),
        "backlinks_count": len(data.get("dependencies", [])),
    }
    return result


def tool_get_references(path: str) -> dict:
    """获取文件的出链（它引用了谁）"""
    _ensure_project()
    data = _http_get(f"/api/file/{path}")
    if "_error" in data:
        return data
    links = data.get("links", [])
    return {"path": path, "references": links, "count": len(links)}


def tool_get_backlinks(path: str) -> dict:
    """获取文件的入链（谁引用了它）"""
    _ensure_project()
    data = _http_get(f"/api/file/{path}/backlinks")
    if "_error" in data:
        return data
    backlinks = data.get("backlinks", [])
    return {"path": path, "backlinks": backlinks, "count": len(backlinks)}


def tool_get_dependency_graph() -> dict:
    """获取当前项目完整依赖图"""
    _ensure_project()
    data = _http_get("/api/graph")
    if "_error" in data:
        return data
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    return {"node_count": len(nodes), "edge_count": len(edges), "nodes": nodes, "edges": edges}


def tool_get_broken_links() -> dict:
    """获取所有断开的内部链接"""
    _ensure_project()
    data = _http_get("/api/broken-links")
    if "_error" in data:
        return data
    return data


def tool_get_sync_suggestions(path: str = None) -> dict:
    """获取同步建议（文件改动后哪些引用需要更新）"""
    _ensure_project()
    # The Flask server uses /api/sync-check (no per-file filtering in current API)
    data = _http_get("/api/sync-check")
    if "_error" in data:
        return data
    suggestions = data if isinstance(data, list) else data.get("suggestions", [])
    if path:
        suggestions = [s for s in suggestions if s.get("changed_file") == path or s.get("target") == path]
    return {"suggestions": suggestions, "count": len(suggestions)}


def tool_get_change_log(limit: int = 50) -> dict:
    """获取最近文件变更记录"""
    _ensure_project()
    data = _http_get("/api/changes", {"limit": limit})
    if "_error" in data:
        return data
    changes = data if isinstance(data, list) else data.get("changes", [])
    return {"changes": changes, "count": len(changes)}


def tool_list_silenced_links() -> dict:
    """获取当前项目所有已静默的断链目标"""
    _ensure_project()
    data = _http_get("/api/silenced-links")
    if "_error" in data:
        return data
    return {"silenced_links": data if isinstance(data, list) else data.get("silenced_links", [])}


def tool_silence_link(target: str) -> dict:
    """静默一个断链目标（将其从断链列表中隐藏）"""
    _ensure_project()
    data = _http_post("/api/silenced-links/silence", {"target": target})
    if "_error" in data:
        return data
    if not data.get("success"):
        return {"_error": data.get("error", "操作失败")}
    return {"success": True, "target": target, "added": data.get("added", True)}


def tool_unsilence_link(target: str) -> dict:
    """取消静默一个断链目标"""
    _ensure_project()
    data = _http_post("/api/silenced-links/unsilence", {"target": target})
    if "_error" in data:
        return data
    if not data.get("success"):
        return {"_error": data.get("error", "操作失败")}
    return {"success": True, "target": target, "removed": data.get("removed", True)}


def tool_rename_file(path: str, new_name: str) -> dict:
    """重命名文件并自动更新所有引用"""
    _ensure_project()
    # Step 1: preview
    preview = _http_post("/api/file/rename-preview", {"path": path, "new_name": new_name})
    if "_error" in preview:
        return preview
    if not preview.get("success"):
        return {"_error": preview.get("error", "预览失败")}
    # Step 2: execute with new_path from preview
    new_path = preview.get("new_path")
    affected = preview.get("affected_count", 0)
    execute = _http_post("/api/file/rename-execute", {"path": path, "new_path": new_path})
    if "_error" in execute:
        return execute
    # Merge results
    result = {
        "success": execute.get("success", False),
        "old_path": execute.get("old_path", path),
        "new_path": execute.get("new_path", new_path),
        "updated_files": execute.get("updated_files", []),
        "affected_count": affected,
    }
    return result


# ── Tool map ───────────────────────────────────────────────────

TOOL_MAP = {
    "list_projects": tool_list_projects,
    "switch_project": tool_switch_project,
    "list_files": tool_list_files,
    "search_files": tool_search_files,
    "get_file_content": tool_get_file_content,
    "get_file_info": tool_get_file_info,
    "get_references": tool_get_references,
    "get_backlinks": tool_get_backlinks,
    "get_dependency_graph": tool_get_dependency_graph,
    "get_broken_links": tool_get_broken_links,
    "get_sync_suggestions": tool_get_sync_suggestions,
    "get_change_log": tool_get_change_log,
    "rename_file": tool_rename_file,
    "list_silenced_links": tool_list_silenced_links,
    "silence_link": tool_silence_link,
    "unsilence_link": tool_unsilence_link,
}


# ── MCP Server ─────────────────────────────────────────────────

async def main():
    _load_config()

    server = Server("mindx")

    @server.list_tools()
    async def handle_list_tools():
        return [
            Tool(
                name="list_projects",
                description="列出 config.yaml 中所有配置的项目",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="switch_project",
                description="切换到指定项目。调用其他工具前必须先选择项目",
                inputSchema={
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            ),
            Tool(
                name="list_files",
                description="列出当前项目所有文件",
                inputSchema={
                    "type": "object",
                    "properties": {"name_pattern": {"type": "string"}},
                },
            ),
            Tool(
                name="search_files",
                description="按名称搜索文件（大小写不敏感）",
                inputSchema={
                    "type": "object",
                    "properties": {"pattern": {"type": "string"}},
                    "required": ["pattern"],
                },
            ),
            Tool(
                name="get_file_content",
                description="读取文件内容",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            Tool(
                name="get_file_info",
                description="获取文件元数据",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            Tool(
                name="get_references",
                description="获取文件的出链（它引用了谁）",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            Tool(
                name="get_backlinks",
                description="获取文件的入链（谁引用了它）",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            ),
            Tool(
                name="get_dependency_graph",
                description="获取当前项目完整依赖图",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_broken_links",
                description="获取所有断开的内部链接",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_sync_suggestions",
                description="获取同步建议（文件改动后哪些引用需要更新）",
                inputSchema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            ),
            Tool(
                name="get_change_log",
                description="获取最近文件变更记录",
                inputSchema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                },
            ),
            Tool(
                name="list_silenced_links",
                description="获取当前项目所有已静默的断链目标",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="silence_link",
                description="静默一个断链目标，将其从全局断链列表中隐藏",
                inputSchema={
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ["target"],
                },
            ),
            Tool(
                name="unsilence_link",
                description="取消静默一个断链目标",
                inputSchema={
                    "type": "object",
                    "properties": {"target": {"type": "string"}},
                    "required": ["target"],
                },
            ),
            Tool(
                name="rename_file",
                description="重命名文件并自动更新所有引用",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "new_name": {"type": "string"},
                    },
                    "required": ["path", "new_name"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        try:
            func = TOOL_MAP.get(name)
            if func is None:
                return [TextContent(type="text", text=json.dumps(
                    {"_error": f"未知工具: {name}"}, ensure_ascii=False
                ))]
            result = func(**arguments)
            return [TextContent(type="text", text=json.dumps(
                result, ensure_ascii=False, indent=2, default=str
            ))]
        except ValueError as e:
            return [TextContent(type="text", text=json.dumps(
                {"_error": str(e)}, ensure_ascii=False
            ))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps(
                {"_error": f"工具执行失败: {e}"}, ensure_ascii=False
            ))]

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
