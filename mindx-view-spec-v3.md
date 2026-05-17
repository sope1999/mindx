# 旺财记忆树 — 视图定义文档 v3.0

> 定义 mindx 三个视图（文件树、记忆树图、依赖图）各自画什么、边怎么分类、引用矩阵完整版。
> 审核通过后据此改动 mindx 程序。

---

## 一、文件分类

| 分类 | 文件 | 默认显示 |
|------|------|----------|
| **核心记忆** | MEMORY.md, memory/ 下所有文件 | ✅ 显示 |
| **基础文件** | AGENTS.md, SOUL.md, USER.md, IDENTITY.md, HEARTBEAT.md | ⬜ 可隐藏 |
| **独立文件** | TOOLS.md, urls.md, 项目开发工作规则.md, 任务工作规则.md, 项目开发管理方案.md | ⬜ 可隐藏 |
| **外部文件** | claude/ 目录, Desktop 路径 | ❌ 不纳入 |

---

## 二、引用分类（边类型）

引用分两种来源：**Markdown 链接** `[→](path)` 和 **隐式规则**（正文中的语义引用）。

### 2.1 Markdown 链接（parser 自动提取）

| 边类型 | 含义 | 示例 |
|--------|------|------|
| `INDEX_TO_CHILD` | 索引表行 → 被索引文件 | MEMORY.md → memory/tools/claude-code.md |
| `L2_TO_L3` | L2 摘要 → L3 完整版 | memory/tools/claude-code.md → memory/tools/full/claude-code.md |
| `PROJECT_REF` | 项目索引 → 项目文件 | _index.md → aviation/overview.md |
| `SELF` | 文件自引用 | 项目开发工作规则.md → 自身 |

### 2.2 隐式引用（需 parser 增强或写入配置）

| 边类型 | 含义 | 示例 | 来源 |
|--------|------|------|------|
| `CONSTITUTION_REF` | 宪法文件间引用 | AGENTS.md → MEMORY.md | AGENTS.md §Session Startup |
| `MEMORY_HEADER` | MEMORY.md 头部纯文本引用 | MEMORY.md → AGENTS.md | MEMORY.md L3 "行为规则 → AGENTS.md" |
| `TOOL_TO_PROJECT` | 工具文件 → 项目文件（调度关系） | claude-code.md → dev-sessions.md | claude-code.md "本项目活跃调度 → dev-sessions.md" |
| `SYNC_RULE` | 收尾检查规则 | system.md 变更 → overview.md 需要检查 | MEMORY.md 收尾检查表 |
| `SIBLING` | 兄弟文件（同目录、语义关联） | dev-sessions.md ↔ dev-sessions-old.md | 配置 |
| `PROJECT_SYNC` | 项目内关联 | PROJECT_PROGRESS.md ↔ overview.md | 配置 |

---

## 三、完整引用矩阵

### 3.1 Markdown 链接（已解析）

| 源文件 | 目标文件 | 边类型 |
|--------|---------|--------|
| MEMORY.md | memory/projects/_index.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/claude-code.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/opencode.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/napcat.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/ragflow.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/search.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/cron.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/vcp.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/system.md | INDEX_TO_CHILD |
| MEMORY.md | memory/tools/warning.md | INDEX_TO_CHILD |
| MEMORY.md | memory/archive/_index.md | INDEX_TO_CHILD |
| MEMORY.md | urls.md | INDEX_TO_CHILD |
| memory/projects/_index.md | memory/projects/aviation/overview.md | PROJECT_REF |
| memory/tools/claude-code.md | memory/tools/full/claude-code.md | L2_TO_L3 |
| memory/tools/opencode.md | memory/tools/full/opencode.md | L2_TO_L3 |
| — | 项目开发工作规则.md 自引用等 | SELF |

### 3.2 隐式引用（已废弃 ⛔）

> v4.0 起所有引用统一使用显式 `[→](path)` Markdown 链接，`implicit-refs.json` 已删除。
> 下表中「⬜ 待实现」的引用已通过添加显式链接完成。

| 源文件 | 目标文件 | 边类型 | 状态 |
|--------|---------|--------|------|
| _index.md | aviation/PROJECT_PROGRESS.md | PROJECT_REF | ✅ 已转为显式 |
| _index.md | aviation/dev-sessions.md | PROJECT_REF | ✅ 已转为显式 |
| _index.md | aviation/dev-sessions-old.md | PROJECT_REF | ✅ 已转为显式 |
| dev-sessions.md | dev-sessions-old.md | SIBLING | ✅ 已转为显式 |
| PROJECT_PROGRESS.md | overview.md | PROJECT_SYNC | ✅ 已转为显式 |
| MEMORY.md | TOOLS.md | MEMORY_HEADER | ✅ 已转为显式 |
| MEMORY.md | 项目开发工作规则.md | MEMORY_HEADER | ✅ 已转为显式 |
| MEMORY.md | 任务工作规则.md | MEMORY_HEADER | ✅ 已转为显式 |
| claude-code.md | dev-sessions.md | TOOL_TO_PROJECT | ⛔ 不需要（项目文档引用由 overview.md 集中管理） |
| claude-code.md | dev-sessions-old.md | TOOL_TO_PROJECT | ⛔ 同上 |
| opencode.md | dev-sessions.md | TOOL_TO_PROJECT | ⛔ 同上 |
| opencode.md | dev-sessions-old.md | TOOL_TO_PROJECT | ⛔ 同上 |
| overview.md | system.md | SYNC_RULE | ⛔ 文本中无明确引用点 |

---

## 四、三个视图的定义

### 4.1 文件树（左侧栏）

**用途**：文件导航，按引用层级排列。选中文件后在右栏显示文件信息。

**默认模式：目录**（v4.1 改）
- 引用层级 + 📁 自动分组合并
- 同 `parentDir` 的子节点归入同一文件夹
- 根层级 `mergeSuperGroups` 合并同前缀分组
- 子文件同目录不重复分组

**可选模式：引用**
- 纯引用层级，无文件夹分组

**边使用规则**：
| 边类型 | 是否纳入层次 | 说明 |
|--------|-------------|------|
| 所有 Markdown 链接 | ✅ 是 | `[→](path)` 统一解析 |
| 外部链接 | ⬜ 可选 | 勾选「外部」后显示 |

---

### 4.2 记忆树图（中间 Tab 1）

**用途**：展示记忆系统的**概念层次**——即"旺财的记忆是怎么组织的"。

**结构（固定，不随数据变化）**：
```
                         ┌─ claude-code.md (L2) ─── full/claude-code.md (L3)
                         ├─ opencode.md (L2) ─── full/opencode.md (L3)
         ┌─ 工具链 ──────┼─ napcat.md (L2)
         │               ├─ ragflow.md (L2)
         │               ├─ search.md (L2)
         │               ├─ cron.md (L2)
MEMORY.md ─┼─ 项目 ───────┼─ _index.md ─── aviation/
(L1)     │               │               ├─ overview.md (L3)
         │               │               ├─ PROJECT_PROGRESS.md (L3)
         │               │               ├─ dev-sessions.md (L3)
         │               │               └─ dev-sessions-old.md (L3)
         │               ├─ vcp.md (L2)
         │               ├─ system.md (L2)
         │               ├─ urls.md (L2)
         │               └─ warning.md (L2)
         │
         └─ 归档 ──────── _index.md (L2)
```

**画法**：
- vis.js 层次布局，方向 LR（左→右）
- 层 1（最左）：MEMORY.md
- 层 2：工具链表 + 项目索引 + 归档索引
- 层 3：工具 L3 完整版 + 项目详情文件
- 节点颜色按文件类型
- 基础文件和独立文件可切换显示

**关键**：这张图**不从 mindx parser 数据动态生成**，而是按上面的固定结构渲染。数据变化只影响节点是否存在（存在=正常色，不存在=灰色）。

---

### 4.3 依赖图（中间 Tab 2）

**用途**：展示**所有引用关系**的完整图——parser 从实际文件解析出的每一条边。

**画法**：
- vis.js 力导向布局
- 每个 `[→](path)` 链接 = 一条边
- 隐式引用（CONSTITUTION_REF, TOOL_TO_PROJECT, SIBLING）也作为边加入
- 基础文件和独立文件可切换显示

**边使用规则**：
| 边类型 | 依赖图显示 |
|--------|-----------|
| INDEX_TO_CHILD | ✅ |
| L2_TO_L3 | ✅ |
| PROJECT_REF | ✅ |
| CONSTITUTION_REF | ✅ |
| MEMORY_HEADER | ✅ |
| TOOL_TO_PROJECT | ✅ |
| SYNC_RULE | ✅ |
| SIBLING | ✅ |
| SELF | ❌ 忽略 |

---

## 五、当前 mindx 程序的问题

### 5.1 文件树
- ❌ 引用树直接从 `/api/graph` 的 markdown 链接构建，但 AGENTS.md → MEMORY.md 等隐式引用缺失，导致 MEMORY.md 无上级、AGENTS.md 孤立
- ❌ 文件树显示的是所有 markdown 链接的树，而非记忆系统的概念层次
- ✅ 基础/独立文件显隐正常

### 5.2 记忆树图
- ❌ 目前和依赖图共享同一份数据（所有 markdown 链接），没有区分"概念树"和"关系图"
- ❌ 应该按固定结构渲染概念层次，而非动态生成
- ❌ 项目开发工作规则.md 等自引用文件产生无用边

### 5.3 依赖图
- ❌ 缺少隐式引用（纯文本 `→` 引用未被解析）
- ❌ SELF 自引用边应被过滤
- ❌ claude/ 目录下的外部文件不应纳入节点

### 5.4 文件信息 / 文件详情
- ⚠ "上级文件"和"下级文件"完全等于"被引用"和"引用"，对于概念根节点 MEMORY.md 显示 `上级: 无`，忽略了 AGENTS.md → MEMORY.md 的隐式引用

---

## 六、改动计划

### 6.1 隐式引用解析策略（两层）

**第一层 — 正则自动抓取**（覆盖 80% 的隐式引用）：
匹配正文中的两种模式：
- `→ filename.md` — 箭头 + 文件名（如 MEMORY.md 头部、claude-code.md 调度说明）
- `` `filename.md` `` — 反引号包裹的文件名（如 AGENTS.md §Session Startup）

正则：`(?:→|→)\s*`?`?([a-zA-Z0-9_/\-\.]+\.md)`?`?`

解析流程：
1. 扫所有 .md 文件正文
2. 排除已在 `[text](path)` 中的链接
3. 文件名匹配 `S.files` 中的已知路径
4. 标记为 `IMPLICIT` 类型边

**第二层 — 配置文件补充**（覆盖语义引用）：
`C:\SOFT\AI\coder\memory\implicit-refs.json`：
```json
{
  "edges": [
    {"from": "dev-sessions.md", "to": "dev-sessions-old.md", "type": "SIBLING"},
    {"from": "PROJECT_PROGRESS.md", "to": "overview.md", "type": "PROJECT_SYNC"}
  ]
}
```

### 6.2 后端改动

---

## 七、概念层次数据格式（/api/memory-tree）

```json
{
  "tree": {
    "id": "MEMORY.md",
    "label": "MEMORY.md (L1)",
    "type": "root_index",
    "children": [
      {
        "id": "__group_tools",
        "label": "工具链",
        "type": "group",
        "children": [
          { "id": "memory/tools/claude-code.md", "label": "claude-code (L2)", "type": "tool_l2",
            "children": [
              { "id": "memory/tools/full/claude-code.md", "label": "claude-code (L3)", "type": "tool_l3" }
            ]
          },
          { "id": "memory/tools/opencode.md", "label": "opencode (L2)", "type": "tool_l2",
            "children": [
              { "id": "memory/tools/full/opencode.md", "label": "opencode (L3)", "type": "tool_l3" }
            ]
          },
          { "id": "memory/tools/napcat.md", "label": "napcat (L2)", "type": "tool_standalone" },
          ...
        ]
      },
      {
        "id": "__group_projects",
        "label": "项目",
        "type": "group",
        "children": [
          { "id": "memory/projects/_index.md", "label": "_index (L2)", "type": "project_index",
            "children": [
              { "id": "memory/projects/aviation/overview.md", "label": "overview (L3)", "type": "project_overview" },
              ...
            ]
          }
        ]
      },
      {
        "id": "__group_archive",
        "label": "归档",
        "type": "group",
        "children": [
          { "id": "memory/archive/_index.md", "label": "_index (L2)", "type": "archive_index" }
        ]
      }
    ]
  }
}
```

---

> **审核要点**：
> 1. 三个视图的定义是否有遗漏场景？
> 2. 隐式引用矩阵是否完整？
> 3. 概念层次结构是否正确？
> 4. 文件树引用模式的边过滤规则是否合理？
>
> 审核通过后开始改动 mindx 程序。
