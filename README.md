# mindx — .md 文件关系可视化工具

mindx v4.6 用来追踪 Markdown 文件之间的引用关系，提供 Web 可视化界面、实时文件监听、外部文件挂载、断链诊断、文件重命名维护，以及供 AI 编程助手使用的 MCP 服务器。

## 功能

| 功能 | 说明 |
|------|------|
| 多项目管理 | 在多个 Markdown 项目之间切换，配置保存到 `config.yaml` |
| 文件监听 | 监听 `.md` 文件新增、修改、删除，并通过 WebSocket 推送到前端 |
| 引用解析 | 提取标准 Markdown 链接 `[text](path)`，构建文件依赖关系 |
| 双显示模式 | 支持全量显示和按引用显示，按引用模式从根文件向外扩展 |
| 四视图 | 文件树、引用树图、目录树图、依赖图 |
| MCP 服务器 | AI 编程助手集成，提供 16 个上下文工具 |
| 事件历史记录 | 保留 3 天回溯记录，支持按类型筛选 |
| 重命名文件 | 预览并执行文件重命名，自动更新所有引用 |
| 重新扫描 | 执行真正的磁盘扫描，并重新挂载外部文件 |
| 断链检测 | 汇总项目内和外部失效引用，支持断链静默和重复断链去重 |
| 外部文件挂载 | 挂载项目外文件或目录，按目录层级显示，重启后保留 |
| 外部引用视图 | 图 Tab 可过滤外部节点，外部节点使用虚线标识，broken 外部节点不进入视觉视图 |
| 框选和批量操作 | 多选、框选、右键隐藏、移除、恢复节点 |
| 227 个测试覆盖 | 143 个 Python 测试，84 个前端 JS 测试 |

## 视图说明

| 区域 | 内容 |
|------|------|
| 左侧文件树 | 项目文件、目录层级、引用状态、过滤和隐藏操作 |
| 中间主视图 | 引用树图、目录树图、依赖图，支持 Tab 切换 |
| 右侧面板 | 📡 实时事件、💡 同步建议、📋 历史切换 |

## 安装

```bash
git clone https://github.com/yourname/mindx.git
cd mindx
pip install -r requirements.txt
pip install -r requirements-mcp.txt    # MCP 服务器依赖
npm install                             # 前端测试依赖
```

## 启动

```bash
python server.py              # Web UI
python mcp_server.py          # MCP 服务器（供 AI 工具连接）
```

Web UI 默认访问地址：

```text
http://127.0.0.1:5020
```

首次启动会自动创建 `config.yaml`。打开界面后，通过“添加项目”选择要追踪的 Markdown 项目文件夹。

### Windows 后台启动

```powershell
.\start-mindx.ps1   # 静默后台启动
.\stop-mindx.ps1    # 停止服务
```

启动脚本会检查依赖和端口，后台启动失败时会打印 `%TEMP%\mindx-startup.log` 中的最近日志，并以失败状态退出。

## 配置

`config.yaml` 会自动生成，也可以手动调整：

```yaml
version: "1.0.0"
port: 5020
projects:
  - name: my-docs
    root: C:/path/to/my-docs
```

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/projects` | GET | 项目列表 |
| `/api/projects/add` | POST | 添加项目 |
| `/api/projects/remove` | POST | 移除项目 |
| `/api/projects/select` | POST | 激活项目 |
| `/api/status` | GET | 服务状态 |
| `/api/files` | GET | 文件列表 |
| `/api/file/<path>` | GET | 文件详情 |
| `/api/file/<path>/backlinks` | GET | 入链查询 |
| `/api/graph` | GET | 完整依赖图 |
| `/api/scan` | GET | 强制全量扫描（含外部文件重挂载）|
| `/api/broken-links` | GET | 全项目断链汇总 |
| `/api/changes` | GET | 变更日志 |
| `/api/history` | GET | 历史记录（?days=3&type=all）|
| `/api/sync-check` | GET | 同步检查 |
| `/api/file/rename-preview` | POST | 重命名预览 |
| `/api/file/rename-execute` | POST | 执行重命名 |
| `/api/external/add` | POST | 挂载外部文件 |
| `/api/external/remove` | POST | 移除外部文件 |
| `/api/external/list` | GET | 外部文件列表 |
| `/api/settings` | GET/POST | 项目设置 |

### WebSocket 事件

| 事件 | 触发场景 |
|------|----------|
| `file_changed` | 项目内 Markdown 文件新增、修改、删除 |
| `sync_needed` | 检测到关联文件可能需要同步 |
| `project_switched` | 当前激活项目切换 |
| `external_changed` | 外部挂载文件变化 |

## MCP 服务器

mindx 支持通过 MCP 协议为 AI 编程助手提供项目上下文：

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

MCP 服务器提供 16 个工具，覆盖项目管理、文件浏览、引用关系、诊断维护、文件操作等场景。

工具能力概览：

| 类别 | 能力 |
|------|------|
| 项目管理 | 列出项目、选择项目、查看服务状态 |
| 文件浏览 | 获取文件列表、读取文件详情、查询外部文件；后端提供外部状态时，MCP 会透传 mounted、unmounted、broken 等字段 |
| 引用关系 | 获取完整依赖图、查询入链、检查内部和外部断链 |
| 诊断维护 | 强制扫描、查看历史、同步检查 |
| 文件操作 | 重命名预览、执行重命名、挂载或移除外部文件 |

## 引用规则

mindx 只解析标准 Markdown 链接，格式为 `[text](path)`。

实际匹配规则：

```text
\[([^\]]*?)\]\(([^)]+)\)
```

### 可解析示例

| 写法 | 说明 |
|------|------|
| `[首页](README.md)` | 引用同目录文件 |
| `[工具说明](docs/tools.md)` | 引用子目录文件 |
| `[上级文档](../shared/guide.md)` | 引用上级目录文件 |
| `[外部资料](C:/notes/shared.md)` | 引用外部绝对路径 |
| `[本机资料](file:///C:/notes/shared.md)` | 引用本机 file:/// 路径 |

### 索引表建议

用表格维护索引文件，便于 mindx 生成稳定的引用关系：

```markdown
| 条目 | 摘要 | 路径 |
|------|------|------|
| Claude Code | AI 编程助手 | [Claude Code](memory/tools/claude-code.md) |
| OpenCode | 会话引擎 | [OpenCode](memory/tools/opencode.md) |
```

mindx 从链接目标中提取路径，并建立当前文件到目标文件的关系。

### 避免自引用

```markdown
# 不建议：文件引用自己，会产生无意义边
[当前文件](README.md)
```

### 增删文件时同步索引

| 操作 | 建议同步内容 |
|------|--------------|
| 新增工具文件 | 在根索引表加一行链接 |
| 删除工具文件 | 删除索引表中的对应行 |
| 新增项目目录 | 在项目索引文件加入入口 |
| 移动或重命名文件 | 使用重命名功能自动更新引用 |

### 外部文件引用

引用项目目录外的文件会被标记为外部链接。`file:///` 是本机路径链接语法，不是新的挂载模型；解析后仍按普通外部路径处理。

```markdown
[共享规范](../shared/MEMORY.md)
[本机规范](file:///C:/notes/shared/MEMORY.md)
```

`external_paths` 只表示用户在界面或 API 中手动挂载的外部文件或目录边界。挂载外部文件或文件夹不会让它们无条件出现在按引用显示中，只有从项目根或当前引用根沿链接链路可达时才会显示在主引用链上。

外部目标的显示语义：

| 状态 | 含义 |
|------|------|
| 已挂载 | 目标在 `external_paths` 覆盖范围内，且被引用链路触达时可作为外部节点展开 |
| 未挂载但存在 | 目标文件存在，但不在 `external_paths` 中；显示为叶子外部引用节点 |
| 断开的外部引用 | 目标文件不存在；进入断链结果和详情诊断，不显示在引用树图、目录树图或依赖图中 |

### 引用模式（按引用显示）

在设置中切换到“按引用显示”后，mindx 从指定根文件出发，沿链接关系向外扩展。不在引用链上的文件会自动隐藏。

```text
MEMORY.md
  docs/tools.md
    docs/tools/full.md
  projects/index.md
    projects/demo.md

diary/2026-05-01.md 没有关联时不会显示
```

## 项目结构

```text
mindx/
├── server.py                 # Flask 主服务、SocketIO、Web API
├── mcp_server.py             # MCP 服务器入口
├── parser.py                 # Markdown 链接解析
├── graph_engine.py           # 依赖图、断链检测、外部文件挂载
├── watcher.py                # 文件监听和项目切换
├── config.py                 # 配置读取和全局常量
├── config.yaml               # 用户项目配置，运行后生成
├── requirements.txt          # Web UI Python 依赖
├── requirements-mcp.txt      # MCP 服务器依赖
├── package.json              # 前端测试依赖和脚本
├── jest.config.js            # Jest 测试配置
├── .gitignore                # Git 忽略规则
├── templates/
│   └── index.html            # 前端入口
├── static/
│   ├── css/style.css         # 界面样式
│   └── js/app.js             # 前端交互逻辑
├── tests/                    # Python 和前端测试
├── README.md                 # 项目说明
├── DEVELOPMENT.md            # 开发记录和版本说明
├── start-mindx.ps1           # Windows 后台启动脚本
└── stop-mindx.ps1            # Windows 停止脚本
```

## 测试

```bash
python -m pytest tests/ -q    # 143 个 Python 测试
npm test                        # 84 个前端 JS 测试
```

## License

GNU General Public License v3.0
