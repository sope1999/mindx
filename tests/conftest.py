import pytest
from pathlib import Path


@pytest.fixture
def project_root():
    """Create a temp project tree with .md files for parser tests."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Create test .md files
        (root / "MEMORY.md").write_text("# Memory\n\nSee [TOOLS.md](TOOLS.md) for tools\n- [urls.md](urls.md)", encoding="utf-8")
        (root / "TOOLS.md").write_text("# Tools\n\n- [claude-code](memory/tools/claude-code.md)", encoding="utf-8")
        (root / "urls.md").write_text("## URLs\n\n[github](https://github.com)", encoding="utf-8")
        (root / "memory").mkdir(exist_ok=True)
        (root / "memory" / "tools").mkdir(parents=True, exist_ok=True)
        (root / "memory" / "tools" / "claude-code.md").write_text(
            "# Claude Code\n\nUses [TOOLS.md](../../TOOLS.md)", encoding="utf-8"
        )
        yield root
