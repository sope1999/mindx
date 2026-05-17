"""File system watcher: monitors a project directory for changes."""

import time
from pathlib import Path
from typing import Callable, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from config import IGNORE_PATTERNS


class MindxEventHandler(FileSystemEventHandler):
    """Handles file system events and dispatches to callback."""

    def __init__(self, project_root: Path, on_change: Callable, ignore_patterns: list):
        super().__init__()
        self.project_root = project_root
        self.on_change = on_change
        self.ignore_patterns = ignore_patterns
        self._debounce: dict = {}  # path -> last event time

    def _should_ignore(self, path: str) -> bool:
        """Check if path matches any ignore pattern."""
        try:
            rel = str(Path(path).relative_to(self.project_root)).replace("\\", "/")
        except ValueError:
            return False
        for pattern in self.ignore_patterns:
            if pattern.endswith("/*"):
                if rel.startswith(pattern[:-2]):
                    return True
            elif pattern.endswith("*"):
                if rel.endswith(pattern[1:]):
                    return True
            elif pattern.startswith("*."):
                if rel.endswith(pattern[1:]):
                    return True
            elif rel.startswith(pattern):
                return True
        return False

    def _should_track(self, abs_path: str) -> bool:
        """Only track .md files and directory structure."""
        path = Path(abs_path)
        # Track .md files and directories
        if path.is_dir():
            return True
        return path.suffix == ".md"

    def _debounce_check(self, path: str) -> bool:
        """Prevent duplicate events within 500ms."""
        now = time.time()
        last = self._debounce.get(path, 0)
        if now - last < 0.5:
            return True  # skip
        self._debounce[path] = now
        return False

    def _rel(self, abs_path: str) -> str:
        """Convert absolute path to relative from project_root."""
        try:
            return str(Path(abs_path).relative_to(self.project_root)).replace("\\", "/")
        except ValueError:
            return abs_path

    def on_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        if not self._should_track(event.src_path):
            return
        if self._debounce_check(event.src_path):
            return
        self.on_change(self._rel(event.src_path), "modified")

    def on_created(self, event: FileSystemEvent):
        if self._should_ignore(event.src_path):
            return
        if not self._should_track(event.src_path):
            return
        if self._debounce_check(event.src_path):
            return
        self.on_change(self._rel(event.src_path), "created")

    def on_deleted(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self._should_ignore(event.src_path):
            return
        if not self._should_track(event.src_path):
            return
        if self._debounce_check(event.src_path):
            return
        self.on_change(self._rel(event.src_path), "deleted")


class FileWatcher:
    """Wraps watchdog Observer for mindx."""

    def __init__(self, project_root: Path, on_change: Callable):
        self.project_root = Path(project_root).resolve()
        self.on_change = on_change
        self.observer: Observer = None
        self._running = False
        self._ignore_patterns = list(IGNORE_PATTERNS)
        self._setup_observer()

    def _setup_observer(self):
        """Create and schedule a new observer with handler."""
        if self.observer is not None:
            try:
                self.observer.stop()
                self.observer.join(timeout=2)
            except Exception:
                pass
        self.observer = Observer()
        handler = MindxEventHandler(
            project_root=self.project_root,
            on_change=self._handle_change,
            ignore_patterns=self._ignore_patterns,
        )
        self.observer.schedule(handler, str(self.project_root), recursive=True)

    def _handle_change(self, rel_path: str, event: str):
        """Forward change event to the main callback."""
        self.on_change(rel_path, event)

    def start(self):
        """Start watching."""
        if not self._running:
            self.observer.start()
            self._running = True

    def stop(self):
        """Stop watching."""
        if self._running:
            self.observer.stop()
            self.observer.join(timeout=5)
            self._running = False

    def restart(self, new_root: Path, new_on_change: Callable):
        """Stop old watcher, reconfigure for new project root, start again."""
        was_running = self._running
        self.stop()
        self.project_root = Path(new_root).resolve()
        self.on_change = new_on_change
        self._setup_observer()
        if was_running:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._running
