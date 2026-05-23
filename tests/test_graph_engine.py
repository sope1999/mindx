"""Unit tests for graph_engine.GraphEngine — core methods only."""

import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from graph_engine import GraphEngine, ChangeEvent, SyncSuggestion


# ── Helpers ──────────────────────────────────────────────────

def _engine(root: Path) -> GraphEngine:
    """Create an engine and run scan_all so data is populated."""
    eng = GraphEngine(root)
    eng.scan_all()
    return eng


# ── scan_all + get_stats ────────────────────────────────────

class TestScanAll:
    def test_scan_all_finds_files(self, project_root):
        eng = _engine(project_root)
        assert eng.get_stats()["total_files"] > 0

    def test_scan_all_builds_edges(self, project_root):
        eng = _engine(project_root)
        # MEMORY.md links to TOOLS.md and urls.md — at least one edge must exist
        assert eng.graph.number_of_edges() > 0

    def test_get_stats_after_scan(self, project_root):
        eng = _engine(project_root)
        stats = eng.get_stats()
        # Required keys
        for key in ("total_files", "total_edges", "total_nodes_graph",
                     "file_types", "recent_changes"):
            assert key in stats
        assert isinstance(stats["file_types"], dict)
        assert stats["recent_changes"] == 0  # no updates yet

    def test_scan_all_ignores_patterns(self, project_root):
        # Create a file inside .git/ — must be ignored
        git_dir = project_root / ".git"
        git_dir.mkdir(exist_ok=True)
        (git_dir / "test.md").write_text("# hidden", encoding="utf-8")
        eng = _engine(project_root)
        assert ".git/test.md" not in eng.files


# ── update_file ─────────────────────────────────────────────

class TestUpdateFile:
    def test_update_file_modified(self, project_root):
        eng = _engine(project_root)
        # Modify MEMORY.md content
        (project_root / "MEMORY.md").write_text(
            "# Memory v2\n\n[TOOLS.md](TOOLS.md)", encoding="utf-8"
        )
        eng.update_file("MEMORY.md", event="modified")
        # File should still be in graph and re-parsed
        assert "MEMORY.md" in eng.files

    def test_update_file_created(self, project_root):
        eng = _engine(project_root)
        new_file = project_root / "NEW.md"
        new_file.write_text("# New file\n\n[TOOLS.md](TOOLS.md)", encoding="utf-8")
        eng.update_file("NEW.md", event="created")
        assert "NEW.md" in eng.files


# ── get_graph_data ──────────────────────────────────────────

class TestGetGraphData:
    def test_get_graph_data_format(self, project_root):
        eng = _engine(project_root)
        data = eng.get_graph_data()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_get_graph_data_node_attrs(self, project_root):
        eng = _engine(project_root)
        data = eng.get_graph_data()
        # Every node should have required attributes
        for node in data["nodes"]:
            assert "id" in node
            # nodes carry 'group' (maps to type) from vis.js output
            # but internal graph nodes store 'type'; check at least one has group
        # At least one node should have a group (type)
        groups = [n.get("group") for n in data["nodes"] if "group" in n]
        assert len(groups) > 0


# ── get_dependencies ────────────────────────────────────────

class TestGetDependencies:
    def test_get_dependencies_has_references(self, project_root):
        eng = _engine(project_root)
        deps = eng.get_dependencies("MEMORY.md")
        # MEMORY.md links to TOOLS.md and urls.md
        assert "references" in deps
        ref_paths = [r["path"] for r in deps["references"]]
        assert "TOOLS.md" in ref_paths

    def test_get_dependencies_referenced_by(self, project_root):
        eng = _engine(project_root)
        deps = eng.get_dependencies("TOOLS.md")
        # MEMORY.md → TOOLS.md, so TOOLS.md is referenced_by MEMORY.md
        assert "referenced_by" in deps
        by_paths = [r["path"] for r in deps["referenced_by"]]
        assert "MEMORY.md" in by_paths


# ── _should_ignore ──────────────────────────────────────────

class TestShouldIgnore:
    def test_should_ignore_dot_git(self, project_root):
        eng = GraphEngine(project_root)
        assert eng._should_ignore(".git/config")
        assert eng._should_ignore(".git/test.md")

    def test_should_ignore_pyc(self, project_root):
        eng = GraphEngine(project_root)
        assert eng._should_ignore("foo.pyc")
        assert eng._should_ignore("sub/dir/bar.pyc")

    def test_should_ignore_warning_dir(self, project_root):
        eng = GraphEngine(project_root)
        assert eng._should_ignore("warning/notes.md")
        # Just "warning" without slash should also match (starts-with logic)
        assert eng._should_ignore("warning")


# ── get_history / history persistence ───────────────────────

class TestHistory:
    def test_history_empty_after_scan(self, project_root):
        eng = _engine(project_root)
        hist = eng.get_history()
        # scan_all does not produce history entries
        assert hist["count"] == 0

    def test_history_after_update(self, project_root):
        eng = _engine(project_root)
        (project_root / "MEMORY.md").write_text(
            "# Updated\n\n[TOOLS.md](TOOLS.md)", encoding="utf-8"
        )
        eng.update_file("MEMORY.md", event="modified")
        hist = eng.get_history()
        assert hist["count"] > 0

    def test_history_filter_by_type(self, project_root):
        eng = _engine(project_root)
        (project_root / "MEMORY.md").write_text(
            "# Updated\n\n[TOOLS.md](TOOLS.md)", encoding="utf-8"
        )
        eng.update_file("MEMORY.md", event="modified")
        changes = eng.get_history(type_filter="changes")
        sync = eng.get_history(type_filter="sync")
        # "changes" filter should only return type=="change"
        for e in changes["history"]:
            assert e["type"] == "change"
        for e in sync["history"]:
            assert e["type"] == "sync"

    def test_history_prunes_old(self, project_root):
        eng = _engine(project_root)
        # Manually inject an old entry (> 3 days)
        old_ts = (datetime.now() - timedelta(days=4)).isoformat()
        eng._history.append({"timestamp": old_ts, "type": "change",
                             "file": "OLD.md", "event": "modified"})
        # _save_history_entry auto-prunes; call it to trigger pruning
        eng._save_history_entry({
            "timestamp": datetime.now().isoformat(),
            "type": "change",
            "file": "MEMORY.md",
            "event": "modified",
        })
        # Old entry should be gone
        for e in eng._history:
            assert eng._parse_ts(e.get("timestamp", "")) >= (
                datetime.now().timestamp() - 3 * 86400
            )


# ── Thread safety (bug #20) ────────────────────────────────

class TestThreadSafety:
    def test_lock_exists(self, project_root):
        eng = GraphEngine(project_root)
        assert hasattr(eng, "_lock")
        assert isinstance(eng._lock, type(threading.RLock()))
