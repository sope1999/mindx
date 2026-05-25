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


# ── excluded_paths ────────────────────────────────────────────

class TestExcludedPaths:
    """Tests for project-level excluded_dirs / excluded_paths."""

    def test_excluded_dir_not_scanned(self, project_root):
        """Files under an excluded directory must not appear in engine.files."""
        # Create a file in memory/secrets/ and exclude "memory/secrets"
        secrets_dir = project_root / "memory" / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        (secrets_dir / "private.md").write_text("# Secret\n", encoding="utf-8")
        eng = GraphEngine(project_root, excluded_paths=["memory/secrets"])
        eng.scan_all()
        assert "memory/secrets/private.md" not in eng.files

    def test_excluded_file_not_scanned(self, project_root):
        """An individually excluded file must not appear in engine.files."""
        eng = GraphEngine(project_root, excluded_paths=["urls.md"])
        eng.scan_all()
        assert "urls.md" not in eng.files
        # Other files should still be present
        assert "MEMORY.md" in eng.files

    def test_non_excluded_file_is_scanned(self, project_root):
        """Files outside excluded_dirs must still be scanned normally."""
        eng = GraphEngine(project_root, excluded_paths=["memory/secrets"])
        eng.scan_all()
        assert "MEMORY.md" in eng.files
        assert "TOOLS.md" in eng.files
        assert "memory/tools/claude-code.md" in eng.files

    def test_excluded_dir_not_in_graph(self, project_root):
        """Excluded files must not appear as graph nodes."""
        secrets_dir = project_root / "memory" / "secrets"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        (secrets_dir / "private.md").write_text("# Secret\n", encoding="utf-8")
        eng = GraphEngine(project_root, excluded_paths=["memory/secrets"])
        eng.scan_all()
        assert not eng.graph.has_node("memory/secrets/private.md")

    def test_update_file_ignores_excluded(self, project_root):
        """update_file must not add a file that's in excluded_paths."""
        eng = GraphEngine(project_root, excluded_paths=["urls.md"])
        eng.scan_all()
        # Try to update the excluded file
        result = eng.update_file("urls.md", event="modified")
        # Should return empty list (skipped)
        assert result == []
        assert "urls.md" not in eng.files

    def test_should_ignore_with_excluded_paths(self, project_root):
        """_should_ignore must match excluded_paths correctly."""
        eng = GraphEngine(project_root, excluded_paths=["memory/secrets", "draft.md"])
        assert eng._should_ignore("memory/secrets/private.md")
        assert eng._should_ignore("memory/secrets/nested/deep.md")
        assert eng._should_ignore("draft.md")
        # Non-excluded paths should not be ignored
        assert not eng._should_ignore("MEMORY.md")
        assert not eng._should_ignore("memory/tools/claude-code.md")

    def test_no_excluded_paths_backward_compat(self, project_root):
        """Projects without excluded_dirs must work unchanged."""
        eng = GraphEngine(project_root)
        eng.scan_all()
        assert "MEMORY.md" in eng.files
        assert eng.get_stats()["total_files"] > 0


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


# ── file:/// external references ─────────────────────────────

class TestFileUriExternal:
    """Tests for file:/// link handling with external_paths."""

    def _make_ext_dir(self, tmp_path, with_links=True):
        """Create a temp directory with a .md file, return (dir_path, file_path)."""
        ext_dir = tmp_path / "external_lib"
        ext_dir.mkdir()
        doc = ext_dir / "readme.md"
        if with_links:
            doc.write_text("# External Doc\n\n[Tools](TOOLS.md)", encoding="utf-8")
        else:
            doc.write_text("# External Doc\n\nNo links here.", encoding="utf-8")
        return ext_dir, doc

    def test_file_uri_mounted_creates_parsed_node(self, project_root, tmp_path):
        """file:/// target within external_paths → mounted node, parsed, edge added."""
        ext_dir, doc = self._make_ext_dir(tmp_path, with_links=False)

        # Create a project file that links to the external file via file:///
        file_uri = f"file:///{str(doc).replace(chr(92), '/')}"
        (project_root / "linker.md").write_text(
            f"[Ext]({file_uri})", encoding="utf-8"
        )

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        eng.scan_all()

        doc_path = str(doc).replace("\\", "/")
        graph_data = eng.get_graph_data()

        # Check the external node exists in graph
        external_nodes = [n for n in graph_data["nodes"] if n.get("is_external")]
        assert len(external_nodes) == 1
        ext_node = external_nodes[0]
        assert ext_node["mounted"] is True
        assert ext_node["absent"] is False

        # Check edge from linker.md to the external node
        ext_edges = [e for e in graph_data["edges"] if e.get("is_external")]
        assert len(ext_edges) == 1

        # Check the external file was added to files
        assert doc_path in eng.files

    def test_file_uri_unmounted_creates_leaf_node(self, project_root, tmp_path):
        """file:/// target outside external_paths → unmounted leaf node."""
        ext_dir, doc = self._make_ext_dir(tmp_path)

        file_uri = f"file:///{str(doc).replace(chr(92), '/')}"
        (project_root / "linker.md").write_text(
            f"[Ext]({file_uri})", encoding="utf-8"
        )

        # external_paths does NOT include ext_dir
        eng = GraphEngine(project_root, external_paths=[])
        eng.scan_all()

        graph_data = eng.get_graph_data()
        external_nodes = [n for n in graph_data["nodes"] if n.get("is_external")]
        assert len(external_nodes) == 1
        ext_node = external_nodes[0]
        assert ext_node["mounted"] is False
        assert ext_node["absent"] is False

        # Edge still created
        ext_edges = [e for e in graph_data["edges"] if e.get("is_external")]
        assert len(ext_edges) == 1

    def test_file_uri_broken_missing_target(self, project_root):
        """file:/// target that doesn't exist → broken external ref."""
        (project_root / "linker.md").write_text(
            "[Missing](file:///C:/nonexistent/path/file.md)", encoding="utf-8"
        )

        eng = GraphEngine(project_root, external_paths=[])
        eng.scan_all()

        graph_data = eng.get_graph_data()
        external_nodes = [n for n in graph_data["nodes"] if n.get("is_external")]
        assert len(external_nodes) == 1
        ext_node = external_nodes[0]
        assert ext_node["mounted"] is False
        assert ext_node["absent"] is True

        # Edge still created (broken ref)
        ext_edges = [e for e in graph_data["edges"] if e.get("is_external")]
        assert len(ext_edges) == 1

    def test_file_uri_mounted_within_nested_path(self, project_root, tmp_path):
        """file:/// target in a subdir of an external_path → still mounted."""
        ext_dir, doc = self._make_ext_dir(tmp_path)
        sub = ext_dir / "sub"
        sub.mkdir()
        sub_doc = sub / "nested.md"
        sub_doc.write_text("# Nested external", encoding="utf-8")

        file_uri = f"file:///{str(sub_doc).replace(chr(92), '/')}"
        (project_root / "linker.md").write_text(
            f"[Nested]({file_uri})", encoding="utf-8"
        )

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        eng.scan_all()

        graph_data = eng.get_graph_data()
        external_nodes = [n for n in graph_data["nodes"] if n.get("is_external")]
        assert len(external_nodes) == 1
        ext_node = external_nodes[0]
        assert ext_node["mounted"] is True

    def test_file_uri_mounted_normalized_paths(self, project_root, tmp_path):
        """file:/// with backslashes in URI is handled correctly on Windows."""
        ext_dir, doc = self._make_ext_dir(tmp_path, with_links=False)
        doc_path_str = str(doc).replace("\\", "/")

        file_uri = f"file:///{doc_path_str}"
        (project_root / "linker.md").write_text(
            f"[Ext]({file_uri})", encoding="utf-8"
        )

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        eng.scan_all()

        ext_nodes_in_graph = [n for n, d in eng.graph.nodes(data=True)
                              if d.get("is_external")]
        assert len(ext_nodes_in_graph) == 1

    def test_file_uri_update_file_rebuilds_external(self, project_root, tmp_path):
        """update_file() also handles file:/// links for mounted targets."""
        ext_dir, doc = self._make_ext_dir(tmp_path, with_links=False)

        file_uri = f"file:///{str(doc).replace(chr(92), '/')}"
        linker = project_root / "linker.md"
        linker.write_text(f"[Ext]({file_uri})", encoding="utf-8")

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        eng.scan_all()

        # Modify linker.md
        linker.write_text(
            f"[Ext]({file_uri})\n\nAlso [Tools](TOOLS.md)", encoding="utf-8"
        )
        eng.update_file("linker.md", event="modified")

        graph_data = eng.get_graph_data()
        external_nodes = [n for n in graph_data["nodes"] if n.get("is_external")]
        assert len(external_nodes) == 1
        assert external_nodes[0]["mounted"] is True

    def test_engine_respects_external_paths_param(self, project_root):
        """GraphEngine.__init__ stores and normalizes external_paths."""
        eng = GraphEngine(project_root, external_paths=["C:/shared/docs"])
        assert len(eng.external_paths) == 1
        # resolve() may change case on Windows; check the path ends correctly
        assert eng.external_paths[0].replace("\\", "/").lower().endswith("shared/docs")

        # Empty by default
        eng2 = GraphEngine(project_root)
        assert eng2.external_paths == []

    def test_is_within_external_paths_helper(self, project_root, tmp_path):
        """_is_within_external_paths correctly checks containment."""
        ext_dir, doc = self._make_ext_dir(tmp_path)
        ext_dir_str = str(ext_dir).replace("\\", "/")
        doc_str = str(doc).replace("\\", "/")
        outside_str = str(tmp_path / "outside" / "file.md").replace("\\", "/")

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        assert eng._is_within_external_paths(doc_str) is True
        assert eng._is_within_external_paths(outside_str) is False
        assert eng._is_within_external_paths(ext_dir_str) is True

    def test_mounted_external_outgoing_relative_link_becomes_edge(
        self, project_root, tmp_path
    ):
        """Mounted external file's outgoing relative link → edge to sibling ext file."""
        ext_dir = tmp_path / "ext_lib"
        ext_dir.mkdir()
        target_file = ext_dir / "REQUIREMENTS.md"
        target_file.write_text("# Requirements", encoding="utf-8")
        source_file = ext_dir / "PROGRESS.md"
        source_file.write_text(
            "# Progress\n\nSee [Requirements](./REQUIREMENTS.md)",
            encoding="utf-8",
        )

        file_uri = f"file:///{str(source_file).replace(chr(92), '/')}"
        (project_root / "linker.md").write_text(
            f"[Progress]({file_uri})", encoding="utf-8"
        )

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        eng.scan_all()

        source_path = str(source_file).replace("\\", "/")
        target_path = str(target_file).replace("\\", "/")

        # Check both external nodes exist
        graph_data = eng.get_graph_data()
        external_nodes = [n for n in graph_data["nodes"] if n.get("is_external")]
        assert len(external_nodes) >= 2

        # Check edge: source → target
        edges = eng.graph.edges()
        edge_pairs = {(s, t) for s, t in edges}
        assert (source_path, target_path) in edge_pairs

    def test_mounted_external_outgoing_unmounted_becomes_leaf(
        self, project_root, tmp_path
    ):
        """Mounted external file links to a file:/// target outside external_paths → unmounted leaf."""
        ext_dir = tmp_path / "ext_lib"
        ext_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "other.md"
        outside_file.write_text("# Other", encoding="utf-8")

        source_file = ext_dir / "PROGRESS.md"
        outside_uri = f"file:///{str(outside_file).replace(chr(92), '/')}"
        source_file.write_text(
            f"# Progress\n\nSee [Other]({outside_uri})",
            encoding="utf-8",
        )

        file_uri = f"file:///{str(source_file).replace(chr(92), '/')}"
        (project_root / "linker.md").write_text(
            f"[Progress]({file_uri})", encoding="utf-8"
        )

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        eng.scan_all()

        graph_data = eng.get_graph_data()
        external_nodes = [n for n in graph_data["nodes"] if n.get("is_external")]
        assert len(external_nodes) >= 2

        source_path = str(source_file).replace("\\", "/")
        outside_path = str(outside_file).replace("\\", "/")

        # The outside file should be an unmounted external leaf
        outside_node = [n for n in external_nodes if n["id"] == outside_path]
        assert len(outside_node) == 1
        assert outside_node[0]["mounted"] is False

        # Edge: source → outside
        edges = eng.graph.edges()
        edge_pairs = {(s, t) for s, t in edges}
        assert (source_path, outside_path) in edge_pairs

    def test_poll_external_files_skips_unmounted_and_network_refs(self, project_root, tmp_path):
        """Polling must only stat mounted external files."""
        ext_dir, mounted_file = self._make_ext_dir(tmp_path, with_links=False)
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        outside_file = outside_dir / "other.md"
        outside_file.write_text("# Other", encoding="utf-8")

        eng = GraphEngine(project_root, external_paths=[str(ext_dir)])
        mounted_path = str(mounted_file).replace("\\", "/")
        outside_path = str(outside_file).replace("\\", "/")
        eng.graph.add_node(mounted_path, **{
            "type": "external", "is_external": True, "mounted": True,
            "exists": True, "abs_path": mounted_path, "last_modified": "old",
        })
        eng.graph.add_node(outside_path, **{
            "type": "external", "is_external": True, "mounted": False,
            "exists": True, "abs_path": outside_path, "last_modified": "old",
        })
        eng.graph.add_node("file:////server/share/doc.md", **{
            "type": "external", "is_external": True, "mounted": False,
            "exists": None, "abs_path": "file:////server/share/doc.md",
        })

        changed = eng.poll_external_files()

        changed_paths = {item["path"] for item in changed}
        assert mounted_path in changed_paths
        assert outside_path not in changed_paths
        assert "file:////server/share/doc.md" not in changed_paths
        assert eng.graph.nodes[outside_path]["last_modified"] == "old"
