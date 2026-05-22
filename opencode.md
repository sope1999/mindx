# mindx 开发文档（v4.5）

> ⚠️ **AI 开发规则（不可跳过）：**
>
> **流程纪律：**
> 1. 改代码必须走 task agent：小改动 `task(category="quick")`，复杂重构 `task(category="deep")`
> 2. 每次改动后立即 `git add -A && git commit -m "描述"`，commit before next action
> 3. 不直接 edit/write，不跳过验证，不跳过 git
>
> **改前影响面检查：**
> 4. 涉及函数/变量/class 改动前，先跑 `lsp_find_references` 确认所有引用点，确保改动覆盖全部影响范围
> 5. 改某个模式前先 `explore` 搜全项目确认所有出现位置，统一修改，禁止假设只有一处
>
> **改后自检：**
> 6. 每次改完立即跑 `lsp_diagnostics` 确认无类型/依赖/导入错误
> 7. 改完用 `lsp_find_references` 复核所有引用点均已覆盖，无遗漏
>
> **UI 交互完整性：**
> 8. 改了 UI 逻辑（事件 handler、状态）后，逐一确认所有依赖该状态的渲染路径是否需要刷新——如改主题变量必须调重绘函数、改数据源必须通知所有消费方
> 9. 改了共享函数/组件后，确认所有调用方行为不受破坏（如三个图共用同一渲染逻辑）
>
> **服务管理：**
> 10. 禁止用 `bash` 启动/重启 `python server.py`（长驻进程超时被 kill，输出干扰 opencode）。改用 `Start-Process -WindowStyle Hidden` 后台启动

## 项目概述

mindx 是一个通用 .md 文件关系可视化工具，支持多项目管理。通过文件树（目录/引用模式）、记忆树图（目录/引用模式）、依赖图四个维度展示项目结构及文件间引用关系。

## 技术栈

- **后端**：Python Flask + Flask-SocketIO + watchdog + NetworkX + PyYAML
- **前端**：原生 HTML/CSS/JS + vis.js 图形库
- **配置**：`config.yaml`（多项目 + 全局首选项）
- **启动**：`python server.py`，默认 `http://127.0.0.1:5020`
- **依赖**：见 `requirements.txt`

## 项目目录

```
C:\SOFT\AI\mindx\
├── server.py            # Flask 主服务 + SocketIO + 多项目 API
├── parser.py            # [→](path) 链接解析 + 外部链接检测
├── graph_engine.py      # NetworkX 依赖图 + 隐式引用 + 通用扫描
├── watcher.py           # watchdog 文件监听 + 项目切换
├── config.py            # config.yaml 管理 + 全局常量
├── config.yaml          # 多项目配置（用户态）
├── requirements.txt     # Python 依赖（含 pyyaml）
├── templates/
│   └── index.html       # 前端入口（含项目标签栏）
├── static/
│   ├── css/style.css    # 暗色主题样式（含项目标签/模态框/外部链接样式）
│   └── js/app.js        # 前端主逻辑（多项目/目录模式/外部链接）
├── start-mindx.ps1      # Windows 启动脚本
├── stop-mindx.ps1       # Windows 停止脚本
├── 新需求.md             # v4.0 新需求文档
├── mindx-view-spec-v3.md
├── OPENCLAW_GUIDE.md
└── DEVELOPMENT.md       # v1→v4.0 完整开发历史 + Bug 表
```

## 核心模块说明（v4.0）

### server.py（~430 行）
- 项目管理 API：`/api/projects`（列表）、`/api/projects/add`、`/api/projects/remove`、`/api/projects/select`
- 数据 API：`/api/status`、`/api/files`、`/api/file/<path>`、`/api/graph`、`/api/scan`、`/api/changes`、`/api/sync-check`
- SocketIO 事件：`file_changed`、`sync_needed`、`project_switched`
- 多引擎 + 多 watcher 字典管理，按项目名索引

### config.py（~225 行）
- `config.yaml` 读写：`load_config()`、`save_config()`
- 项目管理：`add_project()`（含重名后缀处理）、`remove_project()`、`get_project_config()`
- 全局常量：`FILE_TYPES`、`IGNORE_PATTERNS`、`SYNC_RULES`

### parser.py（~210 行）
- `parse_file(abs_path, project_root)` → FileInfo
- `resolve_link_target()` 返回 `(path, is_external)` 元组
- 外部链接自动标记 `is_external=True`、`link_type="external_link"`

### graph_engine.py（~420 行）
- `GraphEngine(project_root)` — 接受任意项目根目录
- `scan_all()` — 递归扫描所有 .md 文件，通用化（不依赖特定目录结构）
- `get_graph_data()` — 返回 vis.js 格式数据，含 `is_external` 标记
- `update_file()` / `_generate_suggestions()` — 增量更新 + 同步建议

### watcher.py（~160 行）
- `FileWatcher(project_root, on_change)` — 监听任意项目目录
- `restart(new_root, new_callback)` — 切换监听目标

### 前端（~1040 行 JS + ~290 行 HTML + ~950 行 CSS）
- **多项目**：标签栏（最多 4 个）+ 下拉列表 + 添加/删除/切换 + 路径失效处理
- **文件树**：目录模式（引用层级 + 📁 自动分组合并）+ 引用模式（纯引用层级）
- **记忆树图**：目录模式（UD 层级树形图）+ 引用树模式（vis.js 力导向）
- **依赖图**：力导向图 + 外部链接虚线标注
- **右键菜单**：隐藏/取消隐藏、移除/恢复
- **批量操作**：多选模式 ☑ → 一键隐藏
- **项目设置**：⚙ 模态弹窗（全量/引用模式、根文件、排除目录）
- **联动**：三视图同步选中 + 过滤联动
- **持久化**：localStorage 按项目命名空间

## 版本历史

### v4.4（2026-05-19）
- 引用树图改为纯 DAG 层级布局（Kahn 拓扑排序 + 手动坐标），分类由引用关系自动判定（独立/基础/核心由边的关系推导）
- 筛选状态跨会话持久化（localStorage 按项目命名空间）
- 开发时刷新按钮替代保存坐标
- 修复：自环边 Kahn 死锁、绝对路径边被过滤、savedPos 覆盖手动坐标、孤立检测覆盖 Kahn 节点、自环边过滤（from===to 不渲染）、双向引用合并为单条双向箭头（seenBi 去重）、全局箭头配置（edges.arrows.to+from enabled）
- 修复：主题切换按钮只更新 `data-theme` 和 localStorage，未调用 `renderAll()`，导致三张 vis-network 图沿用旧主题节点颜色；在主题切换末尾追加 `renderAll()` 重建图。
- 修复：vis-network 4.21 会给未知 group 自动套浅色默认样式并覆盖 per-node `color.background`；移除三张图节点数据中的 `group` 字段，并 bump 到 `app.js?v=4.5.0`。
- 新增：图中点击文件节点后文件树自动高亮对应项（`highlightInTree` + `.selected` class + scrollIntoView）

### v4.5（2026-05-22）— MCP 服务器
- 新增 MCP 服务器 `mcp_server.py`：通过 stdio 协议为 AI 编程助手（Cursor/Claude Desktop）暴露 mindx 知识图谱查询能力
- 13 个 MCP 工具：项目管理（list_projects/switch_project）、文件浏览（list_files/search_files/get_file_content/get_file_info）、引用关系（get_references/get_backlinks/get_dependency_graph）、诊断维护（get_broken_links/get_sync_suggestions/get_change_log）、文件操作（rename_file — 原子重命名+自动更新引用）
- `server.py` 补充 2 个 API 路由：`/api/file/<path>/backlinks`（入链查询）和 `/api/broken-links`（全项目断链汇总）
- MCP 服务器纯 HTTP 代理模式，不重复 mindx 内部逻辑，通过 config.yaml 共享项目配置
- 依赖：`mcp`（Python MCP SDK）、`requests`（`requirements-mcp.txt`）

### v4.3（2026-05-17）
- 设置持久化迁移至 config.yaml（分类覆写、排除目录、显示模式）
- 布局坐标服务器备份（/api/positions）
- Git 初始化 + AI 开发规则
- 滤镜复选框双向同步修复
- 术语统一（删除→移除）
- 删除项目入口移至设置弹窗
- 文件重命名（预览+确认，自动更新引用）

### v4.2（2026-05-16）
- 外部文件挂载 + 持久化 + 目录层级显示
- 记忆树图拆分为引用树图 / 目录树图两个独立 Tab
- 多选框选 + 批量右键操作
- 排除逻辑修复（文件/目录区分、跨路径匹配）
- 主题切换（暗色/亮色）+ 键盘快捷键（Ctrl+F / Esc）
- 目录树图手工坐标布局

### v4.1（2026-05-16）
- 隐式引用全部转为显式 `[→](path)`
- 文件树分组算法通用化（`addDirGroups` + `mergeSuperGroups`）
- 右键菜单（隐藏/移除）+ 批量多选
- 项目设置弹窗（模式切换、根文件、排除目录）
- 外部文件后台轮询追踪
- 启停脚本修复

### v4.0（2026-05-15）
- 多项目管理（config.yaml 驱动，标签栏切换）
- 文件树 + 记忆树图 新增目录模式
- 外部链接检测与虚线标注
- 端口冲突提示

（v1→v3.5 详见 `DEVELOPMENT.md`）

## 隐式引用

项目根目录下的 `implicit-refs.json`（由 `graph_engine._load_implicit_refs()` 加载）：

```json
{
  "edges": [
    {"from": "memory/_index.md", "to": "memory/aviation/A380.md", "type": "PROJECT_REF"},
    ...
  ]
}
```

## 开发环境

- 配置：`config.yaml`（项目列表 + 全局首选项）
- 前端分类规则：核心/基础/独立/外部（app.js 中默认分类 + 用户自定义覆盖）
- 无需硬编码路径，支持任意项目文件夹

## 新增需求（v4.0）

详见 `新需求.md`，已实现的功能：
- 文件树目录模式（纯文件夹层级）
- 记忆树图目录模式（UD 层级树形布局）
- 多项目管理（标签栏切换）
- 外部链接检测与标注
- 空文件夹节点显示

暂缓：PyInstaller 打包、GitHub Release、静默升级检查

## 如何运行

```bash
cd C:\SOFT\AI\mindx
pip install flask flask-socketio watchdog networkx pyyaml
python server.py
# 访问 http://127.0.0.1:5020
# 首次启动会自动创建 config.yaml
# 通过界面 "＋ 添加项目" 添加要追踪的文件夹
```

> 最后更新：2026-05-22 | 当前版本：v4.5
