# mindx v4.3 — AI-Readable Project Manual

> This document is the single source of truth for AI agents working on mindx.
> Last verified against source: 2026-05-18.

---

## 1. Project Overview

**mindx** is a local-first memory-index dashboard that scans a folder of Markdown files, builds a directed dependency graph from their `[text](path)` links, and visualises the result in a browser with real-time file-change detection.

**Tech stack:**

| Layer       | Technology                                                   |
|-------------|--------------------------------------------------------------|
| Backend     | Python 3 — Flask + Flask-SocketIO + watchdog + NetworkX      |
| Frontend    | Vanilla HTML + CSS + JS — vis.js for graph rendering          |
| Config      | YAML (`config.yaml`)                                         |
| Runtime     | `python server.py` → `http://127.0.0.1:5020`                |

**Architecture pipeline:**

```
server.py  ──orchestrates──►  graph_engine  ──scans──►  parser  ──extracts──►  Link objects
    │                           │
    ├──watcher────monitors──►   │
    │                           └──_build_edges()──►  nx.DiGraph
    │                                                   │
    └──SocketIO────pushes────►  /api/graph  ──────────►  frontend S.graphData
                                                      └──► vis.js Networks
```

**Config structure** (`config.yaml`):

```yaml
version: "1.0.0"
port: 5020
projects:
  - name: my-project
    root: "C:/path/to/project"
    external_paths: [...]
    positions: {reftree_positions: {...}, dirtree_positions: {...}, dep_positions: {...}}
    file_classes: {...}
    excluded_dirs: [...]
    display_mode: full | ref
    ref_roots: [...]
    active_root: MEMORY.md
```

---

## 2. File Map

| File | ~Lines | Purpose | Key Items |
|------|--------|---------|-----------|
| `server.py` | 730 | Flask routes, SocketIO events, multi-project management, external polling, startup | `active_project`, `engines{}`, `watchers{}`, `init_engine()`, `_load_externals()`, `_poll_external_files()`, all `/api/*` routes, `run_server()` |
| `graph_engine.py` | 453 | NetworkX graph build/query, sync suggestions, external polling | `GraphEngine(project_root)`, `scan_all()`, `update_file()`, `get_graph_data()`, `get_dependencies()`, `get_stats()`, `poll_external_files()`, `_generate_suggestions()`, `_rule_matches()`, `_find_parent_index()`, `SyncSuggestion`, `ChangeEvent` |
| `parser.py` | 185 | Markdown link extraction, file classification | `parse_file()`, `resolve_link_target()`, `extract_md_links()`, `strip_root()`, `Link`, `FileInfo` |
| `watcher.py` | 133 | watchdog observer wrapper with debounce | `FileWatcher(project_root, on_change)`, `MindxEventHandler`, `start()`, `stop()`, `restart()`, `_should_ignore()`, `_should_track()`, `_debounce_check()` |
| `config.py` | 199 | config.yaml management, constants | `load_config()`, `save_config()`, `add_project()`, `remove_project()`, `get_project_config()`, `FILE_TYPES`, `SYNC_RULES`, `IGNORE_PATTERNS`, `HOST`, `PORT` |
| `templates/index.html` | 291 | Single-page app HTML | Project tabs, file tree panel, 4 tab panels (ref-tree/dir-tree/dep-graph/detail), settings modal, confirm/error modals, folder-picker input |
| `static/css/style.css` | 949 | Dark theme CSS | `:root` CSS variables, `[data-theme="light"]` override, component styles for tree, graphs, detail panel, modals, feeds |
| `static/js/app.js` | 553 | All frontend logic | Global `S` state object, ~60 functions (see §5) |

**Supporting files:**

| File | Purpose |
|------|---------|
| `config.yaml` | Runtime config (auto-generated on first run) |
| `requirements.txt` | Python dependencies |
| `start-mindx.ps1` / `stop-mindx.ps1` | PowerShell start/stop scripts |

---

## 3. API Reference

### REST Endpoints

```
GET  /
  → renders templates/index.html

GET  /api/status
  → {running: bool, project_name: str|null, project_root: str|null,
     watching: bool, stats: {total_files, total_edges, total_nodes_graph,
     file_types: {...}, recent_changes}}

GET  /api/projects
  → [{name: str, root: str, exists_on_disk: bool}]

POST /api/projects/add
  body: {root: "C:/path", name?: "optional"}
  → {success: bool, project?: {name, root}, error?: str}

POST /api/projects/remove
  body: {name: str}
  → {success: bool}

POST /api/projects/select
  body: {name: str}
  → {success: bool, stats: {...}, file_count: int}
  side-effect: emits SocketIO "project_switched"

GET  /api/files
  → [{path, type, exists, size, last_modified, link_count, backlink_count}]

GET  /api/file/<path:file_path>
  → {path, type, exists, abs_path, size, last_modified,
     links: [{target, anchor, context}],
     dependencies: {path, references: [{path, type, link_type}],
                    referenced_by: [{path, type, link_type}]},
     issues: [{type: "broken_link", target, detail}]}

GET  /api/graph
  → {nodes: [{id, label, group, is_external, mounted, title}],
     edges: [{from, to, label, title, is_external}]}

GET  /api/scan
  → triggers full re-scan of active project
  → {total_files, total_edges, total_nodes_graph, file_types, recent_changes}

GET  /api/changes?limit=N
  → [{timestamp, file, event, suggestion_count}]  (most recent first)

GET  /api/sync-check
  → [{changed_file, target, reason, action, severity}]

POST /api/pick-folder
  → {path: str|null, error?: str}  (opens tkinter folder dialog)

POST /api/pick-file
  → {path: str|null, error?: str}  (opens tkinter file dialog)

POST /api/external/add
  body: {path: str}
  → {success: bool, added: [str], count: int}

POST /api/external/remove
  body: {path: str}
  → {success: bool}

GET  /api/external/list
  → [{path, label, exists}]

POST /api/positions/save
  body: {key: str, positions: {nodeId: {x, y}}}
  → {success: bool}

GET  /api/positions/load
  → {reftree_positions: {...}, dirtree_positions: {...}, dep_positions: {...}}

GET  /api/settings/load
  → {file_classes: {}, excluded_dirs: [], display_mode: "full"|"ref",
     ref_roots: [], active_root: str|null}

POST /api/settings/save
  body: {file_classes?, excluded_dirs?, display_mode?, ref_roots?, active_root?}
  → {success: bool}
```

### SocketIO Events (server → client)

| Event | Payload | When emitted |
|-------|---------|--------------|
| `file_changed` | `{file, event, timestamp}` | Any watched .md file changes |
| `sync_needed` | `{file, event, suggestions: [{target, reason, severity, action}]}` | File change triggers a sync rule or backlink |
| `project_switched` | `{name, root, files, graph}` | `/api/projects/select` called |
| `external_changed` | `{file, label, prev_exists, now_exists, prev_mtime, now_mtime}` | Polling detects external file change (30s interval) |

---

## 4. Data Flow

### Main scan pipeline

```
Project folder (.md files)
  → scan_all(): rglob all .md, skip IGNORE_PATTERNS with _should_ignore()
  → parse_file(abs_path, project_root): extract [text](path) links → Link objects
  → FileInfo stored in engine.files{rel_path: FileInfo}
  → _build_edges(): add nodes + edges to nx.DiGraph
    - Handles external targets (outside project_root) with is_external=True
    - Handles targets that exist but weren't scanned yet (deferred parse)
  → get_graph_data(): convert DiGraph to {nodes, edges} JSON
  → /api/graph → frontend S.graphData
  → buildRefTree() → addDirGroups() → renderFileTree()
  → renderMemoryRefTree() / renderMemoryDirTree() → vis.js Network
  → renderDepGraph() → vis.js force-directed Network
```

### External file flow

```
/api/external/add {path}
  → If directory: rglob *.md, add each as external node + FileInfo
  → If file: add single external node + FileInfo
  → _persist_external(): save path to config.yaml external_paths
  → On restart: _load_externals() re-mounts from config.yaml

Background: _poll_external_files() runs every 30s
  → Re-stat all external nodes
  → If exists/mtime changed → emit SocketIO "external_changed"
```

### Sync suggestion flow

```
File change event (watcher)
  → update_file(rel_path, event)
  → _generate_suggestions():
    1. Check SYNC_RULES for explicit rule matches
    2. Find graph backlinks (files referencing the changed file)
    3. Handle broken links from deletion
    4. Find parent _index.md for created/deleted files
  → Deduplicate by (target, action)
  → Return SyncSuggestion list
  → Server emits "sync_needed" via SocketIO
```

### Settings flow

```
Frontend save → POST /api/settings/save → config.yaml (per-project keys)
Frontend load → GET /api/settings/load → _settingsCache → lsSet('settings', cache)
```

### Positions flow

```
vis.js dragEnd → savePosition(key, net) → POST /api/positions/save
initAll() → GET /api/positions/load → lsSet(key, positions) for each key
Render → lsGet(key) for saved positions, apply to vis.js nodes
```

---

## 5. Frontend Architecture

### State object `S`

All global frontend state lives in the `S` object (defined at top of `app.js`):

```javascript
S = {
  files: [],              // [{path, type, exists, size, last_modified, link_count, backlink_count}]
  selectedFile: null,     // currently selected file path (string)
  socket: null,           // Socket.IO client instance
  netRefTree: null,       // vis.js Network — reference tree graph
  netDirTree: null,       // vis.js Network — directory tree graph
  netDepGraph: null,      // vis.js Network — dependency graph
  graphData: null,        // {nodes: [...], edges: [...]} from /api/graph
  lastScan: null,         // timestamp of last scan
  treeMode: 'dir',        // 'dir' | 'ref'
  showCore: true,         // filter: core files
  showBase: true,         // filter: base files
  showStandalone: true,   // filter: standalone files
  showExternal: false,    // filter: external files
  showHidden: false,      // filter: hidden files
  staleMap: {},           // {path: true} for files with outdated references
  projects: [],           // [{name, root, exists_on_disk}]
  activeProject: null,    // {name, root}
  selectMode: false,      // multi-select mode active
  selectedFiles: new Set(),  // batch selection set
  reachableSet: new Set(),   // files reachable from active ref root
}
```

### Key Functions (grouped by concern)

**File Tree:**
- `renderFileTree()` — main tree renderer; builds ref/dir tree, filters, renders nodes
- `buildRefTree(graphData)` — builds hierarchical tree from graph edges
- `addDirGroups(nodes)` — wraps nodes into directory group nodes
- `wrapExternalRoots(nodes)` — wraps external files under a virtual root
- `filterRefTree(nodes, visiblePaths)` — recursively filters tree by visibility
- `renderRefNode(container, node, depth)` — renders single tree node (file or group)
- `mergeSuperGroups(node)` — merges overlapping groups at depth=0 only (called internally by `addDirGroups`)

**Graphs (vis.js):**
- `renderMemoryRefTree(container)` — reference tree: hierarchical then force layout
- `renderMemoryDirTree(container)` — directory tree: manual x,y layout, physics off
- `renderDepGraph()` — force-directed dependency graph

**Settings:**
- `getSettings()` — returns `_settingsCache` or localStorage fallback
- `saveSettings(s)` — updates cache + localStorage + POST /api/settings/save
- `loadSettings()` — async fetch from /api/settings/load, cache to localStorage
- `applySettings()` — recompute reachable set, stale map, renderAll()
- `computeReachable(rootPath)` — BFS from root path, populates S.reachableSet

**Classification:**
- `getClassification(path)` — returns class for path (overrides → defaults)
- `getDefaultClassification(path)` — built-in rules: BASE_DEFAULT, STANDALONE_DEFAULT, core/external
- `setClassification(path, cls)` — save override to settings + localStorage
- `isFileVisible(path)` — combines excluded check → hidden filter → display_mode reachable check → classification filters
- `isVisibleInGraph(path)` — graph-specific: hidden + reachable + external visibility (no classification filters)
- `isExcluded(path)` — checks path against settings.excludedDirs

**UI:**
- `showSettings()` / `hideSettings()` — toggle settings modal
- `showCtxMenu(e, path)` — context menu for file
- `showModal(title, content, buttons)` — generic modal
- `showToast(msg)` — timed toast notification
- `renderProjectTabs()` — renders project tab bar + dropdown

**Filter/Select:**
- `onFilterChange(e)` — syncs all filter checkboxes, calls renderAll()
- `toggleSelectMode()` — enables drag-select mode
- `batchAction(action)` — execute action on selectedFiles set
- `toggleFileSelect(path)` — add/remove from selectedFiles
- `batchHideSelected()` / `batchCancel()` — batch operations

**Project Management:**
- `loadProjects()` — fetch /api/projects, render tabs, auto-select first
- `addProject()` — trigger folder picker, POST /api/projects/add
- `removeProject(name)` — POST /api/projects/remove
- `selectProject(name)` — POST /api/projects/select
- `handleProjectSwitched(data)` — SocketIO handler: update state, re-render

**Network:**
- `connectSocket()` — init Socket.IO, register event handlers
- `initAll()` — main bootstrap: loadProjects → loadSettings → fetchFiles → fetchGraph → loadPositions → renderAll
- `fetchFiles()` — GET /api/files → S.files
- `fetchGraph()` — GET /api/graph → S.graphData
- `api(url)` — simple fetch helper

**Detail Panel:**
- `selectFile(path)` — set S.selectedFile, fetch detail, focus in all graphs
- `fetchFileDetail(path)` — GET /api/file/{path}
- `renderDetail(data)` — populate detail panel DOM

**Positions:**
- `savePosition(key, net)` — POST /api/positions/save with current positions
- `saveRefTreePositions()` / `saveDirTreePositions()` / `saveDepPositions()` — shortcuts
- `loadPositionsFallback()` — GET /api/positions/load → lsSet for each key

**Utility:**
- `lsGet(k)` / `lsSet(k, v)` — localStorage with project-scoped key via `pkey(k)`
- `pkey(k)` — prefixes key: `mindx_${projectName}_${k}`
- `parentDir(p)` / `baseName(p)` — path manipulation
- `getFileIcon(ft)` — emoji icon for file type
- `getNodeColor(ftype, path)` — color based on classification
- `getGroupColor(ft)` — color based on file type
- `getFtypeLabel(ft)` — Chinese label for file type
- `getMemoryLevel(p, ft)` — returns L1/L2/L3/null
- `computeStaleMap()` — marks files whose targets are newer than source
- `bumpReadCount(path)` / `getReadCount(path)` — read tracking in localStorage

### Rendering pipeline

```
connectSocket()
  → on('connect') → initAll()
    → loadProjects() → loadSettings() → fetchFiles() → fetchGraph()
    → loadPositionsFallback() → renderAll()

renderAll() → renderFileTree() + renderRefTreeGraph() + renderDirTreeGraph() + renderDepGraph()

On file_changed event:
  → fetchFiles() → fetchGraph() → computeReachable (if ref mode) → renderAll()

On project_switched event:
  → handleProjectSwitched() → update S state → loadSettings() → renderAll()
```

---

## 6. Modification Guide

### Adding a backend API endpoint

1. Add the route function to `server.py` **before** the `# Startup` section (around line 536)
2. Access current project: `active_project` (global string), `engines.get(active_project)` for engine
3. Access config: `get_project_config(_config, active_project)`
4. Return `jsonify({...})`
5. For POST: `data = request.get_json(force=True)`
6. For SocketIO push: `socketio.emit("event_name", payload)`

### Adding a frontend feature

1. Add HTML elements to `templates/index.html`
2. Add CSS to `static/css/style.css` — use CSS variables from `:root`
3. Add JS functions to `static/js/app.js` — place near related functions
4. Register event listeners near the bottom of `app.js` (after line 500)
5. Use `S` object for shared state
6. Use `lsGet(k)` / `lsSet(k, v)` for persisting to localStorage (runtime cache, project-scoped)
7. Use `fetch('/api/...')` for server communication
8. After data changes, call `renderAll()` to refresh all views

### Adding a filter/classification

1. Add `S.showXxx = true` to the `S` initialization (top of `app.js`)
2. Add checkbox HTML with class `filter-xxx` and id `chk-show-xxx` in the filter bar
3. Add visibility logic to `isFileVisible()` — check `S.showXxx`
4. Add visibility logic to `isVisibleInGraph()` if graph filtering is desired
5. Register event listener: `document.querySelectorAll('.filter-xxx').forEach(cb => cb.addEventListener('change', e => onFilterChange(e)));`
6. Update `onFilterChange()` to sync the new checkbox
7. Add CSS class `cls-xxx` for visual indicator in the tree
8. If persisting: add to settings flow (load/save)

### Modifying the directory tree graph layout

1. Edit `renderMemoryDirTree(container)` in `app.js`
2. `dirMap` object maps directory paths to `{name, subdirs: Set, files: [], _total}`
3. `layoutDir(dir, x, w, depth)` recursively positions directories and children
4. Directory nodes receive explicit `x, y` coordinates
5. Constants: `Y_DIR=110, Y_FILE=80, X_UNIT=100, X_MIN=60`
6. Physics is **disabled** (`physics: {enabled: false}`)
7. Root node `__ROOT__` at `(0, 0)` with project name

### Adding a sync rule

1. Add entry to `SYNC_RULES` list in `config.py`
2. Fields: `trigger` ("file_modified"|"file_created"|"file_deleted"), `pattern`, `target`, `action`, `reason`
3. Pattern matching in `_rule_matches()`: exact match, prefix match, glob `/*.md`, `/*/`
4. Actions: "self_document", "l3_to_l2_sync", "index_update", "project_sync", "sibling_sync", "broken_link_fix"
5. Severities: "critical", "warning", "info"

### Adding an external file type to track

1. Currently only `.md` files are tracked (`_should_track()` in `watcher.py` checks `path.suffix == ".md"`)
2. To add new extensions: modify `_should_track()` in `watcher.py` AND `rglob("*.md")` in `graph_engine.scan_all()` AND `/api/external/add` handler
3. Also update `extract_md_links()` in `parser.py` if new link formats are needed

---

## 7. Gotchas & Conventions

### Path handling

- **File paths MUST use forward slashes**: All paths normalized with `.replace("\\", "/")` before use — applies to both server and frontend
- **External files use absolute paths** as graph node IDs (e.g., `C:/path/to/external.md`)
- **Project-internal files use relative paths** from project root (e.g., `memory/tools/system.md`)
- **`isExcluded()` must work for both absolute and relative paths** — uses tail-segment matching: splits path by `/`, checks each suffix against excluded dirs
- **File-vs-dir in exclude list**: Files added with extension (`.md`) are stored as-is. Directories stored with trailing `/`. This affects `isExcluded` matching.

### Edit tool safety

- **`oldString=""` in edit tool DESTROYS files** — never use empty string as edit anchor. Always provide a real line of code.
- **Always verify file content with Read before editing** — the edit tool requires prior Read
- **Complex changes delegate to agent**: `task(category="deep"|"quick")` — do NOT directly edit/write large changes

### Frontend specifics

- **`S` is the single state source** — all views read from S. Modify S, then call `renderAll()`.
- **localStorage keys are per-project**: `pkey(k)` prefixes with `mindx_${projectName}_`
- **vis.js containers must have dimensions** when Network is initialized — uses `tab-content.active { display: flex }`
- **Group nodes** have `isGroup: true` and synthetic paths like `__dir_memory/tools/`, `__extroot__`
- **`mergeSuperGroups` only runs at depth=0** — prevents false merges at deeper levels
- **Tab switching triggers `redraw()`** on vis.js networks after 100ms timeout (container needs to be visible first)
- **Reference tree graph** uses hierarchical layout on first render, destroys and recreates with free-form physics after 1.5s. On subsequent renders, starts free-form directly.
- **`onFilterChange`** is the single handler for ALL filter checkboxes across all tabs. It reads `e.target.id` to determine which filter changed.

### Server specifics

- **Server-side constants** in `config.py`: `FILE_TYPES` (classification mapping by path), `SYNC_RULES` (trigger rules), `IGNORE_PATTERNS` (scanner/watcher skip patterns)
- **External file polling** runs in a daemon thread every 30 seconds (`POLL_INTERVAL = 30`)
- **Change log is capped** at 200 entries (`_max_changes = 200`)
- **Watcher debounce**: 500ms between events for the same file to avoid duplicates
- **Port conflict**: Server exits with error message (does NOT auto-switch ports)

### Config persistence

- **Config saved immediately** on any mutation — add_project, remove_project, settings save, positions save, external add/remove
- **External paths are normalized** to absolute with forward slashes before persisting to config.yaml
- **Settings are cached** in `_settingsCache` (JS memory) and localStorage as fallback. Server is the source of truth on startup.

---

## 8. Git Workflow

### Before any edit session

```bash
git add -A && git commit -m "snapshot before changes"
```

### After each successful edit

```bash
git add -A && git commit -m "description of change"
```

### Recover lost file

```bash
git checkout -- path/to/file
```

### DO NOT

- Skip commits — they are the only recovery mechanism
- Amend commits that have been referenced externally
- Use `--force` on any git operation
- Commit `config.yaml` with sensitive paths (add to `.gitignore` if needed)
- Use `git reset --hard` unless explicitly requested

### Commit message style

- Use concise descriptions of the change
- Prefix with area when clear: `server:`, `frontend:`, `config:`, `parser:`
- Examples: `server: add /api/export endpoint`, `frontend: add dark mode toggle`, `config: sync rules for L3 tools`
