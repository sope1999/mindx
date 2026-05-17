"""Dependency graph engine: builds and queries the file relationship graph."""

from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import networkx as nx

from config import SYNC_RULES, IGNORE_PATTERNS
from parser import FileInfo, Link, parse_file


@dataclass
class SyncSuggestion:
    """A suggestion for what needs to be synced after a file change."""
    changed_file: str
    event: str            # "modified", "created", "deleted"
    target: str           # file that needs updating
    reason: str
    action: str           # "index_update", "l3_to_l2_sync", "self_document", etc.
    severity: str         # "critical", "warning", "info"


@dataclass
class ChangeEvent:
    """A recorded file system change."""
    timestamp: datetime
    file: str
    event: str            # "modified", "created", "deleted"
    suggestions: List[SyncSuggestion] = field(default_factory=list)


class GraphEngine:
    """Manages the dependency graph and sync rule matching."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.graph = nx.DiGraph()
        self.files: Dict[str, FileInfo] = {}
        self.change_log: List[ChangeEvent] = []
        self._max_changes = 200

    def scan_all(self):
        """Full scan: parse every .md file under project_root recursively."""
        self.graph.clear()
        self.files.clear()

        # Collect all .md files recursively, skipping ignored paths
        md_files: List[Path] = []
        if self.project_root.exists():
            for md_file in self.project_root.rglob("*.md"):
                rel = str(md_file.relative_to(self.project_root)).replace("\\", "/")
                if self._should_ignore(rel):
                    continue
                md_files.append(md_file)

        # Parse every file
        for abs_path in md_files:
            rel = str(abs_path.relative_to(self.project_root)).replace("\\", "/")
            if rel in self.files:
                continue
            info = parse_file(abs_path, self.project_root)
            self.files[info.path] = info
            self.graph.add_node(info.path, **{
                "type": info.file_type,
                "exists": info.exists,
                "label": Path(info.path).name,
            })

        # Build edges from extracted links
        self._build_edges()

    def _should_ignore(self, rel_path: str) -> bool:
        """Check if a relative path matches any IGNORE_PATTERNS."""
        for pattern in IGNORE_PATTERNS:
            if pattern.endswith("/*"):
                if rel_path.startswith(pattern[:-2]):
                    return True
            elif pattern.endswith("*"):
                if rel_path.endswith(pattern[1:]):
                    return True
            elif pattern.startswith("*."):
                if rel_path.endswith(pattern[1:]):
                    return True
            elif rel_path.startswith(pattern):
                return True
        return False

    def _build_edges(self):
        """Add directed edges for all parsed links."""
        new_files: Dict[str, FileInfo] = {}  # collect new files to avoid dict-size-change during iteration

        for file_info in list(self.files.values()):
            for link in file_info.links:
                target = link.target
                if target in self.graph:
                    self.graph.add_edge(file_info.path, target,
                                        link_type=link.link_type,
                                        context=link.context[:100])
                elif (self.project_root / target).exists():
                    # Target exists but wasn't scanned — defer addition
                    if target not in self.files and target not in new_files:
                        abs_path = self.project_root / target
                        t_info = parse_file(abs_path, self.project_root)
                        new_files[t_info.path] = t_info
                    self.graph.add_edge(file_info.path, target,
                                        link_type=link.link_type,
                                        context=link.context[:100])
                elif link.is_external:
                    # External target — try to stat it for light tracking
                    ext_abs = Path(link.target)
                    ext_exists = ext_abs.exists() and ext_abs.is_file()
                    ext_size = 0
                    ext_mtime = None
                    if ext_exists:
                        try:
                            st = ext_abs.stat()
                            ext_size = st.st_size
                            ext_mtime = datetime.fromtimestamp(st.st_mtime)
                        except OSError:
                            ext_exists = False
                    if target not in self.graph and target not in new_files:
                        self.graph.add_node(target, **{
                            "type": "external",
                            "exists": ext_exists,
                            "label": Path(target).name,
                            "is_external": True,
                            "abs_path": str(ext_abs),
                            "size": ext_size,
                            "last_modified": ext_mtime.isoformat() if ext_mtime else None,
                        })
                    self.graph.add_edge(file_info.path, target,
                                        link_type=link.link_type,
                                        context=link.context[:100])

        # Add deferred files
        for path, info in new_files.items():
            self.files[path] = info
            if path not in self.graph:
                self.graph.add_node(path)

    def update_file(self, rel_path: str, event: str = "modified"):
        """Handle a file change event. Returns sync suggestions."""
        abs_path = self.project_root / rel_path

        if not abs_path.exists() and event == "modified":
            event = "deleted"

        # Collect files that reference this one (before removing from graph)
        broken_refs = []  # (referencing_file, link_target) for broken link detection
        if event == "deleted" and rel_path in self.graph:
            broken_refs = [
                (src, rel_path)
                for src, _ in self.graph.in_edges(rel_path)
                if src in self.files
            ]

        # Re-parse the file
        info = parse_file(abs_path, self.project_root)
        old_info = self.files.get(rel_path)

        if event == "deleted":
            if rel_path in self.files:
                del self.files[rel_path]
            if rel_path in self.graph:
                self.graph.remove_node(rel_path)
        else:
            self.files[rel_path] = info
            # Remove old outgoing edges before rebuilding
            if rel_path in self.graph:
                self.graph.remove_edges_from(list(self.graph.out_edges(rel_path)))
            else:
                self.graph.add_node(rel_path, **{
                    "type": info.file_type,
                    "exists": info.exists,
                    "label": Path(info.path).name,
                })
            nx.set_node_attributes(self.graph, {rel_path: {
                "type": info.file_type,
                "exists": info.exists,
            }})

            # Rebuild edges for this file
            for link in info.links:
                target = link.target
                # Ensure target node exists
                if target not in self.graph and (self.project_root / target).exists():
                    t_info = parse_file(self.project_root / target, self.project_root)
                    self.files[t_info.path] = t_info
                    self.graph.add_node(t_info.path, **{
                        "type": t_info.file_type, "exists": t_info.exists,
                        "label": Path(t_info.path).name,
                    })
                if target in self.graph:
                    self.graph.add_edge(rel_path, target,
                                        link_type=link.link_type,
                                        context=link.context[:100])

        # Generate sync suggestions
        suggestions = self._generate_suggestions(rel_path, event, broken_refs)

        # Record change
        self.change_log.append(ChangeEvent(
            timestamp=datetime.now(),
            file=rel_path,
            event=event,
            suggestions=suggestions,
        ))
        if len(self.change_log) > self._max_changes:
            self.change_log = self.change_log[-self._max_changes:]

        return suggestions

    def _generate_suggestions(self, changed_file: str, event: str,
                              broken_refs: list = None) -> List[SyncSuggestion]:
        """Generate sync suggestions based on rules and graph relationships."""
        suggestions = []

        # 1. Check explicit sync rules
        for rule in SYNC_RULES:
            if self._rule_matches(rule, changed_file, event):
                target = rule.get("target")
                if target:
                    suggestions.append(SyncSuggestion(
                        changed_file=changed_file,
                        event=event,
                        target=target,
                        reason=rule["reason"],
                        action=rule["action"],
                        severity="warning",
                    ))
                elif rule["action"] == "self_document":
                    suggestions.append(SyncSuggestion(
                        changed_file=changed_file,
                        event=event,
                        target=changed_file,
                        reason=rule["reason"],
                        action="self_document",
                        severity="info",
                    ))

        # 2. Find all files referencing the changed file (via graph backlinks)
        if event in ("modified", "deleted"):
            referencing = []
            if changed_file in self.graph:
                referencing = [src for src, _ in self.graph.in_edges(changed_file) if src in self.files]
            for src in referencing:
                severity = "warning" if event == "deleted" else "info"
                reason = (
                    f"链接目标已被删除: {changed_file}" if event == "deleted"
                    else f"引用的文件已变更 — 摘要可能需要更新"
                )
                suggestions.append(SyncSuggestion(
                    changed_file=changed_file,
                    event=event,
                    target=src,
                    reason=reason,
                    action="index_update",
                    severity=severity,
                ))

        # 3. Handle broken links from deletion (files that linked TO the deleted file)
        if event == "deleted" and broken_refs:
            for src, _ in broken_refs:
                suggestions.append(SyncSuggestion(
                    changed_file=changed_file,
                    event=event,
                    target=src,
                    reason=f"此文件引用了已删除的 {changed_file} — 链接已断开",
                    action="broken_link_fix",
                    severity="critical",
                ))

        # 4. If file is created/deleted, find the nearest parent _index.md or root .md
        if event in ("created", "deleted"):
            parent = self._find_parent_index(changed_file)
            if parent:
                suggestions.append(SyncSuggestion(
                    changed_file=changed_file,
                    event=event,
                    target=parent,
                    reason=f"新文件{'创建' if event == 'created' else '删除'} — 索引需要更新",
                    action="index_update",
                    severity="critical",
                ))

        # Deduplicate
        seen = set()
        unique = []
        for s in suggestions:
            key = (s.target, s.action)
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique

    def _rule_matches(self, rule: dict, file_path: str, event: str) -> bool:
        """Check if a sync rule matches the change event."""
        if rule["trigger"] != f"file_{event}":
            return False
        pattern = rule["pattern"]
        # Simple glob matching
        if pattern.endswith("/"):
            return file_path.startswith(pattern)
        elif pattern.endswith("/*/"):
            return file_path.startswith(pattern[:-3]) and "/" in file_path[len(pattern) - 3:]
        elif pattern.endswith("/*.md"):
            prefix = pattern[:-5]
            return file_path.startswith(prefix) and file_path.endswith(".md")
        else:
            return file_path == pattern

    def _find_parent_index(self, file_path: str) -> Optional[str]:
        """Find the nearest parent _index.md for a given file path.

        Walks up the directory tree looking for _index.md files.
        """
        parts = Path(file_path).parts
        # Walk up from deepest directory
        for i in range(len(parts) - 1, 0, -1):
            candidate = "/".join(parts[:i]) + "/_index.md"
            if candidate in self.files or (self.project_root / candidate).exists():
                return candidate
        # Also check MEMORY.md at root
        if "MEMORY.md" in self.files or (self.project_root / "MEMORY.md").exists():
            return "MEMORY.md"
        return None

    def get_dependencies(self, file_path: str) -> dict:
        """Get all dependencies for a file."""
        references = []  # files THIS file points to
        referenced_by = []  # files that point TO this file

        if file_path in self.graph:
            for _, target, data in self.graph.out_edges(file_path, data=True):
                references.append({
                    "path": target,
                    "type": self.graph.nodes[target].get("type", "unknown"),
                    "link_type": data.get("link_type", "unknown"),
                })
            for source, _, data in self.graph.in_edges(file_path, data=True):
                referenced_by.append({
                    "path": source,
                    "type": self.graph.nodes[source].get("type", "unknown"),
                    "link_type": data.get("link_type", "unknown"),
                })

        return {
            "path": file_path,
            "references": references,
            "referenced_by": referenced_by,
        }

    def get_graph_data(self) -> dict:
        """Get graph data formatted for vis.js visualization."""
        nodes = []
        edges = []
        node_ids = set()

        for node in self.graph.nodes:
            node_ids.add(node)
            ndata = self.graph.nodes[node]
            nodes.append({
                "id": node,
                "label": Path(node).name,
                "group": ndata.get("type", "unknown"),
                "title": f"{node}\n类型: {ndata.get('type', '?')}",
                "is_external": ndata.get("is_external", False),
                "mounted": ndata.get("mounted", False),
            })

        for source, target, data in self.graph.edges(data=True):
            tgt_node = self.graph.nodes.get(target, {})
            edges.append({
                "from": source,
                "to": target,
                "label": data.get("link_type", ""),
                "title": data.get("context", ""),
                "is_external": tgt_node.get("is_external", False),
            })

        # Include files that exist but have no edges as isolated nodes
        for file_path, info in self.files.items():
            if file_path not in node_ids:
                node_ids.add(file_path)
                nodes.append({
                    "id": file_path,
                    "label": Path(file_path).name,
                    "group": info.file_type,
                    "title": f"{file_path}\n类型: {info.file_type}",
                    "is_external": False,
                    "mounted": False,
                })

        return {"nodes": nodes, "edges": edges}

    def get_stats(self) -> dict:
        """Get summary statistics."""
        types = {}
        for info in self.files.values():
            t = info.file_type
            types[t] = types.get(t, 0) + 1

        return {
            "total_files": len(self.files),
            "total_edges": self.graph.number_of_edges(),
            "total_nodes_graph": self.graph.number_of_nodes(),
            "file_types": types,
            "recent_changes": len(self.change_log),
        }

    def poll_external_files(self) -> List[dict]:
        """Light-tracking: re-stat all external nodes, return list of changed ones.

        Returns list of {path, prev_exists, now_exists, prev_mtime, now_mtime}.
        """
        changed = []
        for node_id, ndata in self.graph.nodes(data=True):
            if not ndata.get("is_external"):
                continue
            abs_path_str = ndata.get("abs_path", node_id)
            abs_path = Path(abs_path_str)
            prev_exists = ndata.get("exists", False)
            prev_mtime = ndata.get("last_modified")

            now_exists = abs_path.exists() and abs_path.is_file()
            now_mtime = None
            now_size = 0
            if now_exists:
                try:
                    st = abs_path.stat()
                    now_mtime = datetime.fromtimestamp(st.st_mtime).isoformat()
                    now_size = st.st_size
                except OSError:
                    now_exists = False

            if prev_exists != now_exists or prev_mtime != now_mtime:
                nx.set_node_attributes(self.graph, {node_id: {
                    "exists": now_exists,
                    "last_modified": now_mtime,
                    "size": now_size,
                }})
                changed.append({
                    "path": node_id,
                    "label": Path(node_id).name,
                    "prev_exists": prev_exists,
                    "now_exists": now_exists,
                    "prev_mtime": prev_mtime,
                    "now_mtime": now_mtime,
                })
        return changed
