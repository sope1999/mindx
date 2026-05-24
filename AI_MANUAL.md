# mindx v4.5：AI 可读项目手册

> 本文档是 AI agent 处理 mindx 项目时的唯一事实来源。
> 最近一次按源码核验：2026-05-23。

## 目录

1. [项目概览](#1-project-overview)
2. [文件地图](#2-file-map)
3. [API 参考](#3-api-reference)
4. [数据流](#4-data-flow)
5. [前端架构](#5-frontend-architecture)
6. [修改指南](#6-modification-guide)
7. [易错点与约定](#7-gotchas--conventions)
8. [Git 工作流](#8-git-workflow)

---

## 1. Project Overview

**mindx** 是本地优先的记忆索引仪表盘。它扫描一个 Markdown 文件夹，从 `[text](path)` 链接中建立有向依赖图，并在浏览器中用图形界面展示结果，同时通过 `watchdog` 监听文件变化。

**技术栈：**

| 层级 | 技术 |
|------|------|
| 后端 | Python 3、Flask、Flask-SocketIO、watchdog、NetworkX |
| 前端 | 原生 HTML、CSS、JavaScript、vis-network |
| 配置 | YAML，文件名为 `config.yaml` |
| 运行方式 | `python server.py`，默认地址 `http://127.0.0.1:5020` |

**架构流水线：**

```text
server.py  调度  graph_engine  扫描  parser  提取  Link 对象
    │                 │
    ├─ watcher 监听 ─► │
    │                 └─ _build_edges() ─► nx.DiGraph
    │                                          │
    └─ SocketIO 推送 ─► /api/graph ──────────► 前端 S.graphData
                                               └─► vis-network 图
```

**配置结构**，位于 `config.yaml`：

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

| 文件 | 约行数 | 用途 | 关键项 |
|------|--------|------|--------|
| `server.py` | 995 | Flask 路由、SocketIO 事件、多项目管理、外部文件轮询、启动流程 | `active_project`、`engines{}`、`watchers{}`、`init_engine()`、`_load_externals()`、`_poll_external_files()`、全部 `/api/*` 路由、`run_server()` |
| `graph_engine.py` | 552 | NetworkX 图构建与查询、同步建议、外部文件轮询、历史持久化 | `GraphEngine(project_root)`、`scan_all()`、`update_file()`、`get_graph_data()`、`get_dependencies()`、`get_stats()`、`poll_external_files()`、`_generate_suggestions()`、`_rule_matches()`、`_find_parent_index()`、`SyncSuggestion`、`ChangeEvent` |
| `parser.py` | 230 | Markdown 链接提取、文件分类、文件元数据 | `parse_file()`、`resolve_link_target()`、`extract_md_links()`、`strip_root()`、`Link`、`FileInfo`、`_classify_file()` |
| `watcher.py` | 157 | `watchdog` observer 包装与 500ms 防抖 | `FileWatcher(project_root, on_change)`、`MindxEventHandler`、`start()`、`stop()`、`restart()`、`_should_ignore()`、`_should_track()`、`_debounce_check()` |
| `config.py` | 199 | `config.yaml` 管理与常量 | `load_config()`、`save_config()`、`add_project()`、`remove_project()`、`get_project_config()`、`FILE_TYPES`、`SYNC_RULES`、`IGNORE_PATTERNS`、`HOST`、`PORT` |
| `mcp_server.py` | 约 470 | MCP stdio 服务，通过 HTTP 代理调用 Flask | 16 个 MCP 工具，覆盖项目、图、文件、反向链接、断链、断链静默、历史、扫描和同步建议 |
| `templates/index.html` | 约 291 | 单页应用 HTML | 项目标签、文件树面板、4 个标签页，`ref-tree`、`dir-tree`、`dep-graph`、`detail`，设置弹窗、确认弹窗、错误弹窗、文件夹选择输入 |
| `static/css/style.css` | 约 949 | 深色与浅色主题 CSS | `:root` 变量、`[data-theme="light"]` 覆盖、树、图、详情面板、弹窗、信息流样式 |
| `static/js/app.js` | 902 | 全部前端逻辑 | 全局 `S` 状态对象、分类、树、图、设置、项目、SocketIO、标签切换、重命名、历史面板等函数 |
| `tests/` | 不适用 | Python 与 JavaScript 回归测试 | `test_parser.py`、`test_graph_engine.py`、`test_server.py`、`test_mcp_server.py`、`app.test.js`。当前收集到 103 个 pytest 测试，`app.test.js` 中有 65 个 Jest 测试 |

**辅助文件：**

| 文件 | 用途 |
|------|------|
| `config.yaml` | 运行时配置，首次运行会自动生成或补齐默认结构 |
| `requirements.txt` | Python 依赖 |
| `requirements-mcp.txt` | MCP 服务依赖，包含 `mcp`、`requests` |
| `package.json` / `jest.config.js` | Jest 测试基础设施 |
| `.gitignore` | 忽略 `node_modules`、`__pycache__`、`.pytest_cache` 等生成文件 |
| `start-mindx.ps1` / `stop-mindx.ps1` | PowerShell 启动与停止脚本 |

---

## 3. API Reference

### REST 端点

```text
GET  /
  返回 templates/index.html

GET  /api/status
  返回 {running, project_name, project_root, watching, stats}
  stats 来自 GraphEngine.get_stats()，包含 total_files, total_edges,
  total_nodes_graph, file_types, recent_changes

GET  /api/projects
  返回 [{name, root, exists_on_disk}]

POST /api/projects/add
  body: {root: "C:/path", name?: "optional"}
  返回 {success, project?, error?}

POST /api/projects/remove
  body: {name}
  返回 {success}

POST /api/projects/select
  body: {name}
  返回 {success, stats, file_count}
  副作用：停止旧 watcher，初始化或重启目标 watcher，发送 SocketIO 事件 "project_switched"

GET  /api/files
  返回 [{path, type, exists, size, last_modified, link_count, backlink_count, is_external?, mounted?, external_status?}]

GET  /api/file/<path:file_path>
  返回 {path, dependencies, type?, exists?, size?, abs_path?, last_modified?, links?, issues, is_external?, mounted?, external_status?}
  links: [{target, anchor, context, is_external?, mounted?, external_status?, target_exists?}]
  dependencies: {path, references: [{path, type, link_type, is_external?, mounted?, external_status?}], referenced_by: [{path, type, link_type}]}
  issues: [{type: "broken_link", target, detail, is_external?}]

GET  /api/file/<path:file_path>/backlinks
  返回 {backlinks: [{from, link_type, context}]}

GET  /api/broken-links
  返回 {broken_links: [{file, target, link_type, context, is_external?, external_status?, target_exists?}], count, total_count?}

GET  /api/graph
  返回 {nodes: [{id, label, group, title, is_external, mounted, external_status?}], edges: [{from, to, label, title, is_external, external_status?}]}

GET  /api/scan
  执行 engine.scan_all()，随后调用 _load_externals(active_project, engine)
  返回 {total_files, total_edges, total_nodes_graph, file_types, recent_changes}

GET  /api/changes?limit=N
  返回最近变更，格式 [{timestamp, file, event, suggestion_count}]，最新在前

GET  /api/history?days=3&type=all|changes|sync
  返回 .mindx/history.json 中的持久化历史，days 最大被限制为 3
  返回 {history, count}

GET  /api/sync-check
  对每个文件按 modified 和 created 生成建议
  返回 [{changed_file, target, reason, action, severity}]

POST /api/pick-folder
  打开 tkinter 文件夹选择框
  返回 {path, error?}

POST /api/pick-file
  打开 tkinter 文件选择框，默认筛选 Markdown
  返回 {path, error?}

POST /api/external/add
  body: {path}
  目录会 rglob("*.md") 并把每个 Markdown 文件挂载为外部节点
  文件会挂载单个外部节点
  返回 {success, added, count}

POST /api/external/remove
  body: {path}
  返回 {success, error?}

GET  /api/external/list
  返回 [{path, label, exists}]

POST /api/positions/save
  body: {key, positions: {nodeId: {x, y}}}
  返回 {success}

GET  /api/positions/load
  返回当前项目配置中的 positions 对象，常见键为 reftree_positions, dirtree_positions, dep_positions

GET  /api/settings/load
  返回 {file_classes, excluded_dirs, display_mode, ref_roots, active_root}

POST /api/settings/save
  body 可包含 file_classes, excluded_dirs, display_mode, ref_roots, active_root
  返回 {success}

POST /api/file/rename-preview
  body: {path, new_name}
  返回 {success, old_path, new_path, affected_count, changes}
  changes: [{file, changes: [{old_link, new_link, context}]}]

POST /api/file/rename-execute
  body: {path, new_path}
  返回 {success, old_path, new_path, updated_files, error?}
```

### SocketIO 事件，服务端到客户端

| 事件 | 载荷 | 触发时机 |
|------|------|----------|
| `file_changed` | `{file, event, timestamp}` | watcher 回调发现项目内 Markdown 文件发生变化 |
| `sync_needed` | `{file, event, suggestions: [{target, reason, severity, action}]}` | `update_file()` 返回同步建议时 |
| `project_switched` | `{name, root, files, graph}` | 调用 `/api/projects/select` 成功后 |
| `external_changed` | `{file, label, prev_exists, now_exists, prev_mtime, now_mtime}` | 外部文件轮询发现存在状态或 mtime 变化，轮询间隔 30 秒 |

---

## 4. Data Flow

### 线程模型

```text
三个并发路径可能接触项目状态：
  1. Flask 请求处理函数
  2. watchdog observer 回调
  3. 外部文件轮询线程

GraphEngine.__init__ 中创建 self._lock = threading.RLock()。
scan_all(), update_file(), get_graph_data(), get_dependencies(), get_stats(), poll_external_files()
都会在公开方法内部加锁读写 engine.files 或 engine.graph。
不要绕过公开方法直接读写图数据。
```

### 主扫描流水线

```text
项目文件夹中的 .md 文件
  → scan_all(): 用 project_root.rglob("*.md") 遍历，按 IGNORE_PATTERNS 跳过
  → parse_file(abs_path, project_root): 提取 [text](path) 链接，生成 Link 对象
  → FileInfo 存入 engine.files{rel_path: FileInfo}
  → NetworkX 节点写入 nx.DiGraph
     项目内普通节点属性：type, exists, label
     外部链接节点属性：type, exists, label, is_external, abs_path, size, last_modified
     显式挂载外部节点还会带 mounted
  → _build_edges(): 添加有向边
     处理项目外目标，标记 is_external=True
     处理存在但未扫描的目标，延迟 parse 后加入图
  → get_graph_data(): 转为 {nodes, edges} JSON
     节点 JSON 字段为 id, label, group, title, is_external, mounted
     边 JSON 字段为 from, to, label, title, is_external
  → /api/graph → 前端 S.graphData
  → buildRefTree() → addDirGroups() → renderFileTree()
  → renderMemoryRefTree() / renderMemoryDirTree() → vis-network
  → renderDepGraph() → vis-network 力导向图
```

### Markdown 引用规范，AI 编写指南

> **目的**：确保 AI agent 管理 `.md` 文件时使用 mindx 能识别的引用格式，让依赖图准确反映文件关系。

**识别规则：**

mindx 使用正则 `\[([^\]]*?)\]\(([^)]+)\)` 提取链接。实际规则如下：

| 格式 | 识别 | 说明 |
|------|:---:|------|
| `[文本](相对路径.md)` | ✅ | 标准格式 |
| `[文本](子目录/文件.md)` | ✅ | 子目录相对路径 |
| `[文本](../上级/文件.md)` | ✅ | 上级目录相对路径，解析后若不在项目根目录内则视为外部 |
| `[文本](文件.md#锚点)` | ✅ | `#锚点` 会被剥离 |
| `[文本](文件.md "标题")` | ✅ | 结尾的链接标题会被剥离 |
| `[文本](file:///C:/资料/文件.md)` | ✅ | `file:///` 是本机路径链接语法，解析后按外部路径处理 |
| `- [文本](文件.md)` | ✅ | 列表项中的链接 |
| 表格内的 `[文本](path)` | ✅ | 表格单元格引用 |
| `![图片](path.png)` | ⚠️ | 正则仍可能匹配其中的 `[图片](path.png)`，但目标通常不是 `.md`，若文件不存在也不会加入图 |
| `[文本](https://网址)` | ❌ | `raw_target.startswith("http")` 时跳过 |
| `[文本](C:\绝对\路径.md)` | ⚠️ | 作为链接目标解析；是否外部取决于 `Path.resolve()` 后是否位于 project_root 内 |
| `[文本](//server/share/file)` | ✅ | UNC 路径被标记为外部 |
| `[文本](file.md)` 纯文件名 | ✅ | 按当前文件所在目录解析 |

**路径规则：**

1. **优先使用相对路径**，从当前文件所在目录出发，指向项目内另一个 `.md` 文件。
2. **优先使用正斜杠 `/`**，Windows 路径会在多处通过 `.replace("\\", "/")` 标准化。
3. **文件名按文件系统规则匹配**，源码没有做大小写纠正。
4. **空格可以存在**，但建议避免 `<`、`>`、`"`、`|`、`?`、`*`。
5. **`file:///` 不是新挂载模型**，它只提供本机绝对路径写法；是否挂载仍由 `external_paths` 决定。
6. **`external_paths` 是手动挂载边界**，目录只覆盖其中的 Markdown 文件；挂载目标只有被项目根或引用根链路触达时才进入引用链显示。
7. **未挂载但存在的外部目标** 会作为叶子外部引用节点出现，不递归展开。
8. **不存在的内部或外部目标都是断链**，`/api/file/<path>` 和 `/api/broken-links` 会报告；MCP 不制造状态，只透传后端提供的 external_status、mounted、target_exists 等字段。

**AI 编写最佳实践：**

```markdown
# 正确
- 工具配置见 [TOOLS.md](TOOLS.md)
- 开发记录在 [dev-sessions.md](memory/projects/aviation/dev-sessions.md)
- 规则说明见 [工作规则](../项目开发工作规则.md)

# 错误
- [TOOLS](C:\SOFT\AI\coder\TOOLS.md)
- [github](https://github.com/xxx)
- ![截图](shot.png)
- [TOOLS](.\TOOLS.md)
```

**文件分类影响：**

后端 `parser.py` 的 `_classify_file()` 先查可传入的 `file_types` 映射，再按路径启发式分类为 `tool_l3`、`tool_standalone`、`project_overview`、`project_progress`、`dev_sessions`、`project_file`、`archive_index`、`diary`、`root_doc` 或 `unknown`。当前 `scan_all()` 和 `update_file()` 调用 `parse_file()` 时没有传入 `FILE_TYPES`。

前端 `app.js` 还有独立显示分类：`BASE_DEFAULT` 在第 17 行定义，`getClassification(path)` 在第 27 行读取本地覆盖后调用 `getDefaultClassification(path)`。默认显示分类包括 `base`、`external`、`standalone`、`core`。

**IGNORE_PATTERNS 的源码精确列表：**

```python
IGNORE_PATTERNS = [
    ".git", ".claude", ".learnings", ".openclaw",
    "*.pyc", "temp/*", "temp_docs/*",
    "docs/*", "warning/*",
]
```

### 外部文件流程

```text
/api/external/add {path}
  → 如果 path 是目录：rglob("*.md")，把每个文件加入外部节点与 engine.files
  → 如果 path 是文件：加入单个外部节点与 engine.files
  → _persist_external(): 将规范化后的绝对路径写入 config.yaml 的 external_paths
  → 重启后：_load_externals() 从 config.yaml 重新挂载

后台：_poll_external_files() 每 30 秒运行一次
  → engine.poll_external_files() 重新 stat 外部节点
  → exists 或 last_modified 变化时发送 SocketIO 事件 "external_changed"
```

`/api/scan` 会执行 `scan_all()`，然后调用 `_load_externals(active_project, engine)`，所以全量重扫后已挂载的外部文件会回到图里。

### 同步建议流程

```text
文件变化事件，来自 watcher
  → update_file(rel_path, event)
  → _generate_suggestions(changed_file, event, broken_refs):
     1. 遍历 config.py 的 SYNC_RULES，匹配 trigger 与 pattern
     2. 对 modified 或 deleted，查找图中的入边，也就是引用 changed_file 的文件
     3. 对 deleted，处理删除前记录的 broken_refs
     4. 对 created 或 deleted，查找最近的父级 _index.md，找不到则回退 MEMORY.md
  → 按 (target, action) 去重
  → 返回 SyncSuggestion 列表
  → server.py 通过 SocketIO 发送 "sync_needed"
```

`SYNC_RULES` 的匹配方式在 `_rule_matches()` 中实现：`trigger` 必须等于 `file_` 加事件名；`pattern` 支持以 `/` 结尾的前缀匹配、以 `/*/` 结尾的目录层级匹配、以 `/*.md` 结尾的 Markdown 前缀匹配，以及精确匹配。

### 设置流程

```text
前端保存 → POST /api/settings/save → save_config(_config)
前端加载 → GET /api/settings/load → _settingsCache → lsSet('settings', cache)
```

### 历史流程

```text
change 与 sync 事件
  → GraphEngine._save_history_entry(entry)
  → 追加到内存 self._history
  → 清理超过 3 天的记录
  → 写入 .mindx/history.json.tmp
  → os.replace(tmp, .mindx/history.json)
  → GET /api/history?days=3&type=all|changes|sync 读取
```

### 坐标流程

```text
vis-network dragEnd → savePosition(key, net) → POST /api/positions/save
initAll() → loadPositionsFallback() → GET /api/positions/load → lsSet(key, positions)
渲染 → lsGet(key) 读取保存坐标并应用到 vis-network 节点
```

---

## 5. Frontend Architecture

### 状态对象 `S`

全部全局前端状态都放在 `app.js` 顶部的 `S` 对象中，源码第 3 到 15 行如下：

```javascript
const S = {
  files: [], selectedFile: null, socket: null,
  netRefTree: null, netDirTree: null, netDepGraph: null, graphData: null, lastScan: null,
  treeMode: 'dir',
  showCore: true, showBase: true, showStandalone: true, showExternal: false, showHidden: false,
  staleMap: {},
  projects: [],
  activeProject: null,
  selectMode: false,
  selectedFiles: new Set(),
  reachableSet: new Set(),
  historyMode: { changes: false, sync: false },
};
```

`BASE_DEFAULT` 在第 17 行定义：`AGENTS.md`、`SOUL.md`、`USER.md`、`IDENTITY.md`、`HEARTBEAT.md`。`getClassification(path)` 在第 27 行定义，先读取 `lsGet('file_classes')` 的覆盖项，再调用 `getDefaultClassification(path)`。

### 关键函数，按职责分组

**文件树：**

- `renderFileTree()`：主树渲染器，基于引用树或目录树构建节点，应用过滤并写入 DOM。
- `buildRefTree(graphData)`：从图边构建层级引用树。
- `addDirGroups(nodes, depth)`：把节点包装进目录组节点。
- `wrapExternalRoots(roots)`：把已挂载外部文件包装到虚拟根 `__extroot__` 下。
- `filterRefTree(nodes, visiblePaths)`：按可见路径递归过滤引用树。
- `renderRefNode(container, node, depth)`：渲染单个树节点或组节点。
- `mergeSuperGroups(node)`：只在 `depth === 0` 时合并顶层重叠组，由 `addDirGroups()` 内部调用。

**图，vis-network：**

- `computeRefLevels(graphData, visiblePaths)`：用 Kahn 拓扑思路计算引用层级；孤立节点使用 `-1`。
- `renderMemoryRefTree(container)`：引用树图，使用层级布局和手工 x/y，关闭 physics，保存坐标可覆盖初始坐标。
- `renderMemoryDirTree(container)`：目录树图，使用 `dirMap` 与 `layoutDir()` 递归定位目录和文件，关闭 physics。
- `renderDepGraph()`：依赖图，使用 vis-network 的力导向布局，保存坐标可覆盖。
- `renderRefTreeGraph()` / `renderDirTreeGraph()`：根据当前标签页容器调用对应渲染函数。

**设置：**

- `getSettings()`：返回 `_settingsCache`，没有缓存时使用 localStorage 后备值。
- `saveSettings(s)`：更新缓存与 localStorage，并 `POST /api/settings/save`。
- `loadSettings()`：异步读取 `/api/settings/load`，写入缓存和 localStorage。
- `applySettings()`：重新计算 reachable set、stale map，并 `renderAll()`。
- `computeReachable(rootPath)`：从活动根文件做 BFS，写入 `S.reachableSet`。

**分类：**

- `getClassification(path)`：读取分类覆盖，失败时返回默认分类。
- `getDefaultClassification(path)`：内置规则，依次判断 `BASE_DEFAULT`、图数据缺失时返回 `external`、外部节点、DAG 不可达时 `standalone`，否则 `core`。
- `setClassification(path, cls)`：保存覆盖项到设置和 localStorage。
- `isFileVisible(path)`：综合排除规则、隐藏过滤、引用模式 reachable、分类过滤和外部文件规则。
- `isVisibleInGraph(path)`：图专用可见性，当前直接复用 `isFileVisible(path)` 并额外检查引用模式 reachable。
- `isExcluded(path)`：检查 `settings.excludedDirs`，支持绝对或相对路径的尾段匹配。

**UI：**

- `showSettings()` / `hideSettings()`：打开或关闭设置弹窗。
- `toggleHistoryPanel(type)`：右侧面板中切换实时事件或同步建议历史。
- `showCtxMenu(x, y, filePath)`：显示文件右键菜单。
- `showRenameDialog(path)`：先调用 `/api/file/rename-preview`，确认后调用 `/api/file/rename-execute`。
- `showModal(title, content, buttons)`：通用弹窗。
- `showToast(msg)`：短时提示。
- `renderProjectTabs()`：渲染项目标签栏与下拉菜单。
- `btn-rescan` 点击处理函数：调用 `/api/scan`，保持按钮加载状态，然后刷新文件和图。

**过滤与选择：**

- `onFilterChange(e)`：同步所有过滤复选框，写入全局 `mindx_filter_state`，调用 `renderAll()`。
- `toggleSelectMode()`：启用或关闭拖拽多选模式。
- `batchAction(type)`：对 `S.selectedFiles` 执行隐藏、取消隐藏、移除或恢复。
- `toggleFileSelect(path)`：向 `selectedFiles` 添加或移除文件。
- `batchHideSelected()` / `batchCancel()`：批量操作快捷函数。

**项目管理：**

- `loadProjects()`：读取 `/api/projects`，渲染标签，若没有活动项目则选择第一个。
- `addProject()`：触发文件夹选择输入。
- `handleFolderPicked()`：根据浏览器提供的文件夹名提示用户输入完整路径，再调用 `/api/projects/add`。
- `removeProject(name)`：调用 `/api/projects/remove`。
- `selectProject(name)`：调用 `/api/projects/select`。
- `handleProjectSwitched(data)`：SocketIO 回调，更新 `S.activeProject`、`S.files`、`S.graphData`，重新加载设置并渲染。

**网络：**

- `connectSocket()`：初始化 Socket.IO 客户端，注册事件处理函数。
- `initAll()`：主启动流程，加载项目、状态、设置、文件、图、坐标，然后渲染。
- `fetchFiles()`：`GET /api/files` 写入 `S.files`。
- `fetchGraph()`：`GET /api/graph` 写入 `S.graphData`，并清理 `S._dagReachable`。
- `api(url)`：简单 fetch JSON 辅助函数。

**详情面板：**

- `selectFile(path)`：设置 `S.selectedFile`，读取详情，在图中聚焦节点。
- `fetchFileDetail(path)`：读取 `GET /api/file/{path}`。
- `renderDetail(data)`：填充详情面板 DOM。

**坐标：**

- `savePosition(key, net)`：把当前图坐标 `POST /api/positions/save`。
- `saveRefTreePositions()` / `saveDirTreePositions()` / `saveDepPositions()`：坐标保存快捷函数。
- `loadPositionsFallback()`：读取 `/api/positions/load`，将各 key 写入 localStorage。

**工具函数：**

- `lsGet(k)` / `lsSet(k, v)`：基于 `pkey(k)` 的项目级 localStorage。
- `pkey(k)`：生成 `mindx_${projectName}_${k}`。
- `parentDir(p)` / `baseName(p)`：路径处理。
- `getFileIcon(ft)`：按文件类型返回 emoji。
- `getNodeColor(ftype, path)`：按分类返回节点颜色。
- `getGroupColor(ft)`：按文件类型返回组颜色。
- `getFtypeLabel(ft)`：返回中文文件类型标签。
- `getMemoryLevel(p, ft)`：返回 L1、L2、L3 或 `null`。
- `computeStaleMap()`：标记引用目标比来源文件更新的文件。
- `bumpReadCount(path)` / `getReadCount(path)`：使用 localStorage 记录阅读次数。

### 渲染流水线

```text
connectSocket()
  → on('connect') → initAll()
    → loadProjects() → /api/status → loadSettings() → fetchFiles() → fetchGraph()
    → loadPositionsFallback() → renderAll()

renderAll()
  → renderFileTree()
  → renderRefTreeGraph()
  → renderDirTreeGraph()
  → renderDepGraph()

收到 file_changed 事件：
  → addChangeEvent()
  → fetchFiles() → fetchGraph()
  → 如处于 ref 模式则 computeReachable()
  → computeStaleMap() → renderAll()

收到 project_switched 事件：
  → handleProjectSwitched()
  → 更新 S 状态
  → loadSettings()
  → renderProjectTabs() → renderAll()
```

### 当前 UI 说明

- 旧的第 5 个标签页已移除。历史记录现在位于右侧面板的切换按钮后。
- `实时事件` 与 `同步建议` 标题上的 `📋` 按钮会显示对应历史面板。
- 重扫按钮 `btn-rescan` 现在真正通过 `/api/scan` 调用后端 `scan_all()` 与 `_load_externals()`，不是刷新页面。
- 标签切换会在 100ms 后对对应 vis-network 调用 `redraw()`，因为容器需要先可见。
- `tests/app.test.js` 当前包含 65 个 Jest 测试。

---

## 6. Modification Guide

### 添加后端 API 端点

1. 在 `server.py` 中添加路由函数，位置应在 `# Startup` 区域之前。
2. 需要当前项目时通过 `_project_lock` 保护对 `active_project` 的切换逻辑，读取时使用 `engines.get(active_project)`。
3. 读取项目配置使用 `get_project_config(_config, active_project)`。
4. 使用 `jsonify({...})` 返回 JSON。
5. POST 请求读取数据使用 `data = request.get_json(force=True)`。
6. SocketIO 推送使用 `socketio.emit("event_name", payload)`。
7. 图数据通过 GraphEngine 公开方法访问，不要直接改 `engine.graph` 或 `engine.files`，除非你正在维护现有低层实现并同步处理锁。

### 添加前端功能

1. 在 `templates/index.html` 添加 HTML 元素。
2. 在 `static/css/style.css` 添加 CSS，优先使用 `:root` 中的 CSS 变量。
3. 在 `static/js/app.js` 添加 JS 函数，放在相关功能附近。
4. 事件监听器放在文件底部的 `Event listeners` 区域附近。
5. 共享状态放在 `S` 对象中。
6. 持久化运行时缓存使用 `lsGet(k)` / `lsSet(k, v)`，它们是项目级 localStorage。
7. 与服务端通信使用 `fetch('/api/...')` 或 `api(url)`。
8. 数据变化后调用 `renderAll()` 刷新全部视图。

### 添加过滤或分类

1. 在 `S` 初始化中添加 `showXxx` 字段。
2. 在过滤栏 HTML 中添加 `filter-xxx` 类与 `chk-show-xxx` id。
3. 在 `isFileVisible()` 中添加 `S.showXxx` 可见性逻辑。
4. 如果图也需要过滤，检查 `isVisibleInGraph()`。
5. 注册事件监听：`document.querySelectorAll('.filter-xxx').forEach(cb => cb.addEventListener('change', e => onFilterChange(e)));`
6. 更新 `onFilterChange()`，同步新复选框。
7. 添加 `cls-xxx` CSS 类用于树中的视觉标识。
8. 如果需要持久化，把字段加入设置加载与保存流程。

### 修改目录树图布局

1. 编辑 `app.js` 中的 `renderMemoryDirTree(container)`。
2. `dirMap` 把目录路径映射为 `{name, subdirs: Set, files: [], _total}`。
3. `layoutDir(dir, x, w, depth)` 递归定位目录和子节点。
4. 目录节点和文件节点都写入显式 `x, y` 坐标。
5. 常量为 `Y_DIR=110, Y_FILE=80, X_UNIT=100, X_MIN=60`。
6. physics 被关闭：`physics: {enabled: false}`。
7. 根节点 `__ROOT__` 位于 `(0, 0)`，标签使用当前项目名。
8. 如果节点已设置 `color`，不要再设置 `group`。vis-network 4.21 可能用默认浅色组颜色覆盖深色节点背景。

### 添加同步规则

1. 在 `config.py` 的 `SYNC_RULES` 列表中添加条目。
2. 字段为 `trigger`、`pattern`、`target`、`action`、`reason`。
3. `trigger` 使用 `file_modified`、`file_created` 或 `file_deleted`。
4. `_rule_matches()` 支持精确匹配、以 `/` 结尾的前缀匹配、`/*.md`、`/*/`。
5. 当前源码中的 action 包括 `self_document`、`l3_to_l2_sync`、`index_update`、`project_sync`、`sibling_sync`、`broken_link_fix`。
6. 当前源码中显式生成的 severity 包括 `critical`、`warning`、`info`。

### 添加要跟踪的外部文件类型

1. 当前 watcher 只跟踪 `.md` 文件和目录结构，`_should_track()` 中检查 `path.suffix == ".md"`。
2. 若增加扩展名，需要同时修改 `watcher.py` 的 `_should_track()`、`graph_engine.scan_all()` 的 `rglob("*.md")`、`server.py` 中 `/api/external/add` 和 `_load_externals()` 的 `rglob("*.md")`。
3. 如果新增链接格式，还要修改 `parser.py` 的 `extract_md_links()` 或相关解析函数。

### 重命名文件

1. `/api/file/rename-preview` 在写入前计算引用修改预览。
2. `/api/file/rename-execute` 会先改引用文件内容，再重命名磁盘文件。
3. 执行后源码仍会直接移除旧图节点和 `engine.files` 条目，然后对受影响文件调用 `update_file(f, "modified")`，并对新文件调用 `update_file(new_path, "created")`。
4. 维护这段逻辑时，应以 `update_file()` 作为重新注册文件与重建边的入口，不要手动拼接边数据。

### 重启 watcher

1. `watchdog` 的 observer 停止后不能直接复用。
2. `FileWatcher.stop()` 会停止并 `join()`，然后把 `observer` 设为 `None`。
3. `FileWatcher.restart()` 会停止旧 watcher，更新 root 和回调，调用 `_setup_observer()` 重建 observer，再按需 `start()`。

### 持久化配置和历史

1. `config.yaml` 通过 `save_config()` 写入，采用临时文件加 `os.replace()` 的原子替换方式。
2. `.mindx/history.json` 是项目内历史文件，由 `_save_history_entry()` 写入，也采用临时文件加 `os.replace()`。
3. 历史默认保留 3 天，`/api/history` 的 `days` 参数大于 3 时会被截断为 3。

---

## 7. Gotchas & Conventions

### 路径处理

- **文件路径优先使用正斜杠**：服务端和前端多处通过 `.replace("\\", "/")` 标准化路径。
- **外部文件使用绝对路径作为图节点 id**，例如 `C:/path/to/external.md`。
- **项目内部文件使用相对 project_root 的路径**，例如 `memory/tools/system.md`。
- **`isExcluded()` 需要同时处理绝对路径和相对路径**：它会按 `/` 切分路径，并检查每个尾段是否匹配排除项。
- **排除列表中的文件和目录不同**：文件一般保留 `.md`，目录通常带尾随 `/`，这会影响 `isExcluded()` 匹配。

### 编辑工具安全

- **不要用空字符串作为编辑锚点**。如果编辑工具允许 `oldString=""`，它可能覆盖整个文件。
- **编辑前先读取文件内容**，避免基于过期上下文写入。
- **大范围改动要先列清目标和验证点**，避免漏改文档与测试说明。

### 前端细节

- **`S` 是单一状态源**：视图都从 `S` 读取。修改 `S` 后调用 `renderAll()`。
- **localStorage 键是项目级**：`pkey(k)` 会加前缀 `mindx_${projectName}_`。
- **vis-network 容器初始化时必须有尺寸**：活跃标签页通过 `.tab-content.active` 显示。
- **组节点** 使用 `isGroup: true`，合成路径包括 `__dir_memory/tools/`、`__extroot__`、`__extdir_...`。
- **`mergeSuperGroups` 只在 `depth === 0` 运行**，防止深层误合并。
- **标签切换后要 `redraw()`**：当前代码在切换后 100ms 对对应网络调用 `redraw()`。
- **`onFilterChange` 是过滤复选框统一入口**：它读取 `e.target.id`，同步所有相关复选框。
- **vis-network 4.21 组颜色问题**：需要深色节点时不要给节点设置 `group`，否则默认浅色组颜色可能覆盖 `color.background`。
- **图点击后的树高亮**：`highlightInTree(path)` 使用 `CSS.escape(path)` 和 `scrollIntoView()`，改树选择逻辑时保留两者。
- **重扫按钮**：它调用 `/api/scan`，不是刷新页面。加载状态要保持到文件和图刷新完成。

### 服务端细节

- **线程安全**：优先使用 GraphEngine 公开方法。`GraphEngine` 当前使用 `threading.RLock()`，不是普通 `threading.Lock()`。
- **重命名执行**：最终通过 `update_file()` 重新扫描受影响文件和新文件，但现有实现会先移除旧节点和旧 `files` 条目。
- **历史文件**：`.mindx/history.json` 按项目存放，原子写入，默认保留 3 天。
- **解析器边界情况**：超过 50MB 的文件不会提取链接。`[text](url "title")` 的标题会被剥离。UNC 路径会被标记为外部。
- **watchdog 反馈循环**：服务端写文件时用 `_server_writing` 抑制 watcher 回调，不要在没有替代保护的情况下移除。
- **项目切换锁**：`_project_lock` 保护 `active_project` 切换和 watcher 停止启动流程。
- **服务端常量在 `config.py`**：`FILE_TYPES`、`SYNC_RULES`、`IGNORE_PATTERNS`。
- **外部文件轮询**：守护线程每 30 秒执行一次，常量为 `POLL_INTERVAL = 30`。
- **变更日志上限**：`_max_changes = 200`。
- **watcher 防抖**：同一路径 500ms 内重复事件会被跳过。
- **端口冲突**：服务端输出错误并退出，不会自动切换端口。

### 配置持久化

- **配置变更会立即保存**：添加项目、移除项目、保存设置、保存坐标、添加或移除外部路径都会调用 `save_config()`。
- **配置写入是原子的**：先写临时文件，再用 `os.replace()` 替换。
- **外部路径持久化前会转为绝对路径并使用正斜杠**。
- **设置在前端有 `_settingsCache` 与 localStorage 后备**。启动后的事实来源是服务端 `/api/settings/load`。

### MCP 细节

- `mcp_server.py` 使用 `stdio_server()` 作为 MCP 传输方式。
- MCP 工具通过 `_http_get()` 和 `_http_post()` 代理到 Flask 服务，默认 `SERVER_URL = "http://127.0.0.1:5020"`。
- 连接失败会返回 `{"_error": "无法连接 mindx 服务 (127.0.0.1:5020)。请先启动 python server.py"}`。
- `handle_call_tool()` 会捕获未知工具、`ValueError` 和其他异常，并返回 JSON 文本。
- 当前 13 个工具为：`list_projects`、`switch_project`、`list_files`、`search_files`、`get_file_content`、`get_file_info`、`get_references`、`get_backlinks`、`get_dependency_graph`、`get_broken_links`、`get_sync_suggestions`、`get_change_log`、`rename_file`。

---

## 8. Git Workflow

### 每次编辑会话前

```bash
git add -A && git commit -m "snapshot before changes"
```

### 每次成功编辑后

```bash
git add -A && git commit -m "description of change"
```

### 恢复丢失文件

```bash
git checkout -- path/to/file
```

### 不要做

- 不要跳过提交，提交是主要恢复机制。
- 不要 amend 已被外部引用的提交。
- 不要在任何 git 操作中使用 `--force`。
- 不要把带敏感本地路径的 `config.yaml` 提交进仓库，必要时加入 `.gitignore`。
- 除非明确要求，不要使用 `git reset --hard`。

### 提交信息风格

- 使用简短描述说明变更内容。
- 范围明确时加前缀，例如 `server:`、`frontend:`、`config:`、`parser:`。
- 示例：`server: add /api/export endpoint`、`frontend: add dark mode toggle`、`config: sync rules for L3 tools`
