"""Unit tests for mcp_server.py tool functions.

Tests all 13 tool functions directly (no MCP stdio protocol).
Mocks _http_get, _http_post for HTTP tools, and file I/O for content tools.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path so 'import mcp_server' works
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import mcp_server


# ── Fixture ──────────────────────────────────────────────────────

@pytest.fixture
def mock_mcp():
    """Set up mcp_server with mock config and reset CURRENT_PROJECT."""
    orig_config = mcp_server.CONFIG
    orig_project = mcp_server.CURRENT_PROJECT

    mcp_server.CONFIG = {
        "projects": [
            {"name": "test-project", "root": "/tmp/test"},
            {"name": "other", "root": "/tmp/other"},
        ]
    }
    mcp_server.CURRENT_PROJECT = None

    yield mcp_server

    mcp_server.CONFIG = orig_config
    mcp_server.CURRENT_PROJECT = orig_project


@pytest.fixture
def with_project(mock_mcp):
    """mock_mcp + switch to 'test-project' (bypassing HTTP call)."""
    mock_mcp.CURRENT_PROJECT = "test-project"
    yield mock_mcp


# ── Zero-level tools (no project needed) ─────────────────────────

class TestListProjects:
    def test_list_projects(self, mock_mcp):
        result = mcp_server.tool_list_projects()
        assert result == {"projects": ["test-project", "other"]}


class TestSwitchProject:
    def test_switch_project_valid(self, mock_mcp):
        with patch.object(mcp_server, "_http_post", return_value={"success": True}):
            result = mcp_server.tool_switch_project("test-project")
        assert "_error" not in result
        assert result["project"] == "test-project"
        assert result["root"] == "/tmp/test"
        assert mcp_server.CURRENT_PROJECT == "test-project"

    def test_switch_project_invalid(self, mock_mcp):
        result = mcp_server.tool_switch_project("nonexistent")
        assert "_error" in result
        assert "nonexistent" in result["_error"]
        assert "test-project" in result["_error"]
        assert mcp_server.CURRENT_PROJECT is None

    def test_switch_project_remote_fails(self, mock_mcp):
        with patch.object(mcp_server, "_http_post", return_value={"_error": "连接失败"}):
            result = mcp_server.tool_switch_project("test-project")
        assert "_error" in result
        assert mcp_server.CURRENT_PROJECT is None

    def test_switch_project_remote_success_false(self, mock_mcp):
        with patch.object(mcp_server, "_http_post", return_value={"success": False, "message": "bad"}):
            result = mcp_server.tool_switch_project("test-project")
        assert "_error" in result
        assert "bad" in result["_error"]
        assert mcp_server.CURRENT_PROJECT is None


class TestEnsureProject:
    def test_ensure_project_raises(self, mock_mcp):
        with pytest.raises(ValueError, match="没有选择项目"):
            mcp_server.tool_list_files()

    def test_ensure_project_succeeds(self, with_project):
        # After switch, a tool that requires project should not raise
        with patch.object(mcp_server, "_http_get", return_value={"files": []}):
            result = mcp_server.tool_list_files()
        assert "_error" not in result


# ── Query tools (mock _http_get) ─────────────────────────────────

class TestListFiles:
    def test_list_files(self, with_project):
        files = [{"path": "a.md"}, {"path": "b.md"}]
        with patch.object(mcp_server, "_http_get", return_value={"files": files}):
            result = mcp_server.tool_list_files()
        assert result["files"] == files
        assert result["count"] == 2

    def test_list_files_with_pattern(self, with_project):
        files = [{"path": "notes/a.md"}, {"path": "draft/b.md"}, {"path": "c.md"}]
        with patch.object(mcp_server, "_http_get", return_value={"files": files}):
            result = mcp_server.tool_list_files(name_pattern="notes")
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "notes/a.md"
        assert result["count"] == 1

    def test_list_files_api_returns_list(self, with_project):
        files = [{"path": "a.md"}, {"path": "b.md"}]
        with patch.object(mcp_server, "_http_get", return_value=files):
            result = mcp_server.tool_list_files()
        assert result["files"] == files
        assert result["count"] == 2

    def test_list_files_no_project(self, mock_mcp):
        with pytest.raises(ValueError):
            mcp_server.tool_list_files()

    def test_list_files_http_error(self, with_project):
        with patch.object(mcp_server, "_http_get", return_value={"_error": "连接失败"}):
            result = mcp_server.tool_list_files()
        assert "_error" in result


class TestSearchFiles:
    def test_search_files(self, with_project):
        files = [{"path": "notes/a.md"}, {"path": "ideas/b.md"}, {"path": "c.md"}]
        with patch.object(mcp_server, "_http_get", return_value={"files": files}):
            result = mcp_server.tool_search_files("md")
        assert result["count"] == 3

    def test_search_files_case_insensitive(self, with_project):
        files = [{"path": "Notes/A.md"}, {"path": "B.txt"}]
        with patch.object(mcp_server, "_http_get", return_value={"files": files}):
            result = mcp_server.tool_search_files("notes")
        assert result["count"] == 1
        assert result["results"][0]["path"] == "Notes/A.md"


class TestGetFileInfo:
    def test_get_file_info(self, with_project):
        api_data = {
            "path": "a.md",
            "type": "file",
            "exists": True,
            "size": 1024,
            "last_modified": "2025-01-01",
            "links": ["b.md", "c.md"],
            "dependencies": ["d.md"],
            "extra_field": "ignored",
        }
        with patch.object(mcp_server, "_http_get", return_value=api_data):
            result = mcp_server.tool_get_file_info("a.md")
        assert result["path"] == "a.md"
        assert result["type"] == "file"
        assert result["exists"] is True
        assert result["size"] == 1024
        assert result["last_modified"] == "2025-01-01"
        assert result["links_count"] == 2
        assert result["backlinks_count"] == 1
        assert "extra_field" not in result

    def test_get_file_info_http_error(self, with_project):
        with patch.object(mcp_server, "_http_get", return_value={"_error": "fail"}):
            result = mcp_server.tool_get_file_info("a.md")
        assert "_error" in result


class TestGetReferences:
    def test_get_references(self, with_project):
        api_data = {"path": "a.md", "links": ["b.md", "c.md"]}
        with patch.object(mcp_server, "_http_get", return_value=api_data):
            result = mcp_server.tool_get_references("a.md")
        assert result["path"] == "a.md"
        assert result["references"] == ["b.md", "c.md"]
        assert result["count"] == 2

    def test_get_references_empty(self, with_project):
        api_data = {"path": "a.md", "links": []}
        with patch.object(mcp_server, "_http_get", return_value=api_data):
            result = mcp_server.tool_get_references("a.md")
        assert result["references"] == []
        assert result["count"] == 0


class TestGetBacklinks:
    def test_get_backlinks(self, with_project):
        api_data = {"backlinks": [{"source": "b.md"}, {"source": "c.md"}]}
        with patch.object(mcp_server, "_http_get", return_value=api_data):
            result = mcp_server.tool_get_backlinks("a.md")
        assert result["path"] == "a.md"
        assert result["backlinks"] == [{"source": "b.md"}, {"source": "c.md"}]
        assert result["count"] == 2


class TestGetDependencyGraph:
    def test_get_dependency_graph(self, with_project):
        api_data = {
            "nodes": [{"id": 1}, {"id": 2}],
            "edges": [{"from": 1, "to": 2}],
        }
        with patch.object(mcp_server, "_http_get", return_value=api_data):
            result = mcp_server.tool_get_dependency_graph()
        assert result["node_count"] == 2
        assert result["edge_count"] == 1
        assert result["nodes"] == [{"id": 1}, {"id": 2}]
        assert result["edges"] == [{"from": 1, "to": 2}]


class TestGetBrokenLinks:
    def test_get_broken_links(self, with_project):
        api_data = {"broken": [{"path": "a.md", "target": "missing.md"}]}
        with patch.object(mcp_server, "_http_get", return_value=api_data):
            result = mcp_server.tool_get_broken_links()
        # tool_get_broken_links passes through the response directly
        assert result == api_data


class TestGetSyncSuggestions:
    def test_get_sync_suggestions(self, with_project):
        suggestions = [
            {"changed_file": "a.md", "target": "b.md"},
            {"changed_file": "c.md", "target": "d.md"},
        ]
        with patch.object(mcp_server, "_http_get", return_value={"suggestions": suggestions}):
            result = mcp_server.tool_get_sync_suggestions()
        assert result["suggestions"] == suggestions
        assert result["count"] == 2

    def test_get_sync_suggestions_with_path_filter(self, with_project):
        suggestions = [
            {"changed_file": "a.md", "target": "b.md"},
            {"changed_file": "c.md", "target": "a.md"},
        ]
        with patch.object(mcp_server, "_http_get", return_value={"suggestions": suggestions}):
            result = mcp_server.tool_get_sync_suggestions(path="a.md")
        # filters where changed_file == path OR target == path
        assert result["count"] == 2
        assert len(result["suggestions"]) == 2

    def test_get_sync_suggestions_api_returns_list(self, with_project):
        suggestions = [{"changed_file": "a.md", "target": "b.md"}]
        with patch.object(mcp_server, "_http_get", return_value=suggestions):
            result = mcp_server.tool_get_sync_suggestions()
        assert result["suggestions"] == suggestions
        assert result["count"] == 1


class TestGetChangeLog:
    def test_get_change_log(self, with_project):
        changes = [{"path": "a.md", "action": "modified"}]
        with patch.object(mcp_server, "_http_get", return_value={"changes": changes}):
            result = mcp_server.tool_get_change_log()
        assert result["changes"] == changes
        assert result["count"] == 1

    def test_get_change_log_with_limit(self, with_project):
        changes = [{"path": "a.md", "action": "modified"}]
        with patch.object(mcp_server, "_http_get", return_value={"changes": changes}) as mock_get:
            result = mcp_server.tool_get_change_log(limit=10)
        # Verify limit param was passed to _http_get
        mock_get.assert_called_once_with("/api/changes", {"limit": 10})

    def test_get_change_log_api_returns_list(self, with_project):
        changes = [{"path": "a.md", "action": "modified"}]
        with patch.object(mcp_server, "_http_get", return_value=changes):
            result = mcp_server.tool_get_change_log()
        assert result["changes"] == changes
        assert result["count"] == 1


# ── File I/O tools (mock file read) ──────────────────────────────

class TestGetFileContent:
    def test_get_file_content_success(self, with_project):
        fake_file = MagicMock()
        fake_file.resolve.return_value = fake_file
        fake_file.relative_to.return_value = Path("test/a.md")  # under root
        fake_file.exists.return_value = True
        fake_file.is_file.return_value = True
        fake_file.stat.return_value = MagicMock(st_size=100)
        fake_file.read_text.return_value = "hello world"

        with patch.object(mcp_server, "_get_project_root", return_value=Path("/tmp/test")), \
             patch.object(mcp_server.Path, "__truediv__", return_value=fake_file), \
             patch.object(Path, "resolve", return_value=fake_file):
            # The tool resolves: root / path .resolve()
            # We need to mock the Path operations more carefully
            root = Path("/tmp/test")
            target = root / "a.md"
            # Actually let's mock it at a higher level
            pass

        # Use a simpler approach: mock _get_project_root and patch Path operations
        root = Path("/tmp/test")
        # Create a temp file for real file I/O test
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            real_root = Path(td)
            real_file = real_root / "a.md"
            real_file.write_text("hello world", encoding="utf-8")

            # Patch _get_project_root to return our temp dir
            with patch.object(mcp_server, "_get_project_root", return_value=real_root):
                result = mcp_server.tool_get_file_content("a.md")
            assert result["path"] == "a.md"
            assert result["content"] == "hello world"
            assert "_error" not in result

    def test_get_file_content_not_found(self, with_project):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            with patch.object(mcp_server, "_get_project_root", return_value=Path(td)):
                result = mcp_server.tool_get_file_content("nonexistent.md")
            assert "_error" in result
            assert "不存在" in result["_error"]

    def test_get_file_content_path_traversal(self, with_project):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            real_root = Path(td)
            # Create a file outside the root
            outside_dir = Path(tempfile.mkdtemp())
            outside_file = outside_dir / "secret.md"
            outside_file.write_text("secret", encoding="utf-8")

            with patch.object(mcp_server, "_get_project_root", return_value=real_root):
                # Try accessing ../../<outside_dir>/secret.md
                traversal_path = "../" * 10 + "secret.md"
                result = mcp_server.tool_get_file_content(traversal_path)
            assert "_error" in result
            assert "超出项目范围" in result["_error"]

            # Clean up
            outside_file.unlink()
            outside_dir.rmdir()

    def test_get_file_content_large_file(self, with_project):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            real_root = Path(td)
            big_file = real_root / "big.md"
            big_file.write_text("x" * 100, encoding="utf-8")

            # Mock stat to return > 10MB
            with patch.object(mcp_server, "_get_project_root", return_value=real_root), \
                 patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value = MagicMock(st_size=11 * 1024 * 1024)
                result = mcp_server.tool_get_file_content("big.md")
            assert "_error" in result
            assert "too large" in result["_error"].lower()


# ── Write tools (mock _http_post) ────────────────────────────────

class TestRenameFile:
    def test_rename_file_success(self, with_project):
        preview = {"success": True, "new_path": "new_name.md", "affected_count": 3}
        execute = {
            "success": True,
            "old_path": "old.md",
            "new_path": "new_name.md",
            "updated_files": ["b.md", "c.md"],
        }
        with patch.object(mcp_server, "_http_post") as mock_post:
            mock_post.side_effect = [preview, execute]
            result = mcp_server.tool_rename_file("old.md", "new_name.md")
        assert result["success"] is True
        assert result["old_path"] == "old.md"
        assert result["new_path"] == "new_name.md"
        assert result["updated_files"] == ["b.md", "c.md"]
        assert result["affected_count"] == 3
        # Verify two POST calls
        assert mock_post.call_count == 2

    def test_rename_file_preview_fails(self, with_project):
        with patch.object(mcp_server, "_http_post", return_value={"_error": "预览失败"}):
            result = mcp_server.tool_rename_file("old.md", "new.md")
        assert "_error" in result
        assert "预览失败" in result["_error"]

    def test_rename_file_preview_not_success(self, with_project):
        preview = {"success": False, "error": "cannot rename"}
        with patch.object(mcp_server, "_http_post", return_value=preview):
            result = mcp_server.tool_rename_file("old.md", "new.md")
        assert "_error" in result
        assert "cannot rename" in result["_error"]

    def test_rename_file_execute_fails(self, with_project):
        preview = {"success": True, "new_path": "new.md", "affected_count": 1}
        execute = {"_error": "执行失败"}
        with patch.object(mcp_server, "_http_post") as mock_post:
            mock_post.side_effect = [preview, execute]
            result = mcp_server.tool_rename_file("old.md", "new.md")
        assert "_error" in result
        assert "执行失败" in result["_error"]

    def test_rename_file_no_project(self, mock_mcp):
        with pytest.raises(ValueError):
            mcp_server.tool_rename_file("old.md", "new.md")


# ── Error handling (mock _http_get/_http_post) ────────────────────

class TestHttpErrors:
    def test_http_get_connection_error(self, with_project):
        with patch.object(mcp_server, "_http_get", return_value={"_error": "无法连接 mindx 服务"}):
            result = mcp_server.tool_get_broken_links()
        assert "_error" in result
        assert "无法连接" in result["_error"]

    def test_http_get_timeout(self, with_project):
        with patch.object(mcp_server, "_http_get", return_value={"_error": "请求失败: ReadTimeout"}):
            result = mcp_server.tool_get_file_info("a.md")
        assert "_error" in result
        assert "请求失败" in result["_error"]