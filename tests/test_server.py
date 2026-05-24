"""Integration tests for server.py API routes using Flask test client and pytest."""

import pytest
import tempfile
import yaml
from pathlib import Path
from graph_engine import GraphEngine


@pytest.fixture
def app():
    """Create Flask test client with temp project and config."""
    from server import app as flask_app
    import server

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Create test .md files
        (root / "MEMORY.md").write_text("# Memory\n[TOOLS.md](TOOLS.md)")
        (root / "TOOLS.md").write_text("# Tools")
        (root / "sub").mkdir(exist_ok=True)
        (root / "sub" / "child.md").write_text("# Child\nBack to [MEMORY.md](../MEMORY.md)")

        # Create temp config.yaml
        config_path = Path(d) / "config.yaml"
        config = {
            "version": "1.0.0",
            "port": 5020,
            "projects": [{"name": "test", "root": str(root)}],
        }
        config_path.write_text(yaml.dump(config), encoding="utf-8")

        # Monkey-patch config path
        server._config = config
        server.active_project = None
        server.engines.clear()
        server.watchers.clear()

        flask_app.config["TESTING"] = True
        with flask_app.test_client() as client:
            yield client

        # Stop watchers so temp dir can be cleaned up on Windows
        for w in server.watchers.values():
            w.stop()
        server.watchers.clear()
        server.engines.clear()
        server.active_project = None


def _select_project(client):
    """Helper: activate the 'test' project via the select endpoint."""
    return client.post("/api/projects/select", json={"name": "test"})


# ── Project management ────────────────────────────────────────


class TestProjectManagement:
    def test_list_projects(self, app):
        resp = app.get("/api/projects")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        names = [p["name"] for p in data]
        assert "test" in names

    def test_select_project(self, app):
        resp = _select_project(app)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["file_count"] > 0

    def test_select_nonexistent_project(self, app):
        resp = app.post("/api/projects/select", json={"name": "no_such_project"})
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["success"] is False
        assert "not found" in data["error"].lower() or "Project not found" in data["error"]


# ── File listing ──────────────────────────────────────────────


class TestFileListing:
    def test_files_after_select(self, app):
        _select_project(app)
        resp = app.get("/api/files")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0
        paths = [f["path"] for f in data]
        assert "MEMORY.md" in paths

    def test_files_no_project(self, app):
        resp = app.get("/api/files")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []


# ── File detail ───────────────────────────────────────────────


class TestFileDetail:
    def test_file_detail(self, app):
        _select_project(app)
        resp = app.get("/api/file/MEMORY.md")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["path"] == "MEMORY.md"
        # Should have links (outgoing to TOOLS.md)
        assert "links" in data
        link_targets = [l["target"] for l in data["links"]]
        assert "TOOLS.md" in link_targets

    def test_file_detail_not_found(self, app):
        _select_project(app)
        resp = app.get("/api/file/NOPE.md")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["path"] == "NOPE.md"
        # get_dependencies returns dict with references/referenced_by lists
        assert data["dependencies"]["references"] == []
        assert data["dependencies"]["referenced_by"] == []


# ── Graph ─────────────────────────────────────────────────────


class TestGraph:
    def test_graph_has_nodes(self, app):
        _select_project(app)
        resp = app.get("/api/graph")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "nodes" in data
        assert len(data["nodes"]) > 0
        node_ids = [n["id"] for n in data["nodes"]]
        assert "MEMORY.md" in node_ids

    def test_graph_has_edges(self, app):
        _select_project(app)
        resp = app.get("/api/graph")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "edges" in data
        # vis.js format uses "from"/"to" keys
        edge_pairs = [(e["from"], e["to"]) for e in data["edges"]]
        assert ("MEMORY.md", "TOOLS.md") in edge_pairs


# ── Scan ──────────────────────────────────────────────────────


class TestScan:
    def test_scan_returns_stats(self, app):
        _select_project(app)
        resp = app.get("/api/scan")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_files"] > 0


# ── Backlinks (bug fix verification) ──────────────────────────


class TestBacklinks:
    def test_backlinks(self, app):
        _select_project(app)
        # sub/child.md links to MEMORY.md via ../MEMORY.md
        # So MEMORY.md should have sub/child.md as a backlink source
        resp = app.get("/api/file/MEMORY.md/backlinks")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "backlinks" in data
        sources = [b["from"] for b in data["backlinks"]]
        assert "sub/child.md" in sources


# ── Broken links ──────────────────────────────────────────────


class TestBrokenLinks:
    def test_broken_links(self, app):
        _select_project(app)
        resp = app.get("/api/broken-links")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "broken_links" in data
        assert "count" in data
        # Test data has all valid links, so count may be 0
        assert isinstance(data["count"], int)

    def test_external_broken_links_are_reported(self, app):
        import server

        _select_project(app)
        engine = server.engines[server.active_project]
        project_root = engine.project_root
        (project_root / "BROKEN_EXTERNAL.md").write_text(
            "[Missing](file:///C:/definitely/missing/mindx-file.md)", encoding="utf-8"
        )
        engine.scan_all()

        resp = app.get("/api/broken-links")
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(bl.get("is_external") for bl in data["broken_links"])

    def test_broken_links_deduped_by_file_and_target(self, app):
        """Duplicate broken links from same file to same target are deduplicated."""
        import server

        _select_project(app)
        engine = server.engines[server.active_project]
        project_root = engine.project_root
        # Write a file with two links to the same missing target (e.g. with anchor and title)
        (project_root / "DUP_BROKEN.md").write_text(
            "[A](missing.md#anchor) [B](missing.md \"title\")", encoding="utf-8"
        )
        engine.scan_all()

        resp = app.get("/api/broken-links")
        assert resp.status_code == 200
        data = resp.get_json()
        dup_broken = [bl for bl in data["broken_links"] if bl["file"] == "DUP_BROKEN.md"]
        targets = [bl["target"] for bl in dup_broken]
        assert targets.count("missing.md") == 1, f"Expected dedup, got targets: {targets}"

    def test_file_detail_issues_deduped_by_target(self, app):
        """Duplicate broken link issues in file detail are deduplicated by target."""
        import server

        _select_project(app)
        engine = server.engines[server.active_project]
        project_root = engine.project_root
        (project_root / "DUP_ISSUES.md").write_text(
            "[A](gone.md#s1) [B](gone.md#s2)", encoding="utf-8"
        )
        engine.scan_all()

        resp = app.get("/api/file/DUP_ISSUES.md")
        assert resp.status_code == 200
        data = resp.get_json()
        broken_targets = [i["target"] for i in data.get("issues", []) if i["type"] == "broken_link"]
        assert broken_targets.count("gone.md") == 1, f"Expected dedup in issues, got: {broken_targets}"

    def test_file_detail_falls_back_to_external_graph_node(self, app):
        import server

        _select_project(app)
        engine: GraphEngine = server.engines[server.active_project]
        external_path = "C:/shared/unmounted.md"
        engine.graph.add_node(external_path, **{
            "type": "external",
            "exists": True,
            "label": "unmounted.md",
            "is_external": True,
            "mounted": False,
            "external_status": "unmounted",
            "target_exists": True,
            "broken": False,
            "abs_path": external_path,
        })

        resp = app.get("/api/file/" + external_path)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_external"] is True
        assert data["external_status"] == "unmounted"


# ── Changes ───────────────────────────────────────────────────


class TestChanges:
    def test_changes(self, app):
        _select_project(app)
        resp = app.get("/api/changes")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


# ── History ───────────────────────────────────────────────────


class TestHistory:
    def test_history(self, app):
        _select_project(app)
        resp = app.get("/api/history")
        assert resp.status_code == 200
        data = resp.get_json()
        # history may be empty dict or contain entries
        assert isinstance(data, dict)


# ── Settings ──────────────────────────────────────────────────


class TestSettings:
    def test_settings(self, app):
        _select_project(app)
        resp = app.get("/api/settings/load")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        # Default keys expected
        assert "file_classes" in data
        assert "excluded_dirs" in data
        assert "display_mode" in data
