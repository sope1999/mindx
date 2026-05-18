"""mindx server: Flask + SocketIO + multi-project watchdog integration."""

import os
import sys
import json
import time
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

from config import HOST, load_config, save_config, add_project, remove_project, get_project_config
from graph_engine import GraphEngine
from watcher import FileWatcher
from parser import FileInfo

# ── Config ──────────────────────────────────────────────────
_config = load_config()
PORT = _config.get("port", 5020)

# ── App setup ───────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "mindx-memory-index-tracker"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Multi-project state ────────────────────────────────────
engines: dict = {}       # project_name -> GraphEngine
watchers: dict = {}      # project_name -> FileWatcher
active_project: str = None


def _get_active_engine() -> GraphEngine:
    """Return the engine for the currently active project."""
    if active_project is None or active_project not in engines:
        raise RuntimeError("No active project selected")
    return engines[active_project]


def _get_active_watcher() -> FileWatcher:
    """Return the watcher for the currently active project."""
    if active_project is None or active_project not in watchers:
        raise RuntimeError("No active project selected")
    return watchers[active_project]


def _init_project(name: str, root: Path) -> GraphEngine:
    """Initialize engine for a project. Creates engine+watcher if not yet done."""
    if name not in engines:
        engines[name] = GraphEngine(root)
    return engines[name]


# ── File watcher callback factory ───────────────────────────
def _make_on_change(project_name: str):
    """Return a callback that emits socketio events for a specific project."""
    def on_file_change(rel_path: str, event: str):
        engine = engines.get(project_name)
        if engine is None:
            return
        suggestions = engine.update_file(rel_path, event)
        socketio.emit("file_changed", {
            "file": rel_path,
            "event": event,
            "timestamp": datetime.now().isoformat(),
        })
        if suggestions:
            socketio.emit("sync_needed", {
                "file": rel_path,
                "event": event,
                "suggestions": [
                    {"target": s.target, "reason": s.reason, "severity": s.severity, "action": s.action}
                    for s in suggestions
                ],
            })
    return on_file_change


# ── Routes ──────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the dashboard."""
    return render_template("index.html")


# ── Project management ──────────────────────────────────────
@app.route("/api/projects")
def api_projects():
    """List all configured projects."""
    projects = []
    for proj in _config.get("projects", []):
        root = Path(proj["root"])
        projects.append({
            "name": proj["name"],
            "root": proj["root"],
            "exists_on_disk": root.exists() and root.is_dir(),
        })
    return jsonify(projects)


@app.route("/api/projects/add", methods=["POST"])
def api_project_add():
    """Add a new project to config."""
    data = request.get_json(force=True)
    root_str = data.get("root", "").strip()
    if not root_str:
        return jsonify({"success": False, "error": "root is required"}), 400

    root_path = Path(root_str)
    if not root_path.exists() or not root_path.is_dir():
        return jsonify({"success": False, "error": f"Path does not exist: {root_str}"}), 400

    # Extract folder name as default project name
    name = data.get("name") or root_path.name
    proj = add_project(_config, name, str(root_path.resolve()))
    save_config(_config)

    return jsonify({"success": True, "project": proj})


@app.route("/api/projects/remove", methods=["POST"])
def api_project_remove():
    """Remove a project from config."""
    global active_project
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "name is required"}), 400

    # Stop watcher if this project is active
    if name == active_project and name in watchers:
        watchers[name].stop()

    removed = remove_project(_config, name)
    if removed:
        # Clean up in-memory state
        watchers.pop(name, None)
        engines.pop(name, None)
        if name == active_project:
            active_project = None
        save_config(_config)

    return jsonify({"success": removed})


@app.route("/api/projects/select", methods=["POST"])
def api_project_select():
    """Select (activate) a project."""
    global active_project
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "name is required"}), 400

    proj = get_project_config(_config, name)
    if not proj:
        return jsonify({"success": False, "error": f"Project not found: {name}"}), 404

    root = Path(proj["root"])
    if not root.exists():
        return jsonify({"success": False, "error": f"Project root does not exist: {root}"}), 400

    # Stop current watcher
    if active_project and active_project in watchers:
        watchers[active_project].stop()

    # If project already seen, restart its watcher; otherwise init fresh
    if name in watchers:
        engine = _init_project(name, root)
        watchers[name].restart(root, _make_on_change(name))
    else:
        engine = _init_project(name, root)
        engine.scan_all()
        _load_externals(name, engine)
        w = FileWatcher(root, on_change=_make_on_change(name))
        w.start()
        watchers[name] = w

    active_project = name
    stats = engines[name].get_stats()
    graph_data = engines[name].get_graph_data()

    # Build file list for the frontend
    file_list = []
    for path, info in engines[name].files.items():
        file_list.append({
            "path": path,
            "type": info.file_type,
            "exists": info.exists,
            "size": info.size,
            "last_modified": info.last_modified.isoformat() if info.last_modified else None,
            "link_count": len(info.links),
            "backlink_count": len(
                [s for s, _ in engines[name].graph.in_edges(path)]
            ),
        })

    socketio.emit("project_switched", {
        "name": name,
        "root": proj["root"],
        "files": file_list,
        "graph": graph_data,
    })

    return jsonify({
        "success": True,
        "stats": stats,
        "file_count": len(file_list),
    })


# ── Status ──────────────────────────────────────────────────
@app.route("/api/status")
def api_status():
    """Server status."""
    watching = False
    project_root = None
    stats = {}

    if active_project:
        w = watchers.get(active_project)
        eng = engines.get(active_project)
        watching = w.is_running if w else False
        if eng:
            stats = eng.get_stats()
        proj = get_project_config(_config, active_project)
        project_root = proj["root"] if proj else None

    return jsonify({
        "running": True,
        "project_name": active_project,
        "project_root": project_root,
        "watching": watching,
        "stats": stats,
    })


@app.route("/api/files")
def api_files():
    """List all tracked files for active project."""
    if active_project is None:
        return jsonify([])
    engine = engines.get(active_project)
    if engine is None:
        return jsonify([])

    files = []
    for path, info in engine.files.items():
        files.append({
            "path": path,
            "type": info.file_type,
            "exists": info.exists,
            "size": info.size,
            "last_modified": info.last_modified.isoformat() if info.last_modified else None,
            "link_count": len(info.links),
            "backlink_count": len(
                [s for s, _ in engine.graph.in_edges(path)]
            ),
        })
    return jsonify(files)


@app.route("/api/file/<path:file_path>")
def api_file_detail(file_path: str):
    """Get details for a specific file in active project."""
    if active_project is None:
        return jsonify({"path": file_path, "error": "No active project"}), 400

    engine = engines.get(active_project)
    if engine is None:
        return jsonify({"path": file_path, "error": "Engine not ready"}), 500

    deps = engine.get_dependencies(file_path)
    info = engine.files.get(file_path)

    result = {
        "path": file_path,
        "dependencies": deps,
    }

    if info:
        result["type"] = info.file_type
        result["exists"] = info.exists
        result["size"] = info.size
        result["abs_path"] = str(info.abs_path)
        result["last_modified"] = info.last_modified.isoformat() if info.last_modified else None
        result["links"] = [
            {"target": l.target, "anchor": l.anchor_text, "context": l.context[:60]}
            for l in info.links
        ]

    # Check for broken links (only within project)
    proj = get_project_config(_config, active_project)
    project_root = Path(proj["root"]) if proj else Path(".")
    issues = []
    for link in (info.links if info else []):
        if link.is_external:
            continue  # skip external link validation
        target_path = link.target
        if not (project_root / target_path).exists():
            issues.append({
                "type": "broken_link",
                "target": target_path,
                "detail": f"链接目标不存在: {target_path}",
            })
    result["issues"] = issues

    return jsonify(result)


@app.route("/api/graph")
def api_graph():
    """Get full dependency graph data for active project."""
    if active_project is None:
        return jsonify({"nodes": [], "edges": []})
    engine = engines.get(active_project)
    if engine is None:
        return jsonify({"nodes": [], "edges": []})
    return jsonify(engine.get_graph_data())


@app.route("/api/scan")
def api_scan():
    """Trigger full re-scan of active project."""
    if active_project is None:
        return jsonify({"error": "No active project"}), 400
    engine = engines.get(active_project)
    if engine is None:
        return jsonify({"error": "Engine not ready"}), 500

    engine.scan_all()
    stats = engine.get_stats()
    return jsonify(stats)


@app.route("/api/changes")
def api_changes():
    """Get recent change log for active project."""
    if active_project is None:
        return jsonify([])
    engine = engines.get(active_project)
    if engine is None:
        return jsonify([])

    limit = request.args.get("limit", 50, type=int)
    changes = engine.change_log[-limit:]
    return jsonify([
        {
            "timestamp": c.timestamp.isoformat(),
            "file": c.file,
            "event": c.event,
            "suggestion_count": len(c.suggestions),
        }
        for c in reversed(changes)
    ])


@app.route("/api/sync-check")
def api_sync_check():
    """Run a full sync check on all files in active project."""
    if active_project is None:
        return jsonify([])
    engine = engines.get(active_project)
    if engine is None:
        return jsonify([])

    all_suggestions = []

    for file_path in engine.files:
        for rule_type in ["modified", "created"]:
            suggestions = engine._generate_suggestions(file_path, rule_type)
            for s in suggestions:
                all_suggestions.append({
                    "changed_file": s.changed_file,
                    "target": s.target,
                    "reason": s.reason,
                    "action": s.action,
                    "severity": s.severity,
                })

    return jsonify(all_suggestions)


# ── File picker (system dialog) ─────────────────────────────────
@app.route("/api/pick-folder", methods=["POST"])
def api_pick_folder():
    """Open system folder picker and return selected path."""
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="选择文件夹")
        root.destroy()
        return jsonify({"path": path if path else None})
    except Exception as e:
        return jsonify({"path": None, "error": str(e)})


@app.route("/api/pick-file", methods=["POST"])
def api_pick_file():
    """Open system file picker and return selected path."""
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(title="选择文件", filetypes=[("Markdown", "*.md"), ("All", "*.*")])
        root.destroy()
        return jsonify({"path": path if path else None})
    except Exception as e:
        return jsonify({"path": None, "error": str(e)})


# ── External file management ────────────────────────────────────
@app.route("/api/external/add", methods=["POST"])
def api_external_add():
    """Add an external file/folder to the active project's graph."""
    if active_project is None:
        return jsonify({"success": False, "error": "No active project"}), 400
    data = request.get_json(force=True)
    ext_path = data.get("path", "").strip()
    if not ext_path:
        return jsonify({"success": False, "error": "path required"}), 400

    p = Path(ext_path)
    engine = engines.get(active_project)
    added = []

    if p.is_dir():
        for md in p.rglob("*.md"):
            abs_path = str(md.resolve()).replace("\\", "/")
            if abs_path not in engine.graph:
                st = md.stat()
                engine.graph.add_node(abs_path, **{
                    "type": "external", "exists": True,
                    "label": md.name, "is_external": True,
                    "mounted": True,
                    "abs_path": abs_path,
                    "size": st.st_size,
                    "last_modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                })
                engine.files[abs_path] = FileInfo(
                    path=abs_path, abs_path=md, file_type="external",
                    exists=True, size=st.st_size,
                    last_modified=datetime.fromtimestamp(st.st_mtime),
                )
                added.append(abs_path)
    elif p.is_file():
        abs_path = str(p.resolve()).replace("\\", "/")
        if abs_path not in engine.graph:
            st = p.stat() if p.exists() else None
            engine.graph.add_node(abs_path, **{
                "type": "external", "exists": p.exists(),
                "label": p.name, "is_external": True,
                "mounted": True,
                "abs_path": abs_path,
                "size": st.st_size if st else 0,
                "last_modified": datetime.fromtimestamp(st.st_mtime).isoformat() if st else None,
            })
            engine.files[abs_path] = FileInfo(
                path=abs_path, abs_path=p, file_type="external",
                exists=p.exists(), size=st.st_size if st else 0,
                last_modified=datetime.fromtimestamp(st.st_mtime) if st else None,
            )
            added.append(abs_path)

    if added:
        _persist_external(ext_path)
    return jsonify({"success": True, "added": added, "count": len(added)})


def _persist_external(ext_path: str):
    """Save an external path to the active project's config."""
    proj = get_project_config(_config, active_project)
    if proj is None:
        return
    proj.setdefault("external_paths", [])
    normalized = str(Path(ext_path).resolve()).replace("\\", "/")
    if normalized not in proj["external_paths"]:
        proj["external_paths"].append(normalized)
        save_config(_config)


def _unpersist_external(ext_path: str):
    """Remove an external path from the active project's config."""
    proj = get_project_config(_config, active_project)
    if proj is None:
        return
    normalized = str(Path(ext_path).resolve()).replace("\\", "/")
    paths = proj.get("external_paths", [])
    if normalized in paths:
        paths.remove(normalized)
        save_config(_config)


@app.route("/api/external/remove", methods=["POST"])
def api_external_remove():
    """Remove an external file from the graph."""
    if active_project is None:
        return jsonify({"success": False}), 400
    data = request.get_json(force=True)
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"success": False}), 400

    engine = engines.get(active_project)
    if path in engine.graph:
        engine.graph.remove_node(path)
        engine.files.pop(path, None)
        _unpersist_external(path)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "not found"})


@app.route("/api/external/list")
def api_external_list():
    """List all external files in the active project's graph."""
    if active_project is None:
        return jsonify([])
    engine = engines.get(active_project)
    if engine is None:
        return jsonify([])
    externals = []
    for nid, ndata in engine.graph.nodes(data=True):
        if ndata.get("is_external"):
            externals.append({
                "path": nid,
                "label": ndata.get("label", Path(nid).name),
                "exists": ndata.get("exists", False),
            })
    return jsonify(externals)


# ── Startup ─────────────────────────────────────────────────
def init_engine():
    """Initial scan of the first configured project (if any)."""
    global active_project
    projects = _config.get("projects", [])
    if not projects:
        print("[mindx] No projects configured. Use /api/projects/add to add one.")
        return

    # Auto-select first project
    first = projects[0]
    name = first["name"]
    root = Path(first["root"])
    print(f"[mindx] Scanning {root} ...")

    engine = _init_project(name, root)
    engine.scan_all()
    _load_externals(name, engine)
    stats = engine.get_stats()
    print(f"[mindx] Found {stats['total_files']} files, {stats['total_edges']} edges")

    w = FileWatcher(root, on_change=_make_on_change(name))
    w.start()
    watchers[name] = w
    active_project = name


def _load_externals(project_name: str, engine: GraphEngine):
    """Re-mount persisted external paths for a project."""
    proj = get_project_config(_config, project_name)
    if not proj:
        return
    for ext_path in proj.get("external_paths", []):
        p = Path(ext_path)
        if not p.exists():
            continue
        if p.is_dir():
            for md in p.rglob("*.md"):
                abs_path = str(md.resolve()).replace("\\", "/")
                if abs_path in engine.graph:
                    continue
                st = md.stat()
                engine.graph.add_node(abs_path, **{
                    "type": "external", "exists": True,
                    "label": md.name, "is_external": True,
                    "mounted": True,
                    "abs_path": abs_path,
                    "size": st.st_size,
                    "last_modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                })
                engine.files[abs_path] = FileInfo(
                    path=abs_path, abs_path=md, file_type="external",
                    exists=True, size=st.st_size,
                    last_modified=datetime.fromtimestamp(st.st_mtime),
                )
        elif p.is_file():
            abs_path = str(p.resolve()).replace("\\", "/")
            if abs_path in engine.graph:
                continue
            st = p.stat()
            engine.graph.add_node(abs_path, **{
                "type": "external", "exists": True,
                "label": p.name, "is_external": True,
                "mounted": True,
                "abs_path": abs_path,
                "size": st.st_size,
                "last_modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
            })
            engine.files[abs_path] = FileInfo(
                path=abs_path, abs_path=p, file_type="external",
                exists=True, size=st.st_size,
                last_modified=datetime.fromtimestamp(st.st_mtime),
            )


# ── External file polling ────────────────────────────────────
POLL_INTERVAL = 30  # seconds between external file checks

def _poll_external_files():
    """Background thread: periodically check external file mtimes."""
    while True:
        time.sleep(POLL_INTERVAL)
        try:
            if active_project is None:
                continue
            engine = engines.get(active_project)
            if engine is None:
                continue
            changed = engine.poll_external_files()
            for c in changed:
                socketio.emit("external_changed", {
                    "file": c["path"],
                    "label": c["label"],
                    "prev_exists": c["prev_exists"],
                    "now_exists": c["now_exists"],
                    "prev_mtime": c["prev_mtime"],
                    "now_mtime": c["now_mtime"],
                })
        except Exception:
            pass


@app.route("/api/positions/save", methods=["POST"])
def api_positions_save():
    """Save graph layout positions for active project."""
    if active_project is None:
        return jsonify({"success": False}), 400
    proj = get_project_config(_config, active_project)
    if not proj:
        return jsonify({"success": False}), 400
    data = request.get_json(force=True)
    key = data.get("key", "")
    positions = data.get("positions", {})
    if not key:
        return jsonify({"success": False}), 400
    proj.setdefault("positions", {})
    proj["positions"][key] = positions
    save_config(_config)
    return jsonify({"success": True})


@app.route("/api/positions/load")
def api_positions_load():
    """Load graph layout positions for active project."""
    if active_project is None:
        return jsonify({})
    proj = get_project_config(_config, active_project)
    if not proj:
        return jsonify({})
    return jsonify(proj.get("positions", {}))


# ── Settings ──────────────────────────────────────────────────
@app.route("/api/settings/load")
def api_settings_load():
    if active_project is None:
        return jsonify({})
    proj = get_project_config(_config, active_project)
    if not proj:
        return jsonify({})
    return jsonify({
        "file_classes": proj.get("file_classes", {}),
        "excluded_dirs": proj.get("excluded_dirs", []),
        "display_mode": proj.get("display_mode", "full"),
        "ref_roots": proj.get("ref_roots", []),
        "active_root": proj.get("active_root", None),
    })


@app.route("/api/settings/save", methods=["POST"])
def api_settings_save():
    if active_project is None:
        return jsonify({"success": False}), 400
    proj = get_project_config(_config, active_project)
    if not proj:
        return jsonify({"success": False}), 400
    data = request.get_json(force=True)
    for key in ("file_classes", "excluded_dirs", "display_mode", "ref_roots", "active_root"):
        if key in data:
            proj[key] = data[key]
    save_config(_config)
    return jsonify({"success": True})


def run_server():
    """Start the mindx server."""
    init_engine()

    # Start external file polling thread
    poll_thread = threading.Thread(target=_poll_external_files, daemon=True)
    poll_thread.start()

    if active_project:
        proj = get_project_config(_config, active_project)
        print(f"[mindx] Watching {proj['root']}")
    print(f"[mindx] Dashboard: http://{HOST}:{PORT}")

    try:
        socketio.run(app, host=HOST, port=PORT, debug=False, allow_unsafe_werkzeug=True)
    except OSError as e:
        if "Address already in use" in str(e) or "address already in use" in str(e).lower():
            print(f"\n[mindx] ERROR: Port {PORT} is already in use.")
            print(f"[mindx] Please change the port in config.yaml and try again.")
        else:
            print(f"\n[mindx] ERROR: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[mindx] Shutting down...")
    finally:
        for w in watchers.values():
            w.stop()


if __name__ == "__main__":
    run_server()
