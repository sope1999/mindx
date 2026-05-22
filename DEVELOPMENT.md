# mindx 开发文档

> 记录 mindx（Memory Index Tracker）从概念到 v4.6 的完整开发过程。
> 项目路径：`C:\SOFT\AI\mindx\`

---

## 一、项目起源

### 背景
旺财（OpenClaw coder agent）的记忆体系从混合扁平文件重构为三层记忆树后，需要一套工具来：
1. 实时监控记忆文件的变更
2. 可视化文件间的引用关系
3. 在修改单一文件时，告知需要同步更新哪些关联文件
4. 让人（飞鼠）直观看到记忆树的完整依赖状况

### 触发会话
2026-05-12，飞鼠要求：
> "开发一个软件，让记忆树中任何文件的更改都能反应在软件上，同时记忆树中文件索引逻辑的修改、新增、删除都能在软件上看到，单一文件的改动可以关联到其它索引的文件让 openclaw 修改单一文件时知道要同步更新哪些文件，人也能看到文件的关联状况"

---

## 二、技术选型

| 层面 | 选择 | 原因 |
|------|------|------|
| 后端框架 | Flask + Flask-SocketIO | 轻量，WebSocket 实时推送，单文件部署 |
| 文件监听 | watchdog | Python 原生，跨平台，事件驱动 |
| 依赖图 | NetworkX（后端）+ vis.js（前端） | 后端计算图结构，前端可视化渲染 |
| 前端 | 原生 HTML/CSS/JS + vis.js CDN | 零构建工具，一个 Python 进程即可 |
| 数据存储 | 无持久化数据库 | 全量内存计算，localStorage 保存用户状态 |
| 运行方式 | `Start-Process -WindowStyle Hidden` | Windows 后台静默服务 |

### 不选方案及原因
- **Electron**：太重，旺财机器已有 Python 环境
- **React/Vue**：需构建工具链，维护成本高于收益（单人使用）
- **数据库（SQLite）**：文件即数据源，无需额外存储

---

## 三、版本演进

### v1（初始版本）— 约 600 行
**日期**：2026-05-12 上午
**文件**：`server.py`, `parser.py`, `graph_engine.py`, `watcher.py`, `config.py`

**实现**：
- Flask 服务 + SocketIO WebSocket
- watchdog 监听 `C:\SOFT\AI\coder\` 下所有 .md 文件
- Markdown 链接解析器：从 `[text](path)` 提取引用关系
- NetworkX 构建依赖图
- 同步规则引擎：基于 MEMORY.md 收尾检查表格
- 简单前端：三栏布局，vis.js 力导向依赖图

**遗留问题**：
- 文件树只是目录结构平铺，不反映引用层级
- 依赖关系单一来源（仅 markdown 链接）
- 无隐式引用支持

---

### v2（UI 重构）— 约 800 行
**日期**：2026-05-12 下午
**新增**：`templates/index.html`, `static/css/style.css`, `static/js/app.js`（全部重写）

**改动**：
- **四栏布局**：文件树 | 记忆树图/依赖图/文件详情 | 文件信息/实时事件/同步建议
- **文件树**：可展开折叠 + L1/L2/L3 记忆层级标签
- **新增记忆树图**：vis.js 层次布局
- **右栏文件信息**：文件名、路径、上级/下级文件（可折叠）、「查看详细」按钮
- **跨视图联动**：文件树/记忆树图/依赖图点击同一个文件时同步高亮
- **深色主题**：完整暗色 UI

---

### v3（引用树 + 文件分类）— 约 900 行
**日期**：2026-05-12 傍晚

**改动**：
- **文件树默认引用树模式**：按「谁引用谁」排列，MEMORY.md 为根
- **文件分类**：基础文件（AGENTS/SOUL/USER/IDENTITY/HEARTBEAT）、独立文件（规则/TOOLS/urls）
- **显隐控制**：文件树/记忆树图/依赖图三处同步联动
- **过期角标**：下级文件修改时间晚于上级 → 标黄

---

### v3.1（Bug 修复 + LR 布局）— 约 950 行
**日期**：2026-05-12 深夜

**Bug 修复**：

| Bug | 根因 | 修复 |
|-----|------|------|
| 引用树点击无文件信息 | `buildRefTree` 内部做可见性过滤，过滤掉了引用链上的文件 | 改为 `filterRefTree` 统一过滤，`buildRefTree` 只做纯引用树构建 |
| checkbox 切换不刷新 | 过滤器变更后未重新渲染视图 | 新增 `_syncGuard` 防事件循环，`onFilterChange` 统一处理 |
| 记忆树图/依赖图 checkbox 点击无效 | `onFilterChange` 硬编码读取 `chk-show-base`（文件树的 checkbox），而非 event.target | 改为 `event.target` 读取实际点击的 checkbox |

**改进**：
- 记忆树图方向改为 `LR`（左→右）
- 文件详情页新增过期警告区域（`detail-stale-section`）

---

### v3.2（分组结点 + 固定布局 + 交互提示）— 约 1000 行
**日期**：2026-05-13

**功能**：
1. **引用树分组结点**：MEMORY.md 下级按「工具链」「项目」「归档」分组，可折叠展开
2. **依赖图固定布局**：首次渲染后冻结 physics，手动拖动后位置保存到 localStorage
3. **可点击提示**：过期提示、实时事件、同步建议均可点击弹出详情模态框
4. **人工确认**：确认后提示永久消失（存 localStorage）

---

### v3.3（项目结点 + 外部文件 + 分类设置）— 约 1050 行
**日期**：2026-05-13

**功能**：
- **项目名分组结点**：`_index.md` 下提取项目目录名（如 aviation），创建 `📁 aviation` 结点包含其下四文件
- **核心文件显隐开关**：文件树新增「核心」checkbox
- **分类尾标**：基础→`基`(橙)、独立→`独`(黄)、外部→`外`(灰)
- **文件详情分类设置**：核心/基础/独立/外部 四类可手动修改，存 localStorage
- **默认分类恢复**：↩ 按钮恢复原始分类
- **完整路径 + 被读取次数**：文件详情新增字段

**Bug 修复**：

| Bug | 根因 | 修复 |
|-----|------|------|
| 分类按钮点击后不高亮 | `selectFile(path)` 中 `S.selectedFile===path` 提前 return，未触发重渲染 | 改为直接 `fetchFileDetail(path).then(renderDetail)` |

---

### v3.4（删除/创建检测 + 旧边清除）— 约 1050 行
**日期**：2026-05-13

**Bug 修复**：

| Bug | 根因 | 修复 |
|-----|------|------|
| 删除文件无同步建议 | `_generate_suggestions` 只查 3 个 INDEX_FILES，忽略 L2/tool 等普通文件的反向引用 | 新增 graph in_edges 查询所有引用者；删除前收集 `broken_refs`，标记 critical 级别「链接已断开」 |
| 修改文件链接后旧边残留 | `update_file` 只 `add_edge` 不删旧边 | 新增 `remove_edges_from(out_edges)` 清除旧边再重建 |

**功能**：
- `implicit-refs.json` 加载：`_index.md` → aviation 四文件全部关联
- `api_file_detail` 新增 `abs_path` 字段

---

### v3.5（分类颜色 + 坐标轴排列 + UD 布局 + 双向箭头）— 当前版本
**日期**：2026-05-13

**功能**：
- **分类颜色**：非核心文件统一分类颜色（基础=橙 `#db6d28`、独立=黄 `#d29922`、外部=灰 `#6e7681`），核心文件保持文件类型颜色
- **依赖图坐标轴预置**：非核心文件按分类排列在核心文件上方，同类同行不重叠
  - base Y=-350, standalone Y=-230, external Y=-110
  - X 间距 150px，居中排列
- **记忆树图方向**：LR → UD（上→下），同层级左→右
  - 非核心文件 `level:0`（顶层），核心文件 `level:1`（下方）
- **双向箭头**：父↔子互引用时显示 `↔` 双箭头
- **解除 fixed 约束**：所有图自动生成时预置坐标，之后可自由拖动，拖动后点 💾 保存

**Bug 修复**：

| Bug | 根因 | 修复 |
|-----|------|------|
| 记忆树图和依赖图空白 | `renderMemoryTree` 函数体替换时旧代码残留，产生重复闭合括号 `Unexpected token '}'` | 删除残留的重复代码块 |
| 非核心文件未排列在上方 | `arrangeNonCoreDep` 在 stabilized 之后设置位置，节点 fixed 阻止拖动 | 改为 DataSet 创建前预置 x/y 坐标，去掉 `fixed` 约束 |
| `addProjectNodes` 不生效 | `parts[pi+2]` 取到文件名而非项目名 | 改为 `parts[pi+1]` |

---

## 四、架构图

```
C:\SOFT\AI\mindx\
│
├── server.py              ← Flask + SocketIO + watchdog 集成入口
├── config.py              ← 路径配置、文件类型映射、同步规则
├── parser.py              ← Markdown [→](path) 链接解析
├── graph_engine.py        ← NetworkX 依赖图 + 同步规则引擎
├── watcher.py             ← watchdog 文件系统监听
│
├── templates/
│   └── index.html         ← 单页仪表盘
│
├── static/
│   ├── css/style.css      ← 深色主题样式
│   └── js/app.js          ← 全部前端逻辑（~320 行）
│
├── start.ps1 / stop.ps1   ← Windows 启停脚本
├── requirements.txt       ← Python 依赖
├── DEVELOPMENT.md         ← 本文件
├── OPENCLAW_GUIDE.md      ← OpenClaw 使用指南
└── mindx-view-spec-v3.md  ← 视图定义文档（引用矩阵 + 画法）
```

### 数据流

```
文件系统变更 → watchdog → on_file_change()
    → engine.update_file() → 更新 NetworkX 图
    → SocketIO emit('file_changed') → 前端刷新
    → SocketIO emit('sync_needed')  → 前端同步建议
```

### API

| 路由 | 返回 |
|------|------|
| `GET /` | 仪表盘 HTML |
| `GET /api/status` | 运行状态 + 统计 |
| `GET /api/files` | 所有文件列表 |
| `GET /api/file/<path>` | 文件详情 + 依赖关系 + 完整路径 |
| `GET /api/graph` | 完整图数据（节点 + 边） |
| `GET /api/changes` | 变更日志 |
| `GET /api/sync-check` | 全量同步检查 |

---

## 五、关键设计决策

### 5.1 三种视图的职责分离
| 视图 | 职责 | 数据来源 |
|------|------|---------|
| 文件树 | 按引用层级导航 | parser 解析的边 + 隐式引用 |
| 记忆树图 | 引用层级可视化（UD 上→下） | parser 边 + 分类着色 |
| 依赖图 | 全部引用关系力导向图 | parser 边 + 隐式引用 + 坐标预置 |

### 5.2 隐式引用处理
Markdown 链接 `[→](path)` 被 parser 自动解析。纯文本引用通过 `implicit-refs.json` 补充。

已实现：`C:\SOFT\AI\coder\memory\implicit-refs.json`，graph_engine 在 `scan_all()` 时加载。

### 5.3 边类型体系
| 类型 | 含义 | 双向箭头条件 |
|------|------|-------------|
| INDEX_TO_CHILD | 索引表→被索引文件 | A↔B 同时存在时 |
| L2_TO_L3 | L2摘要→L3完整版 | — |
| PROJECT_REF | 项目索引→项目文件 | — |
| SIBLING | 兄弟文件 | — |
| TOOL_TO_PROJECT | 工具→项目调度 | — |

### 5.4 前端状态管理
- 全局 `S` 对象管理所有状态
- localStorage 持久化：依赖图位置、记忆树图位置、确认项、分类覆写、读取计数
- SocketIO 驱动实时更新
- 无前端框架，纯 DOM 操作

---

## 六、Bug 总表

| # | 发现版本 | Bug | 根因 | 修复 |
|---|---------|-----|------|------|
| 1 | v3.1 | 引用树点击无文件信息 | `buildRefTree` 内部做可见性过滤 | `filterRefTree` 统一过滤 |
| 2 | v3.1 | checkbox 切换不刷新 | 事件处理链路断裂 | `_syncGuard` + `onFilterChange` |
| 3 | v3.1 | 记忆树图/依赖图 checkbox 无效 | `onFilterChange` 硬编码读取错误元素 | 读 `event.target` |
| 4 | v3.3 | 分类按钮不高亮 | `selectFile` 提前 return | 直接调 `fetchFileDetail` |
| 5 | v3.4 | 删除文件无同步建议 | `_generate_suggestions` 只查索引文件 | graph in_edges + broken_refs |
| 6 | v3.4 | 修改链接后旧边残留 | `update_file` 只 add 不 remove | `remove_edges_from(out_edges)` |
| 7 | v3.3 | `addProjectNodes` 不生效 | `parts[pi+2]` 取到文件名 | 改为 `parts[pi+1]` |
| 8 | v3.5 | 记忆树图/依赖图空白 | 函数体替换时旧代码残留（重复 `}`） | 删除残留代码块 |
| 9 | v3.5 | 非核心文件未在上方 | stabilized 后设位置 + fixed 阻止拖动 | DataSet 创建前预置 x/y |

---

## 七、相关文档

| 文档 | 路径 | 用途 |
|------|------|------|
| 视图定义 | `C:\SOFT\AI\mindx\mindx-view-spec-v3.md` | 三个视图画法 + 引用矩阵 |
| 使用指南 | `C:\SOFT\AI\mindx\OPENCLAW_GUIDE.md` | OpenClaw 如何使用 mindx + 文件写法规范 |
| 记忆框架 | `C:\SOFT\AI\PageIndex\memory-framework.md` | 旺财记忆体系设计 |
| 记忆树快照 | `C:\SOFT\AI\PageIndex\openclaw-memory-tree-v2.md` | 实施后的文件结构快照 |

---

---

## 八、v4.0 — 多项目 + 通用化重构

**日期**：2026-05-15

### 核心改动

| 模块 | 改动 |
|------|------|
| **config.py** | 从硬编码 → `config.yaml` 多项目配置，含 `load_config`/`save_config`/`add_project`/`remove_project` |
| **server.py** | 新增 4 个项目管理 API，端口冲突提示，多引擎/多 watcher 管理 |
| **graph_engine.py** | 接受 `project_root` 参数，通用化递归扫描，外部链接支持，移除 coder 特定逻辑 |
| **watcher.py** | 接受 `project_root` 参数，新增 `restart()` 方法支持项目切换 |
| **parser.py** | 新增 `is_external`/`target_is_external` 字段，通用化路径解析 |
| **前端** | 多项目标签栏 + 下拉列表、文件树目录模式增强、记忆树图目录模式、外部链接虚线标注、空文件夹节点 |

### 新增需求（来自 `新需求.md` v1.0）

| 需求 | 状态 |
|------|------|
| 多项目管理（添加/删除/切换） | ✅ |
| config.yaml 配置 | ✅ |
| 端口冲突弹窗提示 | ✅ |
| 文件树目录模式 | ✅ |
| 记忆树图目录模式（UD 树形布局） | ✅ |
| 依赖图外部链接标注 | ✅ |
| 空文件夹节点 | ✅ |
| 项目路径失效处理 | ✅ |
| 项目名规则（文件夹名 + 重名后缀） | ✅ |
| 静默升级检查 | ❌ 暂缓 |
| PyInstaller 打包 | ❌ 暂缓 |

### 架构变化

```
旧：config.py (硬编码) → single engine → single watcher
新：config.yaml (配置驱动) → engines{} 字典 → watchers{} 字典 → per-project 管理
```

> 最后更新：2026-05-22 | 当前版本：v4.5

---

## 九、v4.1 — 引用规则统一 + 文件树重构

**日期**：2026-05-16

### 隐式引用废弃

| 动作 | 详情 |
|------|------|
| 删除 | `memory/implicit-refs.json` |
| 移除 | `graph_engine._load_implicit_refs()` + `import json` |
| 转为显式 | 所有隐式引用改为 `[→](path)` Markdown 链接 |

引用规则统一为一条：**标准 Markdown 链接 `[text](path)`**。

### 引用链整理

```
_index.md ──→ overview.md ──→ PROJECT_PROGRESS.md
                           ──→ dev-sessions.md
                           ──→ dev-sessions-old.md
```

项目文档由 `overview.md` 集中管理，不散落在工具文件中。

### 文件树分组算法重写

| 版本 | 算法 | 问题 |
|------|------|------|
| v4.0 | 硬编码 `GROUP_SPEC`（tools/→工具链 等） | coder 专属 |
| v4.1 | 通用 `addDirGroups` + `mergeSuperGroups` | 任意项目适用 |

核心规则：
1. 子节点按 `parentDir` 分组合并 → `📁 目录名/`
2. 分组节点不递归自己的子节点（防同名嵌套）
3. `mergeSuperGroups` 根层级合并同前缀分组（`tools/` `projects/` → `📁 memory/`）
4. 子文件同目录不分组（防 `📁 aviation/` 内再嵌套 `📁 aviation/`）

### 文件树模式重定义

| 模式 | v4.0 | v4.1 |
|------|------|------|
| **目录** | 纯文件系统目录树 | 引用层级 + 📁 分组（默认） |
| **引用** | 引用层级 + 分组 | 纯引用层级，无分组 |

### 新增功能

| 功能 | 说明 |
|------|------|
| 右键菜单 | 隐藏/取消隐藏、移除/恢复文件 |
| 批量隐藏 | 多选模式 ☑ → 一键隐藏 |
| 项目设置 | ⚙ 模态弹窗：全量/引用模式、根文件管理、排除目录 |
| 外部追踪 | 30s 后台轮询外部文件 mtime |
| 脚本修复 | `start-mindx.ps1` / `stop-mindx.ps1` 端口检测 + 缓存清理 |

---

## 十、v4.2 — 外部文件管理 + 视图拆分 + 排除完善

**日期**：2026-05-16

### 外部文件挂载

| 功能 | 说明 |
|------|------|
| 挂载入口 | ⚙ 项目设置 → 外部文件/文件夹，支持手动输入 + 系统文件管理器选择 |
| 持久化 | 挂载路径存入 `config.yaml` 的 `external_paths`，重启不丢失 |
| 扫描过滤 | `scan_all()` 跳过 `IGNORE_PATTERNS` 匹配的文件（`temp/*` 等） |
| 显示规则 | 无引用关系的挂载文件统一收入 `📁 外部/`，按系统目录层级嵌套 |
| 排除优先 | 排除列表对挂载文件同样生效，排除后不出现在外部区域 |

### 记忆树图拆分

原「🌳 记忆树图」拆为两个独立 Tab：

| Tab | 内容 |
|------|------|
| 🌿 引用树图 | 引用关系层级，UD 层次 → 冻结后自由拖动 |
| 📁 目录树图 | 文件夹层级，UD 固定树形，不可拖动 |

各自独立容器、布局持久化。

### 多选增强

| 功能 | 说明 |
|------|------|
| 框选 | ☑ 多选模式 → 按住左键拖拽蓝色矩形框选文件 |
| 批量右键 | 多选后右键 → 批量隐藏/取消隐藏/移除/恢复 |
| 坐标修复 | 框选改用 `clientX/Y` 视口坐标，滚动不影响选区 |

### 排除逻辑修复

| 修复 | 说明 |
|------|------|
| 文件排除 | `addExcludeDir` 区分文件（不加 `/`）和目录（加 `/`） |
| 跨路径匹配 | `isExcluded` 从路径尾部逐段匹配，绝对路径也能命中 |
| 空组隐藏 | `filterRefNode` 分组节点无可见子节点时不渲染 |
| 扫描过滤 | `scan_all()` 引入 `_should_ignore`，源头跳过被忽略目录 |

### 文件树目录模式改进

`addDirGroups` 重写：按 `parentDir` 分组 + 同目录不重复分组 + `mergeSuperGroups` 根级合并同前缀分组。

### 基础体验提升（v4.2）

| 功能 | 说明 |
|------|------|
| 主题切换 | 🌙/☀️ 暗色/亮色，`data-theme` 切换 CSS 变量，偏好存 localStorage |
| 快捷键 | `Ctrl+F` 聚焦搜索、`Esc` 关闭弹窗/菜单 |
| 目录树图重绘 | 手工坐标算法替代 vis.js 层级布局：父节点居中、子目录比例分宽、文件横排 |
| 文件监听修复 | `watching: False` → 清理 `__pycache__` + 强制重启恢复 |

---

## 十一、v4.3 — 配置持久化 + 稳定性修复

**日期**：2026-05-17

### 设置持久化迁移

分类覆写、排除目录、显示模式、根文件设置从 localStorage 迁到 `config.yaml`：

| 数据 | 旧存储 | 新存储 |
|------|--------|--------|
| `file_classes` | localStorage | `config.yaml` 每项目 |
| `excluded_dirs` | localStorage | `config.yaml` 每项目 |
| `display_mode` / `ref_roots` / `active_root` | localStorage | `config.yaml` 每项目 |
| 布局坐标 | localStorage | `config.yaml`（服务器 + local缓存） |

新增 API：`/api/settings/load`、`/api/settings/save`、`/api/positions/save`、`/api/positions/load`

### Git 版本控制

```bash
git init && git add -A && git commit
```

所有代码纳入 git，`.gitignore` 排除 `__pycache__`。`opencode.md` 顶部写入 AI 开发规则（走 agent 委派、每次 commit）。

### Bug 修复

| Bug | 修复 |
|-----|------|
| 核心/外部/隐藏复选框无效 | `onFilterChange` 事件分支补齐全部五种过滤器 |
| 分类按钮不高亮 | `renderDetail` 补充分类高亮 + `detail-classify` 事件监听 |
| 各 Tab 过滤器不同步 | 双向联动：任一 Tab 操作同步全部 |
| 启动不显示项目标签 | `initAll` 增加 `loadProjects()` 调用 |
| 外部文件路径反斜杠 | 挂载时路径统一 `replace("\\", "/")` |
| 重命名→引用断裂 | rename-execute 精确替换 raw_target + 删除旧节点重排边 |

### UI 改进

| 改进 | 说明 |
|------|------|
| 删除项目入口 | 从标签栏 × 移至 ⚙ 设置弹窗底部「危险操作」 |
| 用语统一 | 所有"删除"→"移除"，前端文案一致 |

### 新功能

| 功能 | 说明 |
|------|------|
| 文件重命名 | 右键→✏重命名→预览变更→确认→自动更新所有引用+读写磁盘 |

（v4.3 完）

---

## 十二、v4.4 — 引用树图 DAG 布局 + 分类自动化

**日期**：2026-05-19

### 引用树图 DAG 层级自动布局

引用树图由 vis.js 力导向改为纯 DAG 层级布局：

| 算法 | 说明 |
|------|------|
| Kahn 拓扑排序 | 对引用图执行拓扑排序，计算每个节点的 `refLevel`（层级深度） |
| 手动坐标 | 根据层级分配 Y 坐标，同层级按索引分配 X 坐标，禁用 vis.js physics |
| 坐标持久化 | 手动拖动后点击 💾 保存坐标，下次渲染时优先使用已保存坐标 |

核心函数：`computeRefLevels(graphData)` — 接收图数据，返回 `{levels: {nodeId: level}, maxLevel: number}`。

### 分类逻辑改为引用树结构驱动

| 旧逻辑 | 新逻辑 |
|--------|--------|
| 手动/硬编码分类（核心/基础/独立） | 由引用图的边关系自动判定 |
| 独立 = 无引用关系 | 独立 = 无入边且无出边 |
| 基础 = 有入边无出边 | 基础 = 有入边（被引用）但无出边 |
| 核心 = 有出边 | 核心 = 有出边（引用其他文件） |

分类由 `computeRefLevels` 的拓扑排序结果自动推导，不再需要手动维护分类规则。

### 开发时刷新按钮替代保存坐标

引用树图增加刷新按钮（🔄），开发模式下替代 💾 保存坐标按钮：
- 点击 🔄 重新运行 `computeRefLevels` 并重新布局
- 手动拖动后仍可 💾 保存自定义坐标

### 筛选状态 localStorage 持久化

| 状态 | 旧行为 | 新行为 |
|------|--------|--------|
| 过滤器复选框（核心/基础/独立/外部/隐藏） | 页面刷新后重置为默认 | 刷新后恢复上次选择，存 localStorage |
| 搜索框文本 | 刷新后清空 | 刷新后恢复 |

使用 `lsSet('filters', {...})` / `lsGet('filters')` 按项目命名空间持久化。

### Bug 修复

| Bug | 根因 | 修复 |
|-----|------|------|
| 自环边导致 Kahn 死锁 | 节点引用自身形成自环，Kahn 算法永远无法将其入度归零 | 预处理阶段过滤自环边（`from === to`） |
| 自环箭头误显为双向 | overview.md→overview.md 等自引用渲染为角落箭头 | 过滤 from===to 的边 |
| 双向引用显示两条并行线 | A→B 和 B→A 各渲染一条 | 合并为单条双向箭头 (arrows:'to,from') + seenBi 去重 |
| 双向箭头不渲染 | 缺少全局 edges.arrows 配置 | opts 加入 edges:{arrows:{to:{enabled:true},from:{enabled:true}}} |
| 绝对路径边在 computeRefLevels 中被过滤 | 外部文件使用绝对路径作为节点 ID，与项目相对路径不匹配 | 统一使用节点 ID 查找，不假设路径格式 |
| savedPos 后覆盖手动坐标 | `renderMemoryRefTree` 先应用手动坐标，后被 savedPos 覆盖 | 优先级调整：savedPos > 手动拖动 > 自动布局 |
| 孤立检测覆盖已处理的 Kahn 节点 | 孤立节点（无入边无出边）在 Kahn 处理后又被孤立检测重复处理 | 孤立检测跳过已在 Kahn 结果中的节点 |
| 10 | v4.4 | 主题切换后图保持浅色 | 主题按钮只改了 `data-theme` 未调用 `renderAll()`，节点颜色不变 | 主题切换末尾追加 `renderAll()` |
| 11 | v4.4 | 主题切换后图仍浅色 | vis-network 4.21 的 group 默认样式自动覆盖 per-node `color.background` | 移除节点 `group` 字段，bump 到 `app.js?v=4.5.0` |

- 图中点击节点 → 文件树高亮对应项并滚动到位（`highlightInTree`）

（v4.4 完）

## 十三、v4.5 — MCP 服务器

> **关键决策**：MCP 服务器采用纯 HTTP 代理模式，通过 `requests` 调用 `server.py` 的 HTTP API，不重复实现图引擎逻辑。项目选择走运行时 `switch_project` 工具而非 `--project` 参数。

### 背景

mindx 作为开发者日常使用的知识图谱工具，积累了大量文件引用关系数据。AI 编程助手（Cursor、Claude Desktop）需要通过 MCP 协议获取这些上下文来理解项目结构。

### 技术方案

```
AI 工具 ←─stdio─→ mcp_server.py ←─HTTP─→ server.py:5020
                      ↓
                config.yaml（启动时读取）
```

- **新增文件**：`mcp_server.py`（423 行）
- **新增依赖**：`requirements-mcp.txt`（mcp>=1.0.0, requests>=2.28.0）
- **server.py 补充**：
  - `GET /api/file/<path>/backlinks` — 文件入链查询
  - `GET /api/broken-links` — 全项目断链汇总

### 13 个 MCP 工具

| 分类 | 工具 | 实现 |
|------|------|------|
| 项目管理 | `list_projects`, `switch_project` | 读 config.yaml，设进程级变量 |
| 文件浏览 | `list_files`, `search_files`, `get_file_content`, `get_file_info` | HTTP 调 Flask + 磁盘 I/O |
| 引用关系 | `get_references`, `get_backlinks`, `get_dependency_graph` | HTTP 调 Flask |
| 诊断维护 | `get_broken_links`, `get_sync_suggestions`, `get_change_log` | HTTP 调 Flask |
| 文件操作 | `rename_file` | 两步 HTTP（preview → execute），原子更新引用 |

### 状态管理

- 无 `--project` 参数，MCP 实例可服务所有项目
- `current_project = None` 初始状态，`switch_project` 切换
- `list_projects` 始终可用；其他工具缺少项目时返回可执行错误提示
- 错误处理分层：项目未选 / Flask 不通 / 文件不存在

### 坑

- **路由顺序**：`/api/file/<path>/backlinks` 必须定义在 `/api/file/<path>` 之前，否则 Flask 的 `<path:file_path>` 会将 `MEMORY.md/backlinks` 当成完整路径吞掉（commit `e3ff74b`）
- **端点命名不一致**：`get_sync_suggestions` 调用 `/api/sync-check`（非 `/api/sync-suggestions`）

### Bug 表

（v4.5 无新 Bug）

### 配置示例

```json
{
  "mcpServers": {
    "mindx": {
      "command": "python",
      "args": ["C:/SOFT/AI/mindx/mcp_server.py"]
    }
  }
}
```

### 事件历史面板

- 持久化事件记录到项目根目录 `.mindx/history.json`（JSON 增量追加）
- `GraphEngine._load_history()` 启动时加载并自动清理 >3 天记录
- `update_file()` 在每次变更事件和同步建议时写入 history
- `GET /api/history?days=3&type=all|changes|sync` 查询 API
- 前端新增第 5 个标签页 📋 历史：时间线视图，支持按类型筛选，点击文件名跳转到详情

（v4.5 完）
