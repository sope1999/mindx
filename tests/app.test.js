/**
 * Unit tests for mindx static/js/app.js
 * Tests utility functions and data processing logic.
 * Does NOT test rendering functions (too DOM-dependent).
 */

// ── DOM setup BEFORE requiring app.js ──
// app.js IIFE reads btn-theme at load time, and many event listeners bind to DOM elements.
// We provide a comprehensive DOM stub so the require() doesn't throw.
document.body.innerHTML = `
  <div id="file-tree"></div>
  <div id="ref-tree-container"></div>
  <div id="dir-tree-container"></div>
  <div id="dep-graph-container"></div>
  <input id="tree-filter" value="">
  <div id="mindx-toast"></div>
  <button id="btn-theme">🌙</button>
  <button id="btn-rescan"></button>
  <span id="chk-show-core"></span>
  <span id="chk-show-base"></span>
  <span id="chk-show-standalone"></span>
  <span id="chk-show-external"></span>
  <span id="chk-show-hidden"></span>
  <div id="app"></div>
  <div id="no-project-state"></div>
  <div id="project-tabs"></div>
  <div id="project-dropdown"></div>
  <div id="status-dot"></div>
  <div id="footer-watching"></div>
  <div id="footer-path"></div>
  <div id="file-count"></div>
  <div id="detail-empty"></div>
  <div id="detail-content"></div>
  <div id="detail-path"></div>
  <div id="detail-type-badge"></div>
  <div id="detail-meta"></div>
  <div id="detail-fullpath"></div>
  <div id="detail-parents"></div>
  <div id="detail-children"></div>
  <div id="detail-issues-section"></div>
  <div id="detail-issues"></div>
  <div id="detail-links"></div>
  <div id="detail-classify"></div>
  <div id="file-info-empty"></div>
  <div id="file-info-content"></div>
  <div id="fi-name"></div>
  <div id="fi-path"></div>
  <div id="fi-meta"></div>
  <div id="fi-parents-count"></div>
  <div id="fi-parents-list"></div>
  <div id="fi-children-count"></div>
  <div id="fi-children-list"></div>
  <div id="fi-parents-header"><span class="fi-arrow"></span></div>
  <div id="fi-children-header"><span class="fi-arrow"></span></div>
  <div id="fi-parents-list"></div>
  <div id="fi-children-list"></div>
  <button id="btn-tree-ref"></button>
  <button id="btn-tree-dir"></button>
  <button id="btn-tree-select"></button>
  <button id="btn-tree-expand"></button>
  <button id="btn-tree-collapse"></button>
  <button id="btn-ref-save"></button>
  <button id="btn-ref-refresh"></button>
  <button id="btn-dir-save"></button>
  <button id="btn-dir-refresh"></button>
  <button id="btn-dep-save"></button>
  <button id="btn-dep-refresh"></button>
  <button id="btn-show-detail"></button>
  <button id="btn-settings"></button>
  <button id="btn-settings-close"></button>
  <button id="btn-settings-cancel"></button>
  <button id="btn-settings-save"></button>
  <button id="btn-settings-delete"></button>
  <button id="btn-add-root"></button>
  <button id="btn-add-exclude"></button>
  <button id="btn-pick-exclude"></button>
  <input id="input-exclude-dir" value="">
  <button id="btn-add-external"></button>
  <button id="btn-pick-external-file"></button>
  <button id="btn-pick-external-folder"></button>
  <input id="input-external-path" value="">
  <button id="btn-batch-hide"></button>
  <button id="btn-batch-cancel"></button>
  <button id="btn-project-dropdown"></button>
  <button id="btn-no-project-add"></button>
  <button id="btn-add-project"></button>
  <button id="btn-classify-default"></button>
  <div id="modal-settings"></div>
  <div id="modal-confirm"><button id="modal-confirm-cancel"></button><button id="modal-confirm-ok"></button><div id="modal-confirm-msg"></div></div>
  <div id="modal-error"><button id="modal-error-delete"></button><button id="modal-error-rechoose"></button><div id="modal-error-msg"></div></div>
  <input id="folder-picker" type="file">
  <div id="setting-roots"></div>
  <div id="setting-root-list"></div>
  <div id="setting-exclude-list"></div>
  <div id="setting-external-list"></div>
  <input id="set-mode-ref" type="radio" name="mode">
  <input id="set-mode-full" type="radio" name="mode" checked>
  <div id="change-feed"></div>
  <div id="suggestion-feed"></div>
  <span id="footer-time"></span>
  <div id="batch-bar"><span id="batch-count"></span></div>
  <div data-tab="detail" class="tab"></div>
  <div id="tab-detail" class="tab-content"></div>
`;

// Mock vis.Network and vis.DataSet constructors
global.vis = {
  Network: class {
    constructor() {}
    on() { return this; }
    destroy() {}
    redraw() {}
    setData() {}
    selectNodes() {}
    getPositions() { return {}; }
  },
  DataSet: class {
    constructor(items) { this.items = items || []; }
  },
};

// Mock socket.io
global.io = function () {
  return { on() { return this; }, emit() { return this; } };
};

// Mock fetch to prevent real network requests during load
global.fetch = jest.fn(() =>
  Promise.resolve({ json: () => Promise.resolve({ success: true }) })
);

// ── Load app.js AFTER all mocks ──
// app.js has a duplicate `function saveDepPositions` declaration (lines 575 & 630).
// `require()` uses strict-mode parsing which rejects duplicate declarations.
// Strategy: Inject app.js as a <script> tag in the jsdom document.
// jsdom will execute it in the window context, making global `const S` and
// function declarations available on the window/global object.
const fs = require('fs');
const pathModule = require('path');
const appCode = fs.readFileSync(pathModule.join(__dirname, '..', 'static', 'js', 'app.js'), 'utf8');

const scriptEl = document.createElement('script');
scriptEl.textContent = appCode;
document.head.appendChild(scriptEl);

// After script injection, S and all functions are on global (window)
// They're accessible directly via global.S, global.getClassification, etc.
// We reference them via global for clarity.

// After requiring, global S and utility functions are available

// ── Helper: reset S state between tests ──
function resetState() {
  S.files = [];
  S.selectedFile = null;
  S.graphData = null;
  S.lastScan = null;
  S.treeMode = 'dir';
  S.showCore = true;
  S.showBase = true;
  S.showStandalone = true;
  S.showExternal = false;
  S.showHidden = false;
  S.staleMap = {};
  S.projects = [];
  S.activeProject = null;
  S.selectMode = false;
  S.selectedFiles = new Set();
  S.reachableSet = new Set();
  S.historyMode = { changes: false, sync: false };
  S._dagReachable = null;
  S._externalReachable = null;
  // Clear localStorage and settings cache
  localStorage.clear();
  // Reset the settings cache from app.js
  _settingsCache = null;
}

beforeEach(() => {
  resetState();
  jest.clearAllMocks();
});

// ═══════════════════════════════════════════
// 1. getClassification
// ═══════════════════════════════════════════
describe('getClassification', () => {
  test('returns "base" for BASE_DEFAULT files like AGENTS.md', () => {
    expect(getClassification('AGENTS.md')).toBe('base');
  });

  test('returns "base" for SOUL.md', () => {
    expect(getClassification('SOUL.md')).toBe('base');
  });

  test('returns "external" when no graphData exists', () => {
    S.graphData = null;
    expect(getClassification('some/random/file.md')).toBe('external');
  });

  test('returns "core" for a node reachable from roots in the DAG', () => {
    // MEMORY.md is a root (indeg=0), core.md is reachable from it
    S.graphData = {
      nodes: [{ id: 'MEMORY.md' }, { id: 'core.md' }],
      edges: [{ from: 'MEMORY.md', to: 'core.md' }],
    };
    expect(getClassification('MEMORY.md')).toBe('core');
    expect(getClassification('core.md')).toBe('core');
  });

  test('returns "standalone" for a node not in DAG', () => {
    S.graphData = {
      nodes: [{ id: 'MEMORY.md' }, { id: 'orphan.md' }],
      edges: [],
    };
    expect(getClassification('orphan.md')).toBe('standalone');
  });

  test('returns "external" for a node marked is_external', () => {
    S.graphData = {
      nodes: [{ id: 'ext.md', is_external: true }],
      edges: [],
    };
    expect(getClassification('ext.md')).toBe('external');
  });

  test('respects overrides from lsGet("file_classes")', () => {
    localStorage.setItem('mindx_file_classes', JSON.stringify({ 'custom.md': 'hidden' }));
    expect(getClassification('custom.md')).toBe('hidden');
  });
});

// ═══════════════════════════════════════════
// 2. isFileVisible
// ═══════════════════════════════════════════
describe('isFileVisible', () => {
  test('core file is visible when showCore=true', () => {
    S.graphData = {
      nodes: [{ id: 'MEMORY.md' }],
      edges: [],
    };
    S.showCore = true;
    expect(isFileVisible('MEMORY.md')).toBe(true);
  });

  test('core file is hidden when showCore=false', () => {
    // MEMORY.md needs edges to be classified as 'core' (reachable in DAG)
    S.graphData = {
      nodes: [{ id: 'MEMORY.md' }, { id: 'child.md' }],
      edges: [{ from: 'MEMORY.md', to: 'child.md' }],
    };
    S.showCore = false;
    expect(isFileVisible('MEMORY.md')).toBe(false);
  });

  test('base file is visible when showBase=true', () => {
    S.showBase = true;
    expect(isFileVisible('AGENTS.md')).toBe(true);
  });

  test('base file is hidden when showBase=false', () => {
    S.showBase = false;
    expect(isFileVisible('AGENTS.md')).toBe(false);
  });

  test('hidden classification is not visible when showHidden=false', () => {
    localStorage.setItem('mindx_file_classes', JSON.stringify({ 'x.md': 'hidden' }));
    S.showHidden = false;
    expect(isFileVisible('x.md')).toBe(false);
  });

  test('excluded path is not visible', () => {
    // Set up settings cache with excludedDirs
    _settingsCache = { excludedDirs: ['node_modules/'], displayMode: 'full', refRoots: [], activeRoot: null, file_classes: {} };
    expect(isFileVisible('node_modules/pkg/index.js')).toBe(false);
  });
});

// ═══════════════════════════════════════════
// 3. isExcluded
// ═══════════════════════════════════════════
describe('isExcluded', () => {
  test('returns true for path in excludedDirs', () => {
    _settingsCache = { excludedDirs: ['dist/'], displayMode: 'full', refRoots: [], activeRoot: null, file_classes: {} };
    expect(isExcluded('dist/bundle.js')).toBe(true);
  });

  test('returns true for path starting with excluded dir', () => {
    _settingsCache = { excludedDirs: ['node_modules/'], displayMode: 'full', refRoots: [], activeRoot: null, file_classes: {} };
    expect(isExcluded('node_modules/react/index.js')).toBe(true);
  });

  test('returns false for non-excluded path', () => {
    _settingsCache = { excludedDirs: ['dist/'], displayMode: 'full', refRoots: [], activeRoot: null, file_classes: {} };
    expect(isExcluded('src/app.js')).toBe(false);
  });

  test('handles Windows backslash paths', () => {
    _settingsCache = { excludedDirs: ['dist/'], displayMode: 'full', refRoots: [], activeRoot: null, file_classes: {} };
    expect(isExcluded('dist\\bundle.js')).toBe(true);
  });
});

// ═══════════════════════════════════════════
// 4. parentDir
// ═══════════════════════════════════════════
describe('parentDir', () => {
  test('extracts parent directory from nested path', () => {
    expect(parentDir('a/b/c.md')).toBe('a/b/');
  });

  test('returns empty string for root-level file', () => {
    expect(parentDir('root.md')).toBe('');
  });

  test('handles deeply nested paths', () => {
    expect(parentDir('src/components/utils/helper.js')).toBe('src/components/utils/');
  });
});

// ═══════════════════════════════════════════
// 5. baseName
// ═══════════════════════════════════════════
describe('baseName', () => {
  test('extracts filename from nested path', () => {
    expect(baseName('a/b/c.md')).toBe('c.md');
  });

  test('returns the path itself for root-level file', () => {
    expect(baseName('root.md')).toBe('root.md');
  });

  test('handles single-segment path', () => {
    expect(baseName('index.js')).toBe('index.js');
  });
});

// ═══════════════════════════════════════════
// 6. getFileIcon
// ═══════════════════════════════════════════
describe('getFileIcon', () => {
  test('returns home icon for root_index', () => {
    expect(getFileIcon('root_index')).toBe('🏠');
  });

  test('returns document icon for unknown type', () => {
    expect(getFileIcon('unknown_type')).toBe('📄');
  });

  test('returns constitution icon', () => {
    expect(getFileIcon('constitution')).toBe('📜');
  });

  test('returns cheatsheet icon', () => {
    expect(getFileIcon('cheatsheet')).toBe('📋');
  });
});

// ═══════════════════════════════════════════
// 7. getMemoryLevel
// ═══════════════════════════════════════════
describe('getMemoryLevel', () => {
  test('returns L1 for MEMORY.md', () => {
    expect(getMemoryLevel('MEMORY.md', 'root_index')).toBe('L1');
  });

  test('returns L2 for project_index', () => {
    expect(getMemoryLevel('some.md', 'project_index')).toBe('L2');
  });

  test('returns L2 for tool_l2', () => {
    expect(getMemoryLevel('tool.md', 'tool_l2')).toBe('L2');
  });

  test('returns L3 for tool_l3', () => {
    expect(getMemoryLevel('tool.md', 'tool_l3')).toBe('L3');
  });

  test('returns L3 for diary', () => {
    expect(getMemoryLevel('diary.md', 'diary')).toBe('L3');
  });

  test('returns null for unknown type', () => {
    expect(getMemoryLevel('random.md', 'unknown')).toBeNull();
  });
});

// ═══════════════════════════════════════════
// 8. S state initialization
// ═══════════════════════════════════════════
describe('S state initialization', () => {
  test('S.files is an array', () => {
    expect(Array.isArray(S.files)).toBe(true);
  });

  test('S.treeMode defaults to "dir"', () => {
    expect(S.treeMode).toBe('dir');
  });

  test('S.showCore defaults to true', () => {
    expect(S.showCore).toBe(true);
  });

  test('S.showExternal defaults to false', () => {
    expect(S.showExternal).toBe(false);
  });

  test('S.showHidden defaults to false', () => {
    expect(S.showHidden).toBe(false);
  });

  test('S.selectedFiles is a Set', () => {
    expect(S.selectedFiles).toBeInstanceOf(Set);
  });

  test('S.reachableSet is a Set', () => {
    expect(S.reachableSet).toBeInstanceOf(Set);
  });
});

// ═══════════════════════════════════════════
// 9. BASE_DEFAULT
// ═══════════════════════════════════════════
describe('BASE_DEFAULT', () => {
  test('includes AGENTS.md', () => {
    expect(BASE_DEFAULT.has('AGENTS.md')).toBe(true);
  });

  test('includes SOUL.md', () => {
    expect(BASE_DEFAULT.has('SOUL.md')).toBe(true);
  });

  test('includes USER.md', () => {
    expect(BASE_DEFAULT.has('USER.md')).toBe(true);
  });

  test('includes IDENTITY.md', () => {
    expect(BASE_DEFAULT.has('IDENTITY.md')).toBe(true);
  });

  test('includes HEARTBEAT.md', () => {
    expect(BASE_DEFAULT.has('HEARTBEAT.md')).toBe(true);
  });

  test('does not include MEMORY.md', () => {
    expect(BASE_DEFAULT.has('MEMORY.md')).toBe(false);
  });
});

// ═══════════════════════════════════════════
// 10. History mode state
// ═══════════════════════════════════════════
describe('S.historyMode', () => {
  test('changes defaults to false', () => {
    expect(S.historyMode.changes).toBe(false);
  });

  test('sync defaults to false', () => {
    expect(S.historyMode.sync).toBe(false);
  });
});

// ═══════════════════════════════════════════
// 11. lsGet / lsSet
// ═══════════════════════════════════════════
describe('lsGet / lsSet', () => {
  test('lsSet stores and lsGet retrieves a value', () => {
    lsSet('test_key', { foo: 42 });
    expect(lsGet('test_key')).toEqual({ foo: 42 });
  });

  test('lsGet returns null for missing key', () => {
    expect(lsGet('nonexistent_key')).toBeNull();
  });

  test('lsGet handles corrupt JSON gracefully', () => {
    localStorage.setItem('mindx_test_bad', 'not-json');
    expect(lsGet('test_bad')).toBeNull();
  });
});

// ═══════════════════════════════════════════
// 12. computeStaleMap
// ═══════════════════════════════════════════
describe('computeStaleMap', () => {
  test('marks source as stale when target is newer', () => {
    S.files = [
      { path: 'old.md', last_modified: '2024-01-01T00:00:00Z' },
      { path: 'new.md', last_modified: '2024-06-01T00:00:00Z' },
    ];
    S.graphData = {
      nodes: [],
      edges: [{ from: 'old.md', to: 'new.md' }],
    };
    computeStaleMap();
    expect(S.staleMap['old.md']).toBe(true);
  });

  test('does not mark source as stale when target is older', () => {
    S.files = [
      { path: 'new.md', last_modified: '2024-06-01T00:00:00Z' },
      { path: 'old.md', last_modified: '2024-01-01T00:00:00Z' },
    ];
    S.graphData = {
      nodes: [],
      edges: [{ from: 'new.md', to: 'old.md' }],
    };
    computeStaleMap();
    expect(S.staleMap['new.md']).toBeUndefined();
  });

  test('handles null graphData gracefully', () => {
    S.graphData = null;
    computeStaleMap();
    expect(S.staleMap).toEqual({});
  });
});

// ═══════════════════════════════════════════
// 13. computeReachable
// ═══════════════════════════════════════════
describe('computeReachable', () => {
  test('computes reachable set from a root', () => {
    S.graphData = {
      nodes: [],
      edges: [
        { from: 'A', to: 'B' },
        { from: 'B', to: 'C' },
      ],
    };
    const result = computeReachable('A');
    expect(result.has('A')).toBe(true);
    expect(result.has('B')).toBe(true);
    expect(result.has('C')).toBe(true);
  });

  test('does not reach disconnected nodes', () => {
    S.graphData = {
      nodes: [],
      edges: [{ from: 'A', to: 'B' }],
    };
    const result = computeReachable('A');
    expect(result.has('C')).toBe(false);
  });

  test('returns empty set when rootPath is null', () => {
    S.graphData = { nodes: [], edges: [] };
    const result = computeReachable(null);
    expect(result.size).toBe(0);
  });
});

// ═══════════════════════════════════════════
// 13b. computeRefLevels
// ═══════════════════════════════════════════
describe('computeRefLevels', () => {
  test('normal DAG: root level 0, children level 1+', () => {
    const graphData = {
      nodes: [],
      edges: [
        { from: 'MEMORY.md', to: 'a.md' },
        { from: 'MEMORY.md', to: 'b.md' },
        { from: 'a.md', to: 'c.md' },
      ],
    };
    const visible = new Set(['MEMORY.md', 'a.md', 'b.md', 'c.md']);
    const levels = computeRefLevels(graphData, visible);
    expect(levels['MEMORY.md']).toBe(0);
    expect(levels['a.md']).toBe(1);
    expect(levels['b.md']).toBe(1);
    expect(levels['c.md']).toBe(2);
  });

  test('cycle nodes get level based on best incoming edge', () => {
    // opencode.md (level 1) references both cycle members
    // cycle: projects ↔ sessions
    const graphData = {
      nodes: [],
      edges: [
        { from: 'MEMORY.md', to: 'opencode.md' },
        { from: 'opencode.md', to: 'opencode-projects.md' },
        { from: 'opencode.md', to: 'opencode-sessions.md' },
        { from: 'opencode-projects.md', to: 'opencode-sessions.md' },
        { from: 'opencode-sessions.md', to: 'opencode-projects.md' },
      ],
    };
    const visible = new Set(['MEMORY.md', 'opencode.md', 'opencode-projects.md', 'opencode-sessions.md']);
    const levels = computeRefLevels(graphData, visible);
    expect(levels['MEMORY.md']).toBe(0);
    expect(levels['opencode.md']).toBe(1);
    // Both cycle nodes should be level 2 (from opencode.md level 1 + 1)
    expect(levels['opencode-projects.md']).toBe(2);
    expect(levels['opencode-sessions.md']).toBe(2);
  });

  test('isolated nodes get level -1', () => {
    const graphData = {
      nodes: [],
      edges: [
        { from: 'MEMORY.md', to: 'a.md' },
      ],
    };
    const visible = new Set(['MEMORY.md', 'a.md', 'orphan.md']);
    const levels = computeRefLevels(graphData, visible);
    expect(levels['MEMORY.md']).toBe(0);
    expect(levels['a.md']).toBe(1);
    expect(levels['orphan.md']).toBe(-1);
  });

  test('cycle with no external incoming edges defaults to level 0', () => {
    // Pure cycle with no root reaching it
    const graphData = {
      nodes: [],
      edges: [
        { from: 'x.md', to: 'y.md' },
        { from: 'y.md', to: 'x.md' },
      ],
    };
    const visible = new Set(['MEMORY.md', 'x.md', 'y.md']);
    const levels = computeRefLevels(graphData, visible);
    // MEMORY.md has no edges at all → isolated → -1
    expect(levels['MEMORY.md']).toBe(-1);
    // x and y are in a cycle with no external incoming edges, bestLevel=undefined, origIndegree>0 → 0
    expect(levels['x.md']).toBe(0);
    expect(levels['y.md']).toBe(0);
  });
});

// ═══════════════════════════════════════════
// 14. External reference display status
// ═══════════════════════════════════════════
describe('external reference display status', () => {
  beforeEach(() => {
    S.showExternal = true;
  });

  test('hides mounted external files that are not reached by a non-external reference chain', () => {
    S.files = [{ path: 'C:/ext/unreached.md', type: 'external' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/unreached.md', is_external: true, mounted: true, exists: true },
      ],
      edges: [],
    };

    expect(getExternalStatus('C:/ext/unreached.md')).toBe('mounted');
    expect(isFileVisible('C:/ext/unreached.md')).toBe(false);
  });

  test('shows mounted external files reached through the reference graph', () => {
    S.files = [{ path: 'C:/ext/reached.md', type: 'external' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/reached.md', is_external: true, mounted: true, exists: true },
      ],
      edges: [{ from: 'MEMORY.md', to: 'C:/ext/reached.md' }],
    };

    expect(isFileVisible('C:/ext/reached.md')).toBe(true);
  });

  test('adds referenced unmounted external leaf nodes from graph data without requiring S.files entries', () => {
    S.files = [{ path: 'MEMORY.md', type: 'root_index' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/leaf.md', is_external: true, mounted: false, exists: true, group: 'external' },
      ],
      edges: [{ from: 'MEMORY.md', to: 'C:/ext/leaf.md' }],
    };

    expect(getExternalStatus('C:/ext/leaf.md')).toBe('unmounted');
    expect(getDisplayFiles().map(f => f.path)).toContain('C:/ext/leaf.md');
    expect(isFileVisible('C:/ext/leaf.md')).toBe(true);
  });

  test('labels missing external references as broken leaves', () => {
    S.files = [{ path: 'MEMORY.md', type: 'root_index' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/missing.md', is_external: true, mounted: false, exists: false, group: 'external' },
      ],
      edges: [{ from: 'MEMORY.md', to: 'C:/ext/missing.md' }],
    };

    expect(getExternalStatus('C:/ext/missing.md')).toBe('broken');
    expect(isFileVisible('C:/ext/missing.md')).toBe(true);
  });

  test('does not misclassify explicit unmounted status as mounted', () => {
    S.graphData = {
      nodes: [{ id: 'C:/ext/leaf.md', is_external: true, mounted: false, exists: true, external_status: 'unmounted' }],
      edges: [],
    };

    expect(getExternalStatus('C:/ext/leaf.md')).toBe('unmounted');
  });

  test('broken status takes precedence over mounted hints', () => {
    S.graphData = {
      nodes: [{ id: 'C:/ext/missing.md', is_external: true, mounted: true, exists: false, external_status: 'mounted' }],
      edges: [],
    };

    expect(getExternalStatus('C:/ext/missing.md')).toBe('broken');
  });
});

// ═══════════════════════════════════════════
// 15. getDisplayFiles skips broken external nodes
// ═══════════════════════════════════════════
describe('getDisplayFiles skips broken external nodes', () => {
  test('excludes nodes with exists=false from display files', () => {
    S.files = [{ path: 'MEMORY.md', type: 'root_index' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/missing.md', is_external: true, exists: false, group: 'external' },
      ],
      edges: [{ from: 'MEMORY.md', to: 'C:/ext/missing.md' }],
    };

    const paths = getDisplayFiles().map(f => f.path);
    expect(paths).not.toContain('C:/ext/missing.md');
    // But getDisplayFile still works for detail panel
    expect(getDisplayFile('C:/ext/missing.md')).toBeTruthy();
  });

  test('excludes nodes with absent=true from display files', () => {
    S.files = [{ path: 'MEMORY.md', type: 'root_index' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/absent.md', is_external: true, absent: true, group: 'external' },
      ],
      edges: [{ from: 'MEMORY.md', to: 'C:/ext/absent.md' }],
    };

    const paths = getDisplayFiles().map(f => f.path);
    expect(paths).not.toContain('C:/ext/absent.md');
  });

  test('includes mounted external nodes with exists=true', () => {
    S.files = [{ path: 'MEMORY.md', type: 'root_index' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/real.md', is_external: true, exists: true, mounted: true, group: 'external' },
      ],
      edges: [{ from: 'MEMORY.md', to: 'C:/ext/real.md' }],
    };

    const paths = getDisplayFiles().map(f => f.path);
    expect(paths).toContain('C:/ext/real.md');
  });

  test('includes unmounted external leaf nodes with exists=true', () => {
    S.files = [{ path: 'MEMORY.md', type: 'root_index' }];
    S.graphData = {
      nodes: [
        { id: 'MEMORY.md', is_external: false },
        { id: 'C:/ext/leaf.md', is_external: true, mounted: false, exists: true, group: 'external' },
      ],
      edges: [{ from: 'MEMORY.md', to: 'C:/ext/leaf.md' }],
    };

    const paths = getDisplayFiles().map(f => f.path);
    expect(paths).toContain('C:/ext/leaf.md');
  });
});

// ═══════════════════════════════════════════
// 16. getFtypeLabel
// ═══════════════════════════════════════════
describe('getFtypeLabel', () => {
  test('returns Chinese label for root_index', () => {
    expect(getFtypeLabel('root_index')).toBe('根索引');
  });

  test('returns the type itself for unknown types', () => {
    expect(getFtypeLabel('custom_type')).toBe('custom_type');
  });
});

// ═══════════════════════════════════════════
// 17. bumpReadCount / getReadCount
// ═══════════════════════════════════════════
describe('bumpReadCount / getReadCount', () => {
  test('bumps read count and returns incremented value', () => {
    const count = bumpReadCount('test.md');
    expect(count).toBe(1);
    expect(getReadCount('test.md')).toBe(1);
  });

  test('accumulates multiple bumps', () => {
    bumpReadCount('doc.md');
    bumpReadCount('doc.md');
    bumpReadCount('doc.md');
    expect(getReadCount('doc.md')).toBe(3);
  });

  test('returns 0 for unread file', () => {
    expect(getReadCount('never-read.md')).toBe(0);
  });
});

// ═══════════════════════════════════════════
// 18. buildRefTree
// ═══════════════════════════════════════════
describe('buildRefTree', () => {
  test('builds tree from graph edges', () => {
    S.files = [{ path: 'MEMORY.md' }, { path: 'child.md' }];
    const graphData = {
      nodes: [{ id: 'MEMORY.md' }, { id: 'child.md' }],
      edges: [{ from: 'MEMORY.md', to: 'child.md' }],
    };
    const tree = buildRefTree(graphData);
    expect(tree.length).toBeGreaterThan(0);
    expect(tree[0].path).toBe('MEMORY.md');
    expect(tree[0].children.length).toBe(1);
    expect(tree[0].children[0].path).toBe('child.md');
  });

  test('returns empty array for null graphData', () => {
    expect(buildRefTree(null)).toEqual([]);
  });

  test('MEMORY.md sorts first among roots', () => {
    S.files = [{ path: 'MEMORY.md' }, { path: 'alpha.md' }, { path: 'beta.md' }];
    const graphData = {
      nodes: [{ id: 'MEMORY.md' }, { id: 'alpha.md' }, { id: 'beta.md' }],
      edges: [],
    };
    const tree = buildRefTree(graphData);
    expect(tree[0].path).toBe('MEMORY.md');
  });
});

// ═══════════════════════════════════════════
// 19. renderDetail silence button for broken_external_link
// ═══════════════════════════════════════════
describe('renderDetail silence button for external broken links', () => {
  test('shows silence button for broken_external_link issues', () => {
    const data = {
      path: 'test.md',
      type: 'md',
      exists: true,
      size: 100,
      last_modified: null,
      abs_path: '/tmp/test.md',
      dependencies: { referenced_by: [], references: [] },
      links: [],
      silenced_links: [],
      issues: [
        { type: 'broken_external_link', target: 'C:/ext/missing.md', detail: '外部链接目标不存在: C:/ext/missing.md' },
      ],
    };
    renderDetail(data);
    const issuesHtml = document.getElementById('detail-issues').innerHTML;
    expect(issuesHtml).toContain('silence-btn');
    expect(issuesHtml).toContain('C:/ext/missing.md');
  });

  test('silence button still works for broken_link issues', () => {
    const data = {
      path: 'test.md',
      type: 'md',
      exists: true,
      size: 100,
      last_modified: null,
      abs_path: '/tmp/test.md',
      dependencies: { referenced_by: [], references: [] },
      links: [],
      silenced_links: [],
      issues: [
        { type: 'broken_link', target: 'missing.md', detail: '链接目标不存在: missing.md' },
      ],
    };
    renderDetail(data);
    const issuesHtml = document.getElementById('detail-issues').innerHTML;
    expect(issuesHtml).toContain('silence-btn');
    expect(issuesHtml).toContain('missing.md');
  });
});
