# mindx

**.md 文件关系可视化工具** — 追踪 Markdown 文件之间的引用关系，通过多视图实时展示项目结构和依赖网络。

## 功能

| 功能 | 说明 |
|------|------|
| **多项目管理** | 标签栏切换，配置持久化到 `config.yaml` |
| **文件监听** | watchdog 实时追踪 `.md` 增删改，WebSocket 推送 |
| **引用解析** | 自动提取 `[→](path)` 链接，构建有向依赖图 |
| **双显示模式** | 全量显示 / 按引用显示（指定根文件，沿出边 BFS 扩展） |
| **四视图** | 文件树、引用树图、目录树图、依赖图 |
| **外部文件挂载** | 手动挂载外部文件/文件夹，按目录层级显示，重启不丢失 |
| **框选+批量** | ☑ 多选模式 → 拖拽框选 → 右键批量隐藏/移除/恢复 |

## 视图说明

```
┌────────────┬──────────────────────────┬────────────┐
│  文件树     │  记忆树图 / 依赖图        │  文件摘要   │
│  (左栏)     │  (中栏，Tab 切换)         │  (右栏)     │
│            │                          │            │
│  📁 目录    │  🌳 引用层级 / 目录层级    │  路径/分类  │
│  🔗 引用    │  🔗 力导向依赖图         │  上级/下级  │
│  过滤/隐藏  │  外部链接虚线标注         │  事件/建议  │
└────────────┴──────────────────────────┴────────────┘
```

## 安装

```bash
git clone https://github.com/yourname/mindx.git
cd mindx
pip install -r requirements.txt
```

Python 依赖：

```
flask>=3.0
flask-socketio>=5.3
watchdog>=5.0
networkx>=3.2
pyyaml>=6.0
```

## 启动

```bash
python server.py
# 访问 http://127.0.0.1:5020
```

首次启动自动创建 `config.yaml`。通过界面「＋ 添加项目」选择要追踪的 Markdown 项目文件夹。

### Windows 后台启动

```powershell
.\start-mindx.ps1   # 静默后台启动
.\stop-mindx.ps1    # 停止服务
```

## 配置

`config.yaml`（自动生成）：

```yaml
version: "1.0.0"
port: 5020
projects:
  - name: my-docs
    root: C:/path/to/my-docs
```

## 项目结构

```
mindx/
├── server.py            # Flask 主服务 + SocketIO + 多项目 API
├── parser.py            # Markdown [→](path) 链接解析 + 外部检测
├── graph_engine.py      # NetworkX 依赖图 + 隐式引用 + 外部轮询
├── watcher.py           # watchdog 文件监听 + 项目切换
├── config.py            # config.yaml 管理 + 全局常量
├── config.yaml          # 用户项目配置
├── requirements.txt     # Python 依赖
├── templates/
│   └── index.html       # 前端入口
├── static/
│   ├── css/style.css    # 暗色主题
│   └── js/app.js        # 前端逻辑
├── README.md
├── DEVELOPMENT.md       # 开发历史 + 版本记录
├── start-mindx.ps1      # Windows 启动脚本
└── stop-mindx.ps1       # Windows 停止脚本
```

## API

| 端点 | 说明 |
|------|------|
| `GET /api/projects` | 项目列表 |
| `POST /api/projects/add` | 添加项目 `{root}` |
| `POST /api/projects/remove` | 删除项目 `{name}` |
| `POST /api/projects/select` | 激活项目 `{name}` |
| `GET /api/status` | 服务状态 |
| `GET /api/files` | 当前项目文件列表 |
| `GET /api/file/<path>` | 文件详情（含链接、依赖） |
| `GET /api/graph` | 完整图数据（nodes + edges） |
| `GET /api/scan` | 强制全量扫描 |
| `GET /api/sync-check` | 同步检查报告 |

### WebSocket 事件

| 事件 | 触发 |
|------|------|
| `file_changed` | 文件增删改 |
| `sync_needed` | 检测到关联文件需同步 |
| `project_switched` | 切换项目 |
| `external_changed` | 外部引用文件 mtime 变更 |

## 引用规则

**唯一规则：用标准 Markdown 链接 `[text](path)`。** 不用 implicit-refs.json，不用纯文本箭头。

```markdown
# ✅ mindx 能解析
[→](memory/tools/claude-code.md)
[aviation](aviation/overview.md)

# ❌ 解析不到
本项目调度 → dev-sessions.md
```

### 必须：索引表用统一格式

```markdown
| 条目 | 摘要 | 路径 |
|------|------|------|
| Claude Code | AI 编程助手 | [→](memory/tools/claude-code.md) |
| OpenCode | 会话引擎 | [→](memory/tools/opencode.md) |
```

mindx 从 `[→](path)` 提取链接，建立 INDEX_TO_CHILD 关系。

### 禁止：自引用

```markdown
# ❌ 文件引用自己，产生无意义边
[→](项目开发工作规则.md)
```

### 必须：增删文件时更新索引

| 操作 | 必须更新 |
|------|---------|
| 新增工具文件 | 根索引表加一行 `[→](新文件)` |
| 删除工具文件 | 根索引表删对应行 |
| 新增项目 | 索引表加行 + `_index.md` 加行 |
| 新增根目录 .md | 判断分类，必要时更新索引 |

### 引用模式（按引用显示）

引用项目目录外的文件会被自动标记为外部链接，依赖图中以虚线显示，30 秒轮询 mtime。

```markdown
# 被 mindx 标记为 external_link
[→](../other-project/MEMORY.md)
```

### 引用模式（按引用显示）

在设置弹窗中切换到「按引用显示」模式后，mindx 从指定的根文件（如 `MEMORY.md`）出发，沿 `[→](path)` 出边 BFS 扩展，**不在引用链上的文件自动隐藏**。

```
MEMORY.md ─→ tools/claude-code.md ─→ tools/full/claude-code.md
          ─→ tools/opencode.md
          ─→ projects/_index.md ─→ aviation/overview.md

diary/2026-05-01.md   ← 无入边也无出边，引用模式下不显示
```

## License

MIT
