/* mindx v4.2 */

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

const BASE_DEFAULT = new Set(['AGENTS.md','SOUL.md','USER.md','IDENTITY.md','HEARTBEAT.md']);

// Theme
(function(){
  const saved=localStorage.getItem('mindx_theme')||'dark';
  document.documentElement.setAttribute('data-theme',saved);
  document.getElementById('btn-theme').textContent=saved==='light'?'☀️':'🌙';
})();

// ── Classification ──
function getClassification(path) {
  const overrides = lsGet('file_classes') || {};
  if (overrides[path]) return overrides[path];
  return getDefaultClassification(path);
}
function getDefaultClassification(path) {
  // Universal base files (same across all OpenCode projects)
  if (BASE_DEFAULT.has(path)) return 'base';
  // Reference-tree-based for everything else
  if (!S.graphData || !S.graphData.edges) return 'external';
  const node = (S.graphData.nodes || []).find(n => n.id === path);
  if (node && node.is_external) return 'external';
  // Build reachable set from roots (indeg=0 nodes) — standalone = not in DAG
  if (!S._dagReachable) {
    const edges = S.graphData.edges || [];
    const indeg = {}, adj = {};
    for (const e of edges) { indeg[e.to] = (indeg[e.to] || 0) + 1; (adj[e.from] = adj[e.from] || []).push(e.to); }
    const roots = Object.keys(adj).filter(n => !indeg[n]);
    S._dagReachable = new Set();
    const q = [...roots];
    while (q.length) {
      const n = q.shift();
      if (S._dagReachable.has(n)) continue;
      S._dagReachable.add(n);
      for (const c of (adj[n] || [])) { if (!S._dagReachable.has(c)) q.push(c); }
    }
  }
  if (!S._dagReachable.has(path)) return 'standalone';
  return 'core';
}
function setClassification(path, cls) {
  const overrides = lsGet('file_classes') || {};
  if (!cls || cls === 'default') { delete overrides[path]; }
  else { overrides[path] = cls; }
  lsSet('file_classes', overrides);
  const s=getSettings();s.file_classes=overrides;saveSettings(s);
}
function isBaseFile(p) { return getClassification(p) === 'base'; }
function isStandaloneFile(p) { return getClassification(p) === 'standalone'; }
function isExternalFile(p) { return getClassification(p) === 'external'; }
function isCoreFile(p) { return getClassification(p) === 'core'; }
function isHiddenFile(p) { return getClassification(p) === 'hidden'; }

function getGraphNode(path) { return (S.graphData?.nodes || []).find(n => n.id === path); }
function hasGraphEdges(path) { return (S.graphData?.edges || []).some(e => e.from === path || e.to === path); }
function getExternalStatus(path) {
  const node = getGraphNode(path);
  if (!node || !node.is_external) return null;
  const raw = String(node.external_status || node.status || '').toLowerCase();
  if (node.exists === false || node.broken || raw === 'broken' || raw === 'missing') return 'broken';
  if (node.mounted === true || raw === 'mounted') return 'mounted';
  if (raw === 'unmounted') return 'unmounted';
  return 'unmounted';
}
function getExternalStatusLabel(status) { return { mounted: '已挂载外部文件', unmounted: '未挂载外部引用叶子', broken: '外部引用缺失' }[status] || ''; }
function isExternalReached(path) {
  if (!S.graphData) return false;
  if (!S._externalReachable) {
    const nodesById = new Map((S.graphData.nodes || []).map(n => [n.id, n]));
    const queue = (S.graphData.nodes || []).filter(n => !n.is_external).map(n => n.id);
    const seen = new Set(queue);
    S._externalReachable = new Set();
    while (queue.length) {
      const cur = queue.shift();
      for (const e of (S.graphData.edges || [])) {
        if (e.from !== cur || seen.has(e.to)) continue;
        seen.add(e.to);
        const target = nodesById.get(e.to);
        if (target?.is_external) S._externalReachable.add(e.to);
        queue.push(e.to);
      }
    }
  }
  return S._externalReachable.has(path);
}
function isExternalReferenceVisible(path) {
  const status = getExternalStatus(path);
  if (!status) return true;
  if (status === 'mounted') return isExternalReached(path);
  return hasGraphEdges(path);
}
function getDisplayFile(path) {
  const file = S.files.find(f => f.path === path);
  if (file) return file;
  const node = getGraphNode(path);
  if (!node?.is_external) return null;
  return { path, type: node.group || node.type || 'external', exists: node.exists, size: node.size, last_modified: node.last_modified, link_count: 0, backlink_count: 0 };
}
function getDisplayFiles() {
  const byPath = new Map(S.files.map(f => [f.path, f]));
  for (const node of (S.graphData?.nodes || [])) {
    if (node.is_external && !byPath.has(node.id) && node.absent !== true && node.exists !== false) byPath.set(node.id, getDisplayFile(node.id));
  }
  return [...byPath.values()].filter(Boolean);
}

function isFileVisible(path) {
  if (isExcluded(path)) return false;
  const cls = getClassification(path);
  if (cls === 'hidden' && !S.showHidden) return false;
  const s=getSettings();
  if (s.displayMode==='ref' && s.activeRoot) { if (!S.reachableSet.has(path)) return false; }
  if (cls === 'core' && !S.showCore) return false;
  if (cls === 'base' && !S.showBase) return false;
  if (cls === 'standalone' && !S.showStandalone) return false;
  if (cls === 'external' && !S.showExternal) return false;
  if (cls === 'external' && !isExternalReferenceVisible(path)) return false;
  // In ref mode, external files must have reference relationships
  if (cls === 'external' && S.treeMode === 'ref' && S.graphData) {
    const hasEdges = (S.graphData.edges || []).some(e => e.from === path || e.to === path);
    if (!hasEdges) return false;
  }
  return true;
}
function isVisibleInGraph(path) {
  const s=getSettings();
  if (s.displayMode==='ref' && s.activeRoot) { if (!S.reachableSet.has(path)) return false; }
  return isFileVisible(path);
}

// ── Utils ──
function getFileIcon(ft){const m={root_index:'🏠',constitution:'📜',cheatsheet:'📋',manual:'📖',bookmarks:'🔖',project_index:'📊',project_overview:'📝',project_progress:'📈',dev_sessions:'🔄',dev_sessions_old:'📦',tool_l2:'⚙️',tool_l3:'📚',tool_standalone:'🔧',archive_index:'🗄',diary:'📅',root_doc:'📄'};return m[ft]||'📄';}
function getGroupColor(ft){const isLight=document.documentElement.getAttribute('data-theme')==='light';if(isLight){const c={root_index:'#d4e2fc',constitution:'#fde8d0',project_index:'#d4f5d4',project_overview:'#d4f5d4',project_progress:'#c8f0c8',dev_sessions:'#d4e2fc',dev_sessions_old:'#e0e3e8',tool_l2:'#e6d9fc',tool_l3:'#f0e4fc',tool_standalone:'#e4d9f7',archive_index:'#e0e3e8',diary:'#e8e8e8',cheatsheet:'#fde8d0',manual:'#fde8d0',bookmarks:'#fde8d0'};return c[ft]||'#e8e8e8';}const c={root_index:'#1e3a5f',constitution:'#3d2b1a',project_index:'#1a3d1a',project_overview:'#1a3d1a',project_progress:'#153d18',dev_sessions:'#1e3a5f',dev_sessions_old:'#2a3038',tool_l2:'#2d1a5f',tool_l3:'#2d1a5f',tool_standalone:'#2d1a5f',archive_index:'#2a3038',diary:'#22262b',cheatsheet:'#3d2b1a',manual:'#3d2b1a',bookmarks:'#3d2b1a'};return c[ft]||'#22262b';}
function getFontColor(){return document.documentElement.getAttribute('data-theme')==='light'?'#000000':'#ffffff';}
function getNodeBorderColor(){return document.documentElement.getAttribute('data-theme')==='light'?'#c8d6e5':'#1c1f2e';}
function getDirBgColor(){return document.documentElement.getAttribute('data-theme')==='light'?'#f0f4f8':'#1c2129';}
function getDirBorderColor(){return document.documentElement.getAttribute('data-theme')==='light'?'#c8d6e5':'#30363d';}
function getRootBgColor(){return document.documentElement.getAttribute('data-theme')==='light'?'#c8d6e5':'#30363d';}
function getRootBorderColor(){return document.documentElement.getAttribute('data-theme')==='light'?'#4f7fd6':'#58a6ff';}
function getFtypeLabel(ft){const m={root_index:'根索引',constitution:'宪法',cheatsheet:'速查卡',manual:'手册',bookmarks:'书签',project_index:'项目索引',project_overview:'项目档案',project_progress:'进度',dev_sessions:'活跃调度',dev_sessions_old:'调度历史',tool_l2:'工具L2',tool_l3:'工具L3',tool_standalone:'工具',archive_index:'归档索引',diary:'日记',root_doc:'文档'};return m[ft]||ft;}
function getMemoryLevel(p,ft){if(p==='MEMORY.md')return'L1';if(ft==='project_index'||ft==='archive_index'||ft==='tool_l2')return'L2';if(ft==='tool_l3'||ft==='project_overview'||ft==='project_progress'||ft==='dev_sessions'||ft==='dev_sessions_old'||ft==='diary')return'L3';return null;}
function getNodeColor(ftype,path){const cls=getClassification(path);const isLight=document.documentElement.getAttribute('data-theme')==='light';if(cls==='base')return isLight?'#d4e2fc':'#1e3a5f';if(cls==='standalone')return isLight?'#fde8d0':'#3d2b1a';if(cls==='external')return isLight?'#d3f0f4':'#1a3d3f';return getGroupColor(ftype);}
function parentDir(p){const i=p.lastIndexOf('/');return i<0?'':p.slice(0,i+1);}
function baseName(p){const i=p.lastIndexOf('/');return i<0?p:p.slice(i+1);}
function pkey(k){return 'mindx_'+(S.activeProject?S.activeProject.name+'_':'')+k;}
function lsGet(k){try{return JSON.parse(localStorage.getItem(pkey(k)));}catch(e){return null;}}
function lsSet(k,v){try{localStorage.setItem(pkey(k),JSON.stringify(v));}catch(e){}}
function lsGetConfirmed(){return new Set(lsGet('confirmed')||[]);}
function lsAddConfirmed(id){const s=lsGetConfirmed();s.add(id);lsSet('confirmed',[...s]);}
function lsIsConfirmed(id){return lsGetConfirmed().has(id);}
function computeStaleMap(){S.staleMap={};if(!S.graphData)return;const fm={};for(const f of S.files)fm[f.path]=f;for(const e of S.graphData.edges){const src=fm[e.from],tgt=fm[e.to];if(src&&tgt&&src.last_modified&&tgt.last_modified&&new Date(tgt.last_modified)>new Date(src.last_modified))S.staleMap[e.from]=true;}}
function bumpReadCount(path){const rc=lsGet('read_counts')||{};rc[path]=(rc[path]||0)+1;lsSet('read_counts',rc);return rc[path];}
function getReadCount(path){return (lsGet('read_counts')||{})[path]||0;}

// ── Reference tree ──
function buildRefTree(graphData){
  if(!graphData||!graphData.edges)return[];
  const refs={},refsBy={},allNodes=new Set();
  for(const n of graphData.nodes)allNodes.add(n.id);for(const f of S.files)allNodes.add(f.path);
  for(const e of graphData.edges){if(!refs[e.from])refs[e.from]=[];refs[e.from].push(e.to);if(!refsBy[e.to])refsBy[e.to]=[];refsBy[e.to].push(e.from);}
  const roots=[];for(const node of allNodes){if(!refsBy[node]||refsBy[node].length===0)roots.push(node);}
  roots.sort((a,b)=>{if(a==='MEMORY.md')return-1;if(b==='MEMORY.md')return 1;return a.localeCompare(b);});
  const visited=new Set();
  function build(p,depth){if(visited.has(p)||depth>10)return null;visited.add(p);const kids=(refs[p]||[]).filter(c=>allNodes.has(c)).map(c=>build(c,depth+1)).filter(Boolean);visited.delete(p);return{path:p,children:kids};}
  return roots.map(r=>build(r,0)).filter(Boolean);
}
function filterRefTree(nodes,visiblePaths){return nodes.map(n=>filterRefNode(n,visiblePaths)).filter(Boolean);}
function filterRefNode(node,visiblePaths){const filtered=node.children.map(c=>filterRefNode(c,visiblePaths)).filter(Boolean);if(node.isGroup)return filtered.length>0?{...node,children:filtered}:null;if(visiblePaths.has(node.path))return{path:node.path,children:filtered,hidden:false};if(filtered.length>0)return{path:node.path,children:filtered,hidden:true};return null;}

// ── File tree ──
function renderFileTree(){
  const filter=(document.getElementById('tree-filter').value||'').toLowerCase();
  const visualFiles=getDisplayFiles().filter(f=>isFileVisible(f.path)&&(!filter||f.path.toLowerCase().includes(filter)));
  const c=document.getElementById('file-tree');c.innerHTML='';
  if(!S.graphData){c.innerHTML='<div class="empty-state small">加载中...</div>';return;}
  let refTree=buildRefTree(S.graphData);
  if(S.treeMode==='dir'){refTree=wrapExternalRoots(refTree);refTree=addDirGroups(refTree);}
  const visiblePaths=new Set(visualFiles.map(f=>f.path));
  const filtered=filterRefTree(refTree,visiblePaths);
  filtered.forEach(n=>renderRefNode(c,n,0));
}
function renderRefNode(container,node,depth){
  if(!node)return;const hasKids=node.children.length>0;const wrapper=document.createElement('div');const row=document.createElement('div');
  if(node.isGroup){
    row.className='tree-item group-node';
    row.style.paddingLeft=(8+depth*14)+'px';row.dataset.path=node.path;
    const toggle=document.createElement('span');toggle.className='tree-toggle expanded';toggle.textContent='▶';row.appendChild(toggle);
    const ic=document.createElement('span');ic.className='tree-icon';ic.textContent='📁';row.appendChild(ic);
    const nm=document.createElement('span');nm.className='tree-name';nm.textContent=node.groupLabel;nm.style.fontWeight='600';nm.style.color='var(--text)';row.appendChild(nm);
    const cnt=document.createElement('span');cnt.className='fi-count';cnt.textContent='('+hasKids+')';row.appendChild(cnt);
    const kc=document.createElement('div');kc.className='tree-children';
    toggle.addEventListener('click',e=>{e.stopPropagation();toggle.classList.toggle('expanded');kc.classList.toggle('collapsed');});
    row.addEventListener('click',e=>{if(e.target!==toggle)toggle.click();});
    wrapper.appendChild(row);wrapper.appendChild(kc);container.appendChild(wrapper);
    node.children.forEach(c=>renderRefNode(kc,c,depth+1));return;
  }
  const f=getDisplayFile(node.path);const level=f?getMemoryLevel(node.path,f.type):null;const icon=f?getFileIcon(f.type):'📄';const name=baseName(node.path);const isStale=!!S.staleMap[node.path];const cls=getClassification(node.path);const extStatus=getExternalStatus(node.path);
  row.className='tree-item'+(isStale?' stale-ref':'')+(node.hidden?' hidden-parent':'')+(cls==='hidden'?' cls-hidden':'')+' cls-'+cls;
  row.style.paddingLeft=(8+depth*14)+'px';row.dataset.path=node.path;
  if(extStatus)row.title=getExternalStatusLabel(extStatus)+'\n'+node.path;
  if(cls==='external')row.style.opacity='0.6';
  if(S.selectMode&&!node.isGroup){const cb=document.createElement('input');cb.type='checkbox';cb.className='tree-cb';cb.dataset.path=node.path;cb.checked=S.selectedFiles.has(node.path);cb.addEventListener('click',e=>{e.stopPropagation();toggleFileSelect(node.path);});row.appendChild(cb);}
  const toggle=document.createElement('span');toggle.className='tree-toggle'+(hasKids?' expanded':' leaf');toggle.textContent='▶';row.appendChild(toggle);
  const ic=document.createElement('span');ic.className='tree-icon';ic.textContent=icon;row.appendChild(ic);
  const nm=document.createElement('span');nm.className='tree-name';nm.textContent=name;if(node.hidden){nm.style.opacity='0.35';nm.style.textDecoration='line-through';}row.appendChild(nm);
  if(level){const b=document.createElement('span');b.className='level-badge '+level;b.textContent=level;row.appendChild(b);}
  if(cls==='base'){const eb=document.createElement('span');eb.className='level-badge cls-tail base';eb.textContent='基';row.appendChild(eb);}
  else if(cls==='standalone'){const eb=document.createElement('span');eb.className='level-badge cls-tail standalone';eb.textContent='独';row.appendChild(eb);}
  else if(cls==='external'){const eb=document.createElement('span');eb.className='level-badge cls-tail external '+(extStatus||'');eb.textContent=extStatus==='mounted'?'挂':(extStatus==='broken'?'断':'叶');eb.title=getExternalStatusLabel(extStatus)||'外部';row.appendChild(eb);}
  if(cls==='hidden'){const hb=document.createElement('span');hb.className='level-badge cls-tail hidden';hb.textContent='隐';row.appendChild(hb);row.style.opacity='0.45';}
  if(isStale){const sd=document.createElement('span');sd.className='stale-dot';sd.title='下级文件已更新，摘要可能过期';sd.style.display='inline-block';row.appendChild(sd);}
  row.addEventListener('click',e=>{if(e.target!==toggle||toggle.classList.contains('leaf'))selectFile(node.path);});
  row.addEventListener('contextmenu',e=>{e.preventDefault();showCtxMenu(e.pageX,e.pageY,node.path);});
  const kc=document.createElement('div');kc.className='tree-children';
  if(hasKids){toggle.addEventListener('click',e=>{e.stopPropagation();toggle.classList.toggle('expanded');kc.classList.toggle('collapsed');});node.children.forEach(c=>renderRefNode(kc,c,depth+1));}
  wrapper.appendChild(row);wrapper.appendChild(kc);container.appendChild(wrapper);
}

function isExcluded(path){
  const s=getSettings();
  const norm=path.replace(/\\/g,'/');
  for(const d of s.excludedDirs){
    const dn=d.replace(/\\/g,'/');
    if(norm===dn||norm.startsWith(dn))return true;
    const tails=norm.split('/');
    for(let i=1;i<tails.length;i++){const tail=tails.slice(i).join('/')+'/';if(tail===dn||tail.startsWith(dn))return true;}
  }
  return false;
}

// ── Directory grouping ──
function addDirGroups(nodes, depth){
  depth=depth||0;
  for(const node of nodes){
    if(!node.children||node.children.length===0)continue;
    if(node.isGroup){for(const c of node.children)if(!c.isGroup)addDirGroups([c],depth+1);continue;}
    const groups={},ungrouped=[];
    const here=parentDir(node.path);
    for(const child of node.children){
      const dir=parentDir(child.path);
      if(dir&&dir!==here){if(!groups[dir])groups[dir]=[];groups[dir].push(child);}
      else ungrouped.push(child);
    }
    const nc=[];
    for(const[dir,children]of Object.entries(groups)){
      const name=dir.slice(0,-1).split('/').pop();
      const gn={path:'__dir_'+dir,children:children,isGroup:true,groupLabel:'📁 '+name+'/'};
      addDirGroups([gn],depth+1);nc.push(gn);
    }
    nc.push(...ungrouped);node.children=nc;
    for(const c of nc)if(!c.isGroup)addDirGroups([c],depth+1);
    if(depth===0)mergeSuperGroups(node);
  }
  return nodes;
}
function mergeSuperGroups(node){
  const groups=node.children.filter(c=>c.isGroup);
  if(groups.length<2)return;
  const superGroups={},remaining=[];
  for(const g of groups){
    const dir=g.path.replace('__dir_','');
    const i=dir.indexOf('/');
    if(i>0){const top=dir.slice(0,i+1);if(!superGroups[top])superGroups[top]=[];superGroups[top].push(g);}
    else{remaining.push(g);}
  }
  if(Object.keys(superGroups).length===0)return;
  const nc=node.children.filter(c=>!c.isGroup);
  for(const[top,children]of Object.entries(superGroups)){nc.push({path:'__dir_'+top,children:children,isGroup:true,groupLabel:'📁 '+top.slice(0,-1)+'/'});}
  nc.push(...remaining);node.children=nc;
}

function wrapExternalRoots(roots){
  const graphNodes={};
  if(S.graphData)for(const n of S.graphData.nodes)graphNodes[n.id]=n;
  const extNodes=[],others=[];
  for(const r of roots){
    if(r.children&&r.children.length>0){others.push(r);continue;}
    if(isExcluded(r.path))continue;
    const gn=graphNodes[r.path];
    if(gn&&gn.is_external&&gn.mounted){extNodes.push(r);}
    else others.push(r);
  }
  if(!extNodes.length)return roots;
  const paths=extNodes.map(n=>n.path.replace(/\\/g,'/').split('/'));
  let commonLen=0;
  outer:for(let i=0;i<paths[0].length;i++){const seg=paths[0][i];for(let j=1;j<paths.length;j++){if(paths[j][i]!==seg)break outer;}commonLen++;}
  const keepFrom=Math.max(0,commonLen-1);
  const dirTree={};
  for(const n of extNodes){const parts=n.path.replace(/\\/g,'/').split('/').slice(keepFrom);let t=dirTree;for(let i=0;i<parts.length-1;i++){if(!t[parts[i]])t[parts[i]]={};t=t[parts[i]];}t[parts[parts.length-1]]=n;}
  function toGroups(obj){const result=[],fd=[];for(const[k,v]of Object.entries(obj)){if(v.path&&typeof v.path==='string')fd.push(v);else{const kids=toGroups(v);result.push({path:'__extdir_'+k,children:kids,isGroup:true,groupLabel:'📁 '+k+'/'});}}result.push(...fd);return result;}
  const kids=toGroups(dirTree);
  const rootGroup={path:'__extroot__',children:kids,isGroup:true,groupLabel:'📁 外部/'};
  return [rootGroup,...others];
}

// ── Context menu ──
let _ctxMenu=null;
function initCtxMenu(){
  if(_ctxMenu)return;
  _ctxMenu=document.createElement('div');_ctxMenu.id='ctx-menu';_ctxMenu.className='ctx-menu';
  _ctxMenu.innerHTML='<div class="ctx-item" data-action="hide">🔇 隐藏此文件</div><div class="ctx-item" data-action="unhide">🔊 取消隐藏</div><div class="ctx-sep"></div><div class="ctx-item" data-action="rename">✏ 重命名</div><div class="ctx-item ctx-danger" data-action="remove">🗑 移除此文件</div><div class="ctx-item" data-action="restore">↩ 恢复此文件</div><div class="ctx-sep ctx-batch-sep" style="display:none"></div><div class="ctx-item ctx-batch" data-action="batch-hide" style="display:none">🔇 隐藏已选</div><div class="ctx-item ctx-batch" data-action="batch-unhide" style="display:none">🔊 取消隐藏已选</div><div class="ctx-item ctx-danger ctx-batch" data-action="batch-remove" style="display:none">🗑 移除已选</div><div class="ctx-item ctx-batch" data-action="batch-restore" style="display:none">↩ 恢复已选</div>';
  _ctxMenu.addEventListener('click',e=>{const act=e.target.closest('.ctx-item')?.dataset.action;const p=_ctxMenu._filePath;if(!act||!p)return;hideCtxMenu();
    if(act==='hide'){setClassification(p,'hidden');}
    else if(act==='unhide'){setClassification(p,'default');}
    else if(act==='rename'){showRenameDialog(p);}
    else if(act==='remove'){removeFileFromMindx(p);}
    else if(act==='restore'){restoreFileToMindx(p);}
    else if(act==='batch-hide'){batchAction('hide');}
    else if(act==='batch-remove'){batchAction('remove');}
    else if(act==='batch-unhide'){batchAction('unhide');}
    else if(act==='batch-restore'){batchAction('restore');}
    renderAll();});
  document.body.appendChild(_ctxMenu);
  document.addEventListener('click',hideCtxMenu);
}
function showCtxMenu(x,y,filePath){
  initCtxMenu();_ctxMenu._filePath=filePath;
  const isHid=getClassification(filePath)==='hidden';
  const s=getSettings();const isExcl=s.excludedDirs.includes(filePath);
  const batch=S.selectMode&&S.selectedFiles.size>1;
  _ctxMenu.querySelector('[data-action="hide"]').style.display=(isHid||batch)?'none':'';
  _ctxMenu.querySelector('[data-action="unhide"]').style.display=(!isHid||batch)?'none':'';
  _ctxMenu.querySelector('[data-action="remove"]').style.display=(isExcl||batch)?'none':'';
  _ctxMenu.querySelector('[data-action="restore"]').style.display=(!isExcl||batch)?'none':'';
  _ctxMenu.querySelector('.ctx-batch-sep').style.display=batch?'':'none';
  _ctxMenu.querySelectorAll('.ctx-batch').forEach(el=>el.style.display=batch?'':'none');
  _ctxMenu.style.left=x+'px';_ctxMenu.style.top=y+'px';_ctxMenu.classList.add('show');
}
function hideCtxMenu(){if(_ctxMenu)_ctxMenu.classList.remove('show');}
async function showRenameDialog(path){
  hideCtxMenu();
  const oldName=baseName(path);
  const newName=prompt('重命名文件：\n\n当前：'+oldName+'\n\n输入新文件名（同目录）：',oldName);
  if(!newName||newName===oldName)return;
  // Preview changes
  try{
    const r=await fetch('/api/file/rename-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path,new_name:newName})});
    const d=await r.json();
    if(!d.success){alert(d.error||'预览失败');return;}
    if(d.changes.length===0){alert('没有文件引用此文件，可以直接重命名。请在文件管理器中操作。');return;}
    // Show preview modal
    let html='<p>将 <strong>'+oldName+'</strong> 重命名为 <strong>'+d.new_path.split('/').pop()+'</strong></p>';
    html+='<p style="color:var(--yellow)">将修改以下文件中的引用：</p><ul>';
    for(const c of d.changes){
      html+='<li><strong>'+baseName(c.file)+'</strong><ul>';
      for(const lc of c.changes){
        html+='<li><code>'+lc.old_link+'</code> → <code>'+lc.new_link+'</code> <span style="color:var(--text-dim)">'+lc.context+'</span></li>';
      }
      html+='</ul></li>';
    }
    html+='</ul>';
    showModal('✏ 重命名预览',html,[
      {label:'取消',cls:'btn',action:()=>hideModal()},
      {label:'确认重命名',cls:'btn-primary',action:async()=>{
        hideModal();
        const r2=await fetch('/api/file/rename-execute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path,new_path:d.new_path})});
        const d2=await r2.json();
        if(d2.success){
          showToast('已重命名：'+oldName+' → '+d2.new_path.split('/').pop());
          fetchFiles();fetchGraph().then(()=>{renderAll();});
        }else{alert('重命名失败：'+(d2.error||'未知错误'));}
      }}
    ]);
  }catch(e){alert('预览失败：'+e.message);}
}
function removeFileFromMindx(path){
  if(!confirm('确定将此文件从 mindx 管理中移除？\n\n'+path+'\n\n移除后可在项目设置 → 排除目录中恢复。'))return;
  const s=getSettings();if(!s.excludedDirs.includes(path)){s.excludedDirs.push(path);saveSettings(s);}
}
function restoreFileToMindx(path){const s=getSettings();const idx=s.excludedDirs.indexOf(path);if(idx>=0){s.excludedDirs.splice(idx,1);saveSettings(s);}}
function batchAction(type){
  const n=S.selectedFiles.size;
  if(type==='hide'){for(const p of S.selectedFiles)setClassification(p,'hidden');}
  else if(type==='unhide'){for(const p of S.selectedFiles)setClassification(p,'default');}
  else if(type==='remove'){if(!confirm('确定移除已选的 '+n+' 个文件？'))return;const s=getSettings();for(const p of S.selectedFiles){if(!s.excludedDirs.includes(p))s.excludedDirs.push(p);}saveSettings(s);}
  else if(type==='restore'){const s=getSettings();for(const p of S.selectedFiles){const i=s.excludedDirs.indexOf(p);if(i>=0)s.excludedDirs.splice(i,1);}saveSettings(s);}
  S.selectedFiles.clear();S.selectMode=false;updateSelectUI();
}

// ── Batch select ──
function toggleSelectMode(){S.selectMode=!S.selectMode;S.selectedFiles.clear();updateSelectUI();if(!S.selectMode)cleanupDragSelect();else initDragSelect();renderFileTree();}
function updateSelectUI(){const btn=document.getElementById('btn-tree-select');const bar=document.getElementById('batch-bar');if(S.selectMode){btn.classList.add('active');bar.style.display='flex';}else{btn.classList.remove('active');bar.style.display='none';}updateBatchCount();}
function updateBatchCount(){document.getElementById('batch-count').textContent='已选 '+S.selectedFiles.size+' 个文件';}
function toggleFileSelect(path){if(S.selectedFiles.has(path))S.selectedFiles.delete(path);else S.selectedFiles.add(path);updateBatchCount();const cb=document.querySelector('.tree-cb[data-path="'+CSS.escape(path)+'"]');if(cb)cb.checked=S.selectedFiles.has(path);}
function batchHideSelected(){for(const p of S.selectedFiles)setClassification(p,'hidden');S.selectedFiles.clear();S.selectMode=false;updateSelectUI();renderAll();}
function batchCancel(){S.selectedFiles.clear();S.selectMode=false;updateSelectUI();renderFileTree();}

let _dragBox=null,_dragStart=null,_dragMouseMove=null,_dragMouseUp=null;
function cleanupDragSelect(){if(_dragMouseMove){document.removeEventListener('mousemove',_dragMouseMove);_dragMouseMove=null;}if(_dragMouseUp){document.removeEventListener('mouseup',_dragMouseUp);_dragMouseUp=null;}}
function initDragSelect(){
  if(_dragBox)return;
  _dragBox=document.createElement('div');_dragBox.id='drag-box';_dragBox.className='drag-box';document.body.appendChild(_dragBox);
  const tree=document.getElementById('file-tree');
  tree.addEventListener('mousedown',e=>{if(!S.selectMode||e.button!==0)return;if(e.target.closest('.tree-toggle')||e.target.closest('.tree-cb'))return;_dragStart={x:e.clientX,y:e.clientY};_dragBox.style.display='none';e.preventDefault();});
  _dragMouseMove=e=>{if(!_dragStart||!S.selectMode)return;const x1=Math.min(_dragStart.x,e.clientX),y1=Math.min(_dragStart.y,e.clientY),x2=Math.max(_dragStart.x,e.clientX),y2=Math.max(_dragStart.y,e.clientY);if(x2-x1<5&&y2-y1<5)return;_dragBox.style.cssText=`display:block;left:${x1}px;top:${y1}px;width:${x2-x1}px;height:${y2-y1}px`;};
  _dragMouseUp=e=>{if(!_dragStart)return;_dragBox.style.display='none';const x1=Math.min(_dragStart.x,e.clientX),y1=Math.min(_dragStart.y,e.clientY),x2=Math.max(_dragStart.x,e.clientX),y2=Math.max(_dragStart.y,e.clientY);const w=x2-x1,h=y2-y1;_dragStart=null;if(w<5&&h<5)return;const items=document.querySelectorAll('#file-tree .tree-item');for(const item of items){if(!item.dataset.path||item.classList.contains('group-node'))continue;const r=item.getBoundingClientRect();if(r.right>x1&&r.left<x2&&r.bottom>y1&&r.top<y2)S.selectedFiles.add(item.dataset.path);}updateBatchCount();renderFileTree();};
  document.addEventListener('mousemove',_dragMouseMove);
  document.addEventListener('mouseup',_dragMouseUp);
}

// ── Settings ──
let _settingsCache=null;
async function loadSettings(){
  try{const r=await fetch('/api/settings/load');const data=await r.json();_settingsCache={file_classes:data.file_classes||{},excludedDirs:data.excluded_dirs||[],displayMode:data.display_mode||'full',refRoots:data.ref_roots||[],activeRoot:data.active_root||null};lsSet('settings',_settingsCache);return _settingsCache;}catch(e){return lsGet('settings')||{displayMode:'full',refRoots:[],activeRoot:null,excludedDirs:[],file_classes:{}};}
}
function saveSettings(s){
  _settingsCache=s;lsSet('settings',s);
  fetch('/api/settings/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file_classes:s.file_classes,excluded_dirs:s.excludedDirs,display_mode:s.displayMode,ref_roots:s.refRoots,active_root:s.activeRoot})}).catch(()=>{});
}
function getSettings(){return _settingsCache||lsGet('settings')||{displayMode:'full',refRoots:[],activeRoot:null,excludedDirs:[],file_classes:{}};}
function computeReachable(rootPath){const visited=new Set();if(!rootPath||!S.graphData)return visited;const queue=[rootPath];while(queue.length){const cur=queue.shift();if(visited.has(cur))continue;visited.add(cur);for(const e of S.graphData.edges||[]){if(e.from===cur&&!visited.has(e.to))queue.push(e.to);}}S.reachableSet=visited;return visited;}
function showSettings(){
  const s=getSettings();
  document.getElementById(s.displayMode==='ref'?'set-mode-ref':'set-mode-full').checked=true;
  document.getElementById('setting-roots').style.display=s.displayMode==='ref'?'':'none';
  renderSettingRoots();renderSettingExcludes();renderSettingExternals();
  document.getElementById('modal-settings').style.display='flex';
}
function hideSettings(){document.getElementById('modal-settings').style.display='none';}
function renderSettingRoots(){
  const s=getSettings();const list=document.getElementById('setting-root-list');list.innerHTML='';
  if(!s.refRoots.length){list.innerHTML='<div style="color:var(--text-dim);font-size:11px;padding:4px 0">暂无根文件</div>';return;}
  for(const r of s.refRoots){const row=document.createElement('div');row.className='setting-item';const isActive=r===s.activeRoot;row.innerHTML=`<input type="radio" name="activeRoot" value="${r}" ${isActive?'checked':''}> <span class="set-root-path">${r}</span><button class="btn btn-xs set-root-del" data-path="${r}">&times;</button>`;row.querySelector('input[type=radio]').addEventListener('change',()=>{s.activeRoot=r;saveSettings(s);applySettings();});row.querySelector('.set-root-del').addEventListener('click',()=>{const idx=s.refRoots.indexOf(r);if(idx>=0)s.refRoots.splice(idx,1);if(s.activeRoot===r)s.activeRoot=s.refRoots[0]||null;saveSettings(s);renderSettingRoots();applySettings();});list.appendChild(row);}
}
function renderSettingExcludes(){
  const s=getSettings();const list=document.getElementById('setting-exclude-list');list.innerHTML='';
  if(!s.excludedDirs.length){list.innerHTML='<div style="color:var(--text-dim);font-size:11px;padding:4px 0">无排除目录</div>';return;}
  for(const d of s.excludedDirs){const row=document.createElement('div');row.className='setting-item';row.innerHTML=`<span class="set-exclude-path">📁 ${d}</span><button class="btn btn-xs set-exclude-del" data-dir="${d}">&times;</button>`;row.querySelector('.set-exclude-del').addEventListener('click',()=>{const idx=s.excludedDirs.indexOf(d);if(idx>=0)s.excludedDirs.splice(idx,1);saveSettings(s);renderSettingExcludes();});list.appendChild(row);}
}
function addRootFile(){
  const s=getSettings();const files=S.files.map(f=>f.path).sort();const msg='输入引用根文件路径（相对于项目根）：\n\n可用文件：\n'+files.slice(0,30).join('\n')+(files.length>30?'\n...还有 '+(files.length-30)+' 个文件':'');const path=prompt(msg,s.refRoots[0]||'MEMORY.md');if(!path||!path.trim())return;const p=path.trim();if(!S.files.some(f=>f.path===p)){alert('文件不存在：'+p);return;}if(s.refRoots.includes(p)){alert('该根文件已存在');return;}s.refRoots.push(p);if(!s.activeRoot)s.activeRoot=p;saveSettings(s);renderSettingRoots();applySettings();}
function addExcludeDir(){
  const input=document.getElementById('input-exclude-dir');const dir=input.value.trim();if(!dir)return;const s=getSettings();const isFile=dir.includes('.')&&!dir.endsWith('/');const normalized=isFile?dir:(dir.endsWith('/')?dir:dir+'/');if(s.excludedDirs.includes(normalized)){alert('该路径已在排除列表中');return;}s.excludedDirs.push(normalized);saveSettings(s);renderSettingExcludes();input.value='';}
async function pickFolder(){const r=await fetch('/api/pick-folder',{method:'POST'});const d=await r.json();return d.path;}
async function pickFile(){const r=await fetch('/api/pick-file',{method:'POST'});const d=await r.json();return d.path;}
async function pickExcludeFolder(){const path=await pickFolder();if(!path)return;document.getElementById('input-exclude-dir').value=path.replace(/\\/g,'/')+'/';}
async function fetchExternals(){const r=await fetch('/api/external/list');return r.json();}
function renderSettingExternals(){
  const list=document.getElementById('setting-external-list');list.innerHTML='<div style="color:var(--text-dim);font-size:11px;padding:4px 0">加载中...</div>';
  fetchExternals().then(exts=>{const s=getSettings();exts=exts.filter(e=>!s.excludedDirs.some(d=>e.path===d||e.path.startsWith(d)));list.innerHTML='';if(!exts.length){list.innerHTML='<div style="color:var(--text-dim);font-size:11px;padding:4px 0">无外部文件</div>';return;}for(const e of exts){const row=document.createElement('div');row.className='setting-item';row.innerHTML=`<span class="set-external-path">${e.exists?'📄':'❌'} ${e.label||e.path}</span><span style="font-size:9px;color:var(--text-dim);overflow:hidden;text-overflow:ellipsis;flex:1">${e.path}</span><button class="btn btn-xs set-root-del" data-ext="${e.path}">&times;</button>`;row.querySelector('.set-root-del').addEventListener('click',async()=>{await fetch('/api/external/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:e.path})});renderSettingExternals();fetchGraph().then(()=>renderAll());});list.appendChild(row);}}).catch(()=>{list.innerHTML='<div style="color:var(--text-dim);font-size:11px;padding:4px 0">加载失败</div>';});
}
async function addExternal(){const input=document.getElementById('input-external-path');const path=input.value.trim();if(!path){alert('请输入路径或使用文件管理器选择');return;}const r=await fetch('/api/external/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path})});const d=await r.json();if(d.success){input.value='';renderSettingExternals();fetchGraph().then(()=>renderAll());}else{alert('添加失败：'+(d.error||'未知错误'));}}
async function pickExternalFile(){const path=await pickFile();if(path)document.getElementById('input-external-path').value=path;}
async function pickExternalFolder(){const path=await pickFolder();if(path)document.getElementById('input-external-path').value=path;}
function applySettings(){const s=getSettings();if(s.displayMode==='ref'&&s.activeRoot){computeReachable(s.activeRoot);}else{S.reachableSet=new Set();}computeStaleMap();renderAll();}

// ── Memory tree graphs ──
function renderRefTreeGraph(){const container=document.getElementById('ref-tree-container');if(!S.files.length||!S.graphData)return;renderMemoryRefTree(container);}
function renderDirTreeGraph(){const container=document.getElementById('dir-tree-container');if(!S.files.length)return;renderMemoryDirTree(container);}
function renderAll(){renderFileTree();renderRefTreeGraph();renderDirTreeGraph();renderDepGraph();}

function computeRefLevels(graphData, visiblePaths) {
  const gEdges = [];
  const normCache = {};
  for (const e of (graphData.edges || [])) {
    if (!visiblePaths.has(e.from)) continue;
    let target = e.to;
    if (!visiblePaths.has(target)) {
      // Try to resolve absolute path to relative
      if (!normCache[target]) {
        const absNorm = target.replace(/\\/g, '/');
        for (const vp of visiblePaths) {
          const relNorm = vp.replace(/\\/g, '/');
          if (absNorm.endsWith('/' + relNorm) || absNorm === relNorm) {
            normCache[target] = vp;
            break;
          }
        }
      }
      target = normCache[target];
    }
    if (target && visiblePaths.has(target) && e.from !== target) {
      gEdges.push({from: e.from, to: target});
    }
  }
  const indegree = {};
  const origIndegree = {};
  const adj = {};
  for (const p of visiblePaths) { indegree[p] = 0; adj[p] = []; }
  for (const e of gEdges) {
    adj[e.from] = (adj[e.from] || []); adj[e.from].push(e.to);
    indegree[e.to] = (indegree[e.to] || 0) + 1;
  }
  for (const [n, d] of Object.entries(indegree)) { origIndegree[n] = d; }
  const levels = {};
  const bestLevel = {}; // track max level for cycle nodes
  let queue = [];
  for (const [n, d] of Object.entries(indegree)) {
    // Isolated nodes (no incoming AND no outgoing) get -1, not queued
    if (d === 0 && (!adj[n] || adj[n].length === 0)) {
      levels[n] = -1;
    } else if (d === 0) {
      queue.push(n);
      levels[n] = 0;
    }
  }
  while (queue.length) {
    const next = [];
    for (const n of queue) {
      for (const child of (adj[n] || [])) {
        if (!(child in levels)) {
          indegree[child]--;
          bestLevel[child] = Math.max(bestLevel[child] || 0, (levels[n] || 0) + 1);
          if (indegree[child] === 0) {
            levels[child] = bestLevel[child];
            next.push(child);
          }
        }
      }
    }
    queue = next;
  }
  for (const p of visiblePaths) {
    if (!(p in levels)) {
      // Cycle nodes (had incoming edges): use bestLevel if available, else 0
      // Truly isolated nodes (no edges at all): -1
      levels[p] = bestLevel[p] !== undefined ? bestLevel[p] : (origIndegree[p] > 0 ? 0 : -1);
    }
  }
  return levels;
}

function renderMemoryRefTree(container){
  const nodes=[],edges=[],nodeIds=new Set();
  const visiblePaths=new Set(getDisplayFiles().filter(f=>isVisibleInGraph(f.path)).map(f=>f.path));
  // Ref tree graph: exclude external files without reference relationships
  for (const p of visiblePaths) {
    if (isExternalFile(p) && S.graphData) {
      const hasEdges = (S.graphData.edges || []).some(e => e.from === p || e.to === p);
      if (!hasEdges) visiblePaths.delete(p);
    }
  }
  if(!visiblePaths.size)return;
  
  // Compute DAG levels (longest reference path, isolated=-1)
  const dagLevels=computeRefLevels(S.graphData,visiblePaths);
  // Shift levels so min=0 (vis-network handles non-negative better)
  const minLevel=Math.min(0,...Object.values(dagLevels));
  const shift=-minLevel;
  
  // Create nodes with tree depth as hierarchical level
  for(const f of getDisplayFiles()){
    if(!visiblePaths.has(f.path))continue;
    const d=(dagLevels[f.path]??0)+shift;
    const isExt=isExternalFile(f.path);
    const nodeObj={
      id:f.path,label:baseName(f.path),
      color:{background:getNodeColor(f.type,f.path),border:getNodeBorderColor(),highlight:{background:getNodeColor(f.type,f.path),border:'#fff'}},
      font:{color:getFontColor(),size:10,face:'monospace'},
      shape:'box',margin:5,
      title:f.path+'\n'+getFtypeLabel(f.type)+(getExternalStatus(f.path)?'\n'+getExternalStatusLabel(getExternalStatus(f.path)):''),
      level:d
    };
    if(isExt){nodeObj.shapeProperties={borderDashes:[5,5]};nodeObj.borderWidth=2;}
    nodes.push(nodeObj);
    nodeIds.add(f.path);
  }
  
  // Use ALL graph edges (covers tree edges + cross-references), skip self-loops
  const edgeData=(S.graphData.edges||[]).filter(e=>visiblePaths.has(e.from)&&visiblePaths.has(e.to)&&e.from!==e.to);
  const edgeSet=new Set(edgeData.map(e=>e.from+'|||'+e.to));
  const seenBi=new Set();
  for(const e of edgeData){
    const isBi=edgeSet.has(e.to+'|||'+e.from);
    if(isBi){
      const key=[e.from,e.to].sort().join('|||');
      if(seenBi.has(key)) continue;
      seenBi.add(key);
    }
    edges.push({
      from:e.from,to:e.to,
      arrows:isBi?'to,from':'to',
      color:{color:'#3a3d4e',highlight:'#58a6ff'},
      width:1,smooth:false
    });
  }
  
  // Sort nodes by (level, name) for consistent level-internal ordering
  nodes.sort((a,b)=>a.level-b.level||a.label.localeCompare(b.label));

  // Manual positioning by DAG level
  const levelNodes={};
  for(const n of nodes){const lv=n.level;if(!levelNodes[lv])levelNodes[lv]=[];levelNodes[lv].push(n);}
  for(const lv of Object.keys(levelNodes)){levelNodes[lv].sort((a,b)=>a.label.localeCompare(b.label));}
  const X_GAP=120,Y_GAP=180;
  const allLevels=Object.keys(levelNodes).map(Number).sort((a,b)=>a-b);
  const minLv=allLevels[0],maxLv=allLevels[allLevels.length-1];
  const totalLevels=maxLv-minLv+1;
  const Y_TOP=-(totalLevels-1)*Y_GAP/2;
  for(const lv of allLevels){
    const arr=levelNodes[lv];
    const y=Y_TOP+(lv-minLv)*Y_GAP;
    const totalW=(arr.length-1)*X_GAP;
    let x=-totalW/2;
    for(const n of arr){n.x=x;n.y=y;x+=X_GAP;}
  }

  if(!nodes.length)return;
  // Merge saved positions into node data BEFORE creating DataSet
  const savedPos=lsGet('reftree_positions');
  if(savedPos){for(const n of nodes){if(savedPos[n.id]){n.x=savedPos[n.id].x;n.y=savedPos[n.id].y;}}}
  const data={nodes:new vis.DataSet(nodes),edges:new vis.DataSet(edges)};
  const opts={
    layout:{improvedLayout:false,randomSeed:42},
    physics:{enabled:false},
    edges:{arrows:{to:{enabled:true},from:{enabled:true}}},
    interaction:{dragNodes:true,hover:true,navigationButtons:true,keyboard:true}
  };
  if(S.netRefTree)S.netRefTree.destroy();
  S.netRefTree=new vis.Network(container,data,opts);
  S.netRefTree.on('dragEnd',()=>{saveRefTreePositions();});
  S.netRefTree.on('click',params=>{if(params.nodes.length>0){const id=params.nodes[0];if(id!=='__ROOT__'&&!id.endsWith('/'))selectFile(id);highlightInTree(id);}});
}
function savePosition(key,net){
  if(!net)return;
  const pos=net.getPositions();
  fetch('/api/positions/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:key,positions:pos})}).catch(()=>{});
}
function saveRefTreePositions(){savePosition('reftree_positions',S.netRefTree);}
function saveDirTreePositions(){savePosition('dirtree_positions',S.netDirTree);}
function saveDepPositions(){savePosition('dep_positions',S.netDepGraph);}

function renderMemoryDirTree(container){
  const nodes=[],edges=[],nodeIds=new Set();
  const visible=getDisplayFiles().filter(f=>isVisibleInGraph(f.path));
  if(!visible.length)return;
  const dirMap={};
  function ensureDir(p){if(!dirMap[p]){const nm=p.slice(0,-1).split('/').pop();dirMap[p]={name:nm,subdirs:new Set(),files:[]};}}
  for(const f of visible){const d=parentDir(f.path);if(d){ensureDir(d);dirMap[d].files.push(f);}let p=d;while(p){p=parentDir(p.slice(0,-1));if(p){ensureDir(p);dirMap[p].subdirs.add(d);break;}}}
  const rootFiles=visible.filter(f=>!parentDir(f.path));
  function countLeaves(dir){let n=dirMap[dir].files.length;for(const sd of dirMap[dir].subdirs)n+=countLeaves(sd);dirMap[dir]._total=n;return n;}
  const topDirs=Object.keys(dirMap).filter(d=>!Object.keys(dirMap).some(o=>o!==d&&d.startsWith(o)));
  const totalLeaves=rootFiles.length+topDirs.reduce((s,d)=>s+countLeaves(d),0);
  const Y_DIR=110,Y_FILE=80,X_UNIT=100,X_MIN=60;
  const projName=S.activeProject?S.activeProject.name:'project';
  function layoutDir(dir,x,w,depth){const info=dirMap[dir];if(!info)return;const cx=x+w/2,cy=(depth+1)*Y_DIR;nodes.push({id:dir,label:info.name+'/',color:{background:getDirBgColor(),border:getDirBorderColor()},font:{color:getFontColor(),size:11,face:'monospace'},shape:'box',margin:6,x:cx,y:cy});nodeIds.add(dir);const subDirList=[...info.subdirs];if(subDirList.length){const pad=w*0.05,avail=w-pad*2;let sx=x+pad;for(const sd of subDirList){const si=dirMap[sd];if(!si)continue;const sw=Math.max(X_MIN,avail*(si._total/info._total));layoutDir(sd,sx,sw,depth+1);edges.push({from:dir,to:sd,arrows:'to',color:{color:'#252b36'},width:1});sx+=sw;}}if(info.files.length){const fy=cy+Y_DIR*0.55,tw=info.files.length*X_UNIT;let fx=cx-tw/2+X_UNIT/2;for(const f of info.files){nodes.push({id:f.path,label:baseName(f.path),color:{background:getNodeColor(f.type,f.path),border:getNodeBorderColor()},font:{color:getFontColor(),size:10,face:'monospace'},shape:'box',margin:5,x:fx,y:fy});nodeIds.add(f.path);edges.push({from:dir,to:f.path,arrows:'to',color:{color:'#2a3040'},width:1});fx+=X_UNIT;}}}
  nodes.push({id:'__ROOT__',label:projName,color:{background:getRootBgColor(),border:getRootBorderColor()},font:{color:getFontColor(),size:13,face:'monospace',bold:true},shape:'box',margin:8,x:0,y:0});nodeIds.add('__ROOT__');
  const totW=Math.max(totalLeaves*X_UNIT,800);let dx=-totW/2;for(const d of topDirs){const sw=Math.max(X_MIN,totW*(dirMap[d]._total/totalLeaves));layoutDir(d,dx,sw,0);edges.push({from:'__ROOT__',to:d,arrows:'to',color:{color:'#252b36'},width:1});dx+=sw;}
  if(rootFiles.length){const fy=Y_DIR*0.55;let fx=-totW/2+X_UNIT/2;for(const f of rootFiles){nodes.push({id:f.path,label:baseName(f.path),color:{background:getNodeColor(f.type,f.path),border:getNodeBorderColor()},font:{color:getFontColor(),size:10,face:'monospace'},shape:'box',margin:5,x:fx,y:fy});nodeIds.add(f.path);edges.push({from:'__ROOT__',to:f.path,arrows:'to',color:{color:'#2a3040'},width:1});fx+=X_UNIT;}}
  const data={nodes:new vis.DataSet(nodes),edges:new vis.DataSet(edges)};const opts={physics:{enabled:false},interaction:{dragNodes:false,hover:true,navigationButtons:true,keyboard:true},edges:{smooth:false}};
  if(S.netDirTree)S.netDirTree.destroy();S.netDirTree=new vis.Network(container,data,opts);
  setTimeout(()=>{if(S.netDirTree)S.netDirTree.fit({animation:{duration:300}});},500);
  S.netDirTree.on('click',params=>{if(params.nodes.length>0){const id=params.nodes[0];if(id!=='__ROOT__'&&!id.endsWith('/'))selectFile(id);highlightInTree(id);}});
}

// ── Dependency graph ──
function renderDepGraph(){
  if(!S.graphData)return;const container=document.getElementById('dep-graph-container');
  const visiblePaths=new Set(getDisplayFiles().filter(f=>isVisibleInGraph(f.path)).map(f=>f.path));
  const gNodes=S.graphData.nodes.filter(n=>visiblePaths.has(n.id));
  let gEdges=S.graphData.edges.filter(e=>visiblePaths.has(e.from)&&visiblePaths.has(e.to)&&e.from!==e.to);
  const CLS=['base','standalone'];const clsCount={base:0,standalone:0},clsIndex={};
  for(const n of gNodes){const cls=getClassification(n.id);if(cls in clsCount){clsIndex[n.id]=clsCount[cls];clsCount[cls]++;}}
  const X_GAP=150,Y_TOP=-350,Y_GAP=120;
  const nodesArr=gNodes.map(n=>{const status=getExternalStatus(n.id);const base={id:n.id,label:baseName(n.id),title:(n.title||n.id)+(status?'\n'+getExternalStatusLabel(status):''),color:{background:getNodeColor(n.group,n.id),border:getNodeBorderColor(),highlight:{background:getNodeColor(n.group,n.id),border:'#fff'}},font:{color:getFontColor(),size:11,face:'monospace'},shape:'box',margin:5};const cls=getClassification(n.id);if(cls in clsCount){const idx=CLS.indexOf(cls);base.x=(clsIndex[n.id]-(clsCount[cls]-1)/2)*X_GAP;base.y=Y_TOP+idx*Y_GAP;}if(n.is_external){base.shapeProperties={borderDashes:[5,5]};base.borderWidth=2;}return base;});
  const nodes=new vis.DataSet(nodesArr);const edgeSet=new Set(gEdges.map(e=>e.from+'|||'+e.to));
  const edgesArr=[];const seenBiDep=new Set();
  for(const e of gEdges){
    const isBi=edgeSet.has(e.to+'|||'+e.from);
    if(isBi){
      const key=[e.from,e.to].sort().join('|||');
      if(seenBiDep.has(key)) continue;
      seenBiDep.add(key);
    }
    const edgeObj={from:e.from,to:e.to,label:e.label,title:e.title,arrows:isBi?'to,from':'to',color:{color:'#3a3d4e',highlight:'#58a6ff'},font:{color:getFontColor(),size:9,align:'middle'},width:1,smooth:{type:'continuous',roundness:0.3}};if(e.is_external){edgeObj.dashes=true;edgeObj.color={color:'#6e7681',highlight:'#d29922'};}edgesArr.push(edgeObj);
  }
  const edges=new vis.DataSet(edgesArr);
  const savedPos=lsGet('dep_positions');
  const opts={physics:{solver:'forceAtlas2Based',forceAtlas2Based:{gravitationalConstant:-40,centralGravity:0.005,springLength:150,springConstant:0.08},stabilization:{iterations:200}},layout:{improvedLayout:true,randomSeed:42},edges:{arrows:{to:{enabled:true},from:{enabled:true}}},interaction:{hover:true,navigationButtons:true,keyboard:true}};
  if(S.netDepGraph)S.netDepGraph.destroy();S.netDepGraph=new vis.Network(container,{nodes,edges},opts);
  if(savedPos){try{for(const n of nodesArr){if(savedPos[n.id])nodes.update({id:n.id,x:savedPos[n.id].x,y:savedPos[n.id].y});}}catch(e){}}
  let stabilized=false;S.netDepGraph.on('stabilized',()=>{if(!stabilized){stabilized=true;S.netDepGraph.setOptions({physics:false});saveDepPositions();}});
  S.netDepGraph.on('click',params=>{if(params.nodes.length>0){selectFile(params.nodes[0]);highlightInTree(params.nodes[0]);}});
  S.netDepGraph.on('dragEnd',()=>{saveDepPositions();});
}
  function saveDepPositions(){savePosition('dep_positions',S.netDepGraph);}

// ── File detail ──
function highlightInTree(path){
  document.querySelectorAll('#file-tree .tree-item.selected').forEach(el=>el.classList.remove('selected'));
  const target=document.querySelector('#file-tree .tree-item[data-path="'+CSS.escape(path)+'"]');
  if(target){target.classList.add('selected');target.scrollIntoView({block:'nearest',behavior:'smooth'});}
}
function selectFile(path){S.selectedFile=path;bumpReadCount(path);fetchFileDetail(path).then(d=>renderDetail(d));try{S.netRefTree?.selectNodes([path]);S.netRefTree?.focus(path,{scale:1.2,animation:true});}catch(e){}try{S.netDirTree?.selectNodes([path]);S.netDirTree?.focus(path,{scale:1.2,animation:true});}catch(e){}try{S.netDepGraph?.selectNodes([path]);S.netDepGraph?.focus(path,{scale:1.2,animation:true});}catch(e){}}
async function fetchSilencedBrokenLinks(){const r=await fetch('/api/silenced-links');return r.json();}
async function silenceBrokenLink(target) {
  const r = await fetch('/api/silenced-links/silence', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({target})
  });
  return r.json();
}
async function unsilenceBrokenLink(target) {
  const r = await fetch('/api/silenced-links/unsilence', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({target})
  });
  return r.json();
}
async function fetchFileDetail(path){const [detail,silenced]=await Promise.all([fetch('/api/file/'+encodeURIComponent(path)).then(r=>r.json()),fetchSilencedBrokenLinks().catch(()=>[])]);const node=getGraphNode(path);if(node?.is_external){detail.type=detail.type||node.group||'external';if(detail.exists===undefined&&node.exists!==undefined)detail.exists=node.exists;detail.abs_path=detail.abs_path||node.abs_path||path;detail.external_status=getExternalStatus(path);detail.mounted=!!node.mounted;}detail.silenced_links=silenced||[];return detail;}
async function toggleBrokenLinkSilence(target,silenced){const r=silenced?await unsilenceBrokenLink(target):await silenceBrokenLink(target);if(r.success&&S.selectedFile)fetchFileDetail(S.selectedFile).then(d=>renderDetail(d));}
function escapeHtml(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function renderDetail(data){
  document.getElementById('detail-empty').style.display='none';document.getElementById('detail-content').style.display='block';
  document.getElementById('detail-path').textContent=baseName(data.path);
  document.getElementById('detail-type-badge').textContent=getFtypeLabel(data.type||'');
  let meta='';if(data.exists!==undefined)meta+='<span class="status-tag '+(data.exists?'exists':'missing')+'">'+(data.exists?'存在':'缺失')+'</span>';if(data.external_status)meta+='<span class="status-tag external-status '+data.external_status+'">'+getExternalStatusLabel(data.external_status)+'</span>';if(data.size)meta+='<span>'+Math.round(data.size/1024)+' KB</span>';if(data.last_modified)meta+='<span>'+new Date(data.last_modified).toLocaleString('zh-CN')+'</span>';document.getElementById('detail-meta').innerHTML=meta;
  document.getElementById('detail-fullpath').textContent=data.abs_path||data.path;
  const parents=data.dependencies?.referenced_by||[];const children=data.dependencies?.references||[];
  document.getElementById('detail-parents').innerHTML=parents.length?parents.map(p=>'<div class="ref-link" onclick="selectFile(\''+p.path+'\')">'+baseName(p.path)+' <span class="ref-type">'+p.link_type+'</span></div>').join(''):'<span class="dim">无</span>';
  document.getElementById('detail-children').innerHTML=children.length?children.map(c=>'<div class="ref-link" onclick="selectFile(\''+c.path+'\')">'+baseName(c.path)+' <span class="ref-type">'+c.link_type+'</span></div>').join(''):'<span class="dim">无</span>';
  const silencedLinks=new Set(data.silenced_links||[]);const issues=data.issues||[];document.getElementById('detail-issues-section').style.display=issues.length?'':'none';document.getElementById('detail-issues').innerHTML=issues.map(i=>{const isBroken=(i.type==='broken_link'||i.type==='broken_external_link')&&i.target;const silenced=isBroken&&silencedLinks.has(i.target);const btn=isBroken?' <button class="btn btn-xs silence-btn" data-target="'+escapeHtml(i.target)+'" data-silenced="'+silenced+'" title="'+(silenced?'取消静音':'静音')+'" onclick="event.stopPropagation();toggleBrokenLinkSilence(this.dataset.target,this.dataset.silenced===\'true\')">'+(silenced?'🔇':'🔈')+'</button>':'';return '<div class="issue-item">⚠ '+escapeHtml(i.detail)+btn+'</div>';}).join('');
  document.getElementById('detail-links').innerHTML=data.links&&data.links.length?data.links.map(l=>'<div class="ref-link">['+l.anchor+']('+l.target+') <span class="ref-type">'+l.context+'</span>'+(l.is_external?' <span class="ext-tag">外部</span>':'')+'</div>').join(''):'<span class="dim">无</span>';
  // Update right panel
  document.getElementById('file-info-empty').style.display='none';document.getElementById('file-info-content').style.display='block';
  document.getElementById('fi-name').textContent=baseName(data.path);document.getElementById('fi-path').textContent=data.path;
  document.getElementById('fi-meta').innerHTML=meta;
  document.getElementById('fi-parents-count').textContent='('+parents.length+')';document.getElementById('fi-parents-list').innerHTML=document.getElementById('detail-parents').innerHTML;
  document.getElementById('fi-children-count').textContent='('+children.length+')';document.getElementById('fi-children-list').innerHTML=document.getElementById('detail-children').innerHTML;
  // Highlight current classification button
  const cls=getClassification(data.path);
  document.querySelectorAll('#detail-classify .classify-btn').forEach(b=>b.classList.toggle('active',b.dataset.cls===cls));
}

// ── Feed ──
function addChangeEvent(file,event){const feed=document.getElementById('change-feed');const item=document.createElement('div');item.className='feed-item feed-clickable';item.innerHTML='<span class="feed-time">'+new Date().toLocaleTimeString('zh-CN')+'</span> '+(event==='deleted'?'🗑':'📝')+' '+file;item.addEventListener('click',()=>showFeedDetail('change',file,{event:event,time:new Date().toLocaleString('zh-CN')}));feed.insertBefore(item,feed.firstChild);while(feed.children.length>50)feed.lastChild.remove();}
function addSuggestion(file,data){const feed=document.getElementById('suggestion-feed');const sevClass='sev-'+(data.severity||'info');const item=document.createElement('div');item.className='feed-item feed-clickable';item.innerHTML='<span class="'+sevClass+'">'+data.action+'</span> '+data.target;item.title=data.reason;item.addEventListener('click',()=>showFeedDetail('suggestion',file,data));feed.insertBefore(item,feed.firstChild);while(feed.children.length>20)feed.lastChild.remove();}
function showFeedDetail(type,file,data){let content='';if(type==='change'){content=`<p>文件 <strong>${file}</strong> 发生变化</p><p>事件类型：${data.event}</p><p>时间：${data.time||'?'}</p>`;}else if(type==='suggestion'){content=`<p><strong>${file}</strong> ↔ <strong>${data.target||'?'}</strong></p><p>原因：${data.reason||'?'}</p><p>建议操作：${data.action||'?'}</p>`;}showModal(type==='change'?'📡 事件详情':'💡 建议详情',content,[{label:'确认',cls:'btn-primary',action:()=>{const confirmId='feed_'+type+'_'+file+'_'+(data.event||data.target||'');lsAddConfirmed(confirmId);hideModal();}},{label:'关闭',cls:'btn',action:()=>hideModal()}]);}
function showModal(title,content,buttons){let modal=document.getElementById('mindx-modal');if(!modal){modal=document.createElement('div');modal.id='mindx-modal';modal.className='modal-overlay';modal.innerHTML=`<div class="modal-box"><div class="modal-header"><span class="modal-title"></span><button class="modal-close btn btn-xs">&times;</button></div><div class="modal-body"></div><div class="modal-buttons" style="padding:12px 16px;border-top:1px solid var(--border)"></div></div>`;document.body.appendChild(modal);modal.querySelector('.modal-close').addEventListener('click',hideModal);}modal.querySelector('.modal-title').textContent=title;modal.querySelector('.modal-body').innerHTML=content;const btns=modal.querySelector('.modal-buttons');btns.innerHTML='';for(const b of buttons){const btn=document.createElement('button');btn.className='btn '+(b.cls||'');btn.textContent=b.label;btn.addEventListener('click',b.action);btns.appendChild(btn);}modal.classList.add('active');}
function hideModal(){const m=document.getElementById('mindx-modal');if(m)m.classList.remove('active');}
function showToast(msg){let t=document.getElementById('mindx-toast');if(!t){t=document.createElement('div');t.id='mindx-toast';t.className='toast';document.body.appendChild(t);}t.textContent=msg;t.style.display='block';clearTimeout(t._tid);t._tid=setTimeout(()=>t.style.display='none',2000);}

// ── Socket & API ──
function connectSocket(){
  S.socket=io({transports:['websocket','polling']});
  let _initAllRunning=false;
S.socket.on('connect',()=>{document.getElementById('status-dot').className='status-dot connected';document.getElementById('footer-watching').textContent='👁 监听中';if(_initAllRunning)return;_initAllRunning=true;initAll().finally(()=>{_initAllRunning=false;});});
  S.socket.on('disconnect',()=>{document.getElementById('status-dot').className='status-dot';document.getElementById('footer-watching').textContent='⏳ 断开连接';});
  S.socket.on('file_changed',data=>{addChangeEvent(data.file,data.event);fetchFiles();fetchGraph().then(()=>{const s=getSettings();if(s.displayMode==='ref'&&s.activeRoot)computeReachable(s.activeRoot);renderAll();});});
  S.socket.on('sync_needed',data=>{addSuggestion(data.file,{target:data.target||data.file,reason:data.reason||'',severity:data.severity||'info',action:data.action||''});});
  S.socket.on('project_switched',data=>{handleProjectSwitched(data);});
}
async function api(u){const r=await fetch(u);return r.json();}
async function loadPositionsFallback(){
  try{const r=await fetch('/api/positions/load');const d=await r.json();for(const[k,v]of Object.entries(d)){if(Object.keys(v||{}).length>0)lsSet(k,v);}}catch(e){}
}
async function initAll(){
  await loadProjects();
  await loadSettings();
  try{const st=await api('/api/status');updateStats(st);document.getElementById('footer-path').textContent=st.project_root||'—';document.getElementById('footer-watching').textContent=st.watching?'👁 监听中':'⏸ 暂停';document.getElementById('no-project-state').style.display='none';document.getElementById('app').style.display='flex';}catch(e){}
  await fetchFiles();await fetchGraph();await loadPositionsFallback();renderAll();
}
async function fetchFiles(){S.files=await api('/api/files');computeStaleMap();applyAfterData();}
async function fetchGraph(){S._dagReachable=null;S._externalReachable=null;S.graphData=await api('/api/graph');computeStaleMap();applyAfterData();}
async function toggleHistoryPanel(panelType) {
  const feedId = panelType === 'sync' ? 'suggestion-feed' : 'change-feed';
  const container = document.getElementById(feedId);
  const button = document.querySelector(`.history-toggle[data-panel="${panelType}"]`);
  if (!container || !button) return;

  S.historyMode[panelType] = !S.historyMode[panelType];
  if (!S.historyMode[panelType]) {
    button.classList.remove('active');
    if (container._liveNodes) {
      container.replaceChildren(...container._liveNodes);
      container._liveNodes = null;
    } else {
      container.innerHTML = container.dataset.liveContent || '';
    }
    delete container.dataset.liveContent;
    return;
  }

  container.dataset.liveContent = container.innerHTML;
  container._liveNodes = Array.from(container.childNodes);
  button.classList.add('active');
  container.innerHTML = '<p class="text-dim">加载中…</p>';
  try {
    const r = await fetch(`/api/history?days=3&type=${panelType}`);
    const d = await r.json();
    renderHistoryFeed(d.history || [], container);
  } catch(e) {
    container.innerHTML = '<p class="text-dim">加载失败</p>';
  }
}
function renderHistoryFeed(entries, container) {
  container.innerHTML = '';
  if (!entries.length) {
    const empty = document.createElement('p');
    empty.className = 'text-dim';
    empty.textContent = '暂无记录';
    container.appendChild(empty);
    return;
  }
  const pad = n => String(n).padStart(2,'0');
  const fmtTime = ts => {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return ts || '';
    const t = pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds());
    return d.toDateString()===new Date().toDateString()?t:d.toLocaleDateString('zh-CN')+' '+t;
  };
  entries.forEach(entry=>{
    const item = document.createElement('div');
    item.className = 'feed-item';
    const time = document.createElement('span');
    time.className = 'feed-time';
    time.textContent = fmtTime(entry.timestamp);
    const file = (entry.file || '').replace(/\\/g,'/');
    const detail = entry.type === 'sync'
      ? [entry.event || 'sync', entry.target ? '→ '+entry.target : '', entry.reason || ''].filter(Boolean).join(' · ')
      : (entry.event || entry.type || '事件');
    item.appendChild(time);
    item.appendChild(document.createTextNode(' 📋 '+(file || '未知文件')+' — '+detail));
    container.appendChild(item);
  });
}
function applyAfterData(){const s=getSettings();if(s.displayMode==='ref'&&s.activeRoot)computeReachable(s.activeRoot);renderAll();}
function updateStats(st){if(st&&st.stats)document.getElementById('file-count').textContent=(st.stats.total_files||0)+' 文件 · '+(st.stats.total_edges||0)+' 边';if(st&&st.project_root)document.getElementById('footer-path').textContent=st.project_root;}
async function handleProjectSwitched(data){S.activeProject={name:data.name,root:data.root};await loadSettings();S.files=data.files||[];S._dagReachable=null;S.graphData=data.graph||null;computeStaleMap();const s=getSettings();if(s.displayMode==='ref'&&s.activeRoot)computeReachable(s.activeRoot);else S.reachableSet=new Set();renderProjectTabs();renderAll();updateStats(data);showToast('已切换到项目：'+data.name);}

// ── Project management ──
async function loadProjects(){const resp=await fetch('/api/projects');const data=await resp.json();S.projects=data;renderProjectTabs();if(S.projects.length>0&&!S.activeProject)selectProject(S.projects[0].name);}
function renderProjectTabs(){const container=document.getElementById('project-tabs');const dropdown=document.getElementById('project-dropdown');container.innerHTML='';dropdown.innerHTML='';if(!S.projects.length)return;const maxVisible=4;const visibleProjects=S.projects.slice(0,maxVisible);for(const p of visibleProjects){const tab=document.createElement('div');tab.className='project-tab';if(S.activeProject&&S.activeProject.name===p.name)tab.classList.add('active');if(!p.exists_on_disk)tab.classList.add('invalid');tab.innerHTML=`${!p.exists_on_disk?'<span class="tab-warn" title="路径不存在">⚠️</span>':''}<span class="tab-name" title="${p.root}">${p.name}</span>`;tab.querySelector('.tab-name').addEventListener('click',()=>{if(!p.exists_on_disk){showProjectError(p.name,p.root);return;}selectProject(p.name);});container.appendChild(tab);}for(const p of S.projects){const item=document.createElement('div');item.className='project-dropdown-item';if(S.activeProject&&S.activeProject.name===p.name)item.classList.add('active');item.innerHTML=`${!p.exists_on_disk?'<span class="dd-warn">⚠️</span>':''} ${p.name}`;item.addEventListener('click',()=>{if(!p.exists_on_disk){showProjectError(p.name,p.root);return;}selectProject(p.name);dropdown.classList.remove('show');});dropdown.appendChild(item);}
}
async function addProject(){const picker=document.getElementById('folder-picker');picker.value='';picker.click();}
async function handleFolderPicked(){const picker=document.getElementById('folder-picker');const files=picker.files;if(!files||files.length===0)return;const firstFile=files[0];const relativePath=firstFile.webkitRelativePath||firstFile.name;const folderName=relativePath.split('/')[0];const guessedPath=prompt('请输入项目文件夹的完整路径：',S.projects.length>0?S.projects[0].root.split('/').slice(0,-1).join('/')+'/'+folderName:'');if(!guessedPath)return;try{const resp=await fetch('/api/projects/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({root:guessedPath})});const data=await resp.json();if(data.success){await loadProjects();if(data.project)await selectProject(data.project.name);}else{alert('添加项目失败：'+JSON.stringify(data));}}catch(e){alert('添加项目失败：'+e.message);}}
async function removeProject(name){try{const resp=await fetch('/api/projects/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});const data=await resp.json();if(data.success){if(S.activeProject&&S.activeProject.name===name){S.activeProject=null;S.files=[];S.graphData=null;S.selectedFile=null;}await loadProjects();}}catch(e){console.error('removeProject error:',e);}}
async function selectProject(name){try{S.selectedFile=null;const resp=await fetch('/api/projects/select',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});const data=await resp.json();if(data.success){document.getElementById('no-project-state').style.display='none';document.getElementById('app').style.display='flex';}}catch(e){console.error('selectProject error:',e);}}
function showConfirmDelete(name){const msg='确定要移除项目"'+name+'"吗？移除后可从项目列表重新添加。';document.getElementById('modal-confirm-msg').textContent=msg;document.getElementById('modal-confirm').style.display='flex';document.getElementById('modal-confirm-ok').onclick=async()=>{document.getElementById('modal-confirm').style.display='none';await removeProject(name);};}
function showProjectError(name,path){document.getElementById('modal-error-msg').textContent='路径不存在：'+path+'，请重新选择文件夹或移除项目';document.getElementById('modal-error').style.display='flex';window._errorProjectName=name;}
async function handleErrorDelete(){document.getElementById('modal-error').style.display='none';if(window._errorProjectName)await removeProject(window._errorProjectName);}
async function handleErrorRechoose(){document.getElementById('modal-error').style.display='none';if(window._errorProjectName)await removeProject(window._errorProjectName);const picker=document.getElementById('folder-picker');picker.value='';picker.click();}

// ── Tree mode toggles ──
function updateTreeButtons(){document.getElementById('btn-tree-ref').classList.toggle('active',S.treeMode==='ref');document.getElementById('btn-tree-dir').classList.toggle('active',S.treeMode==='dir');}
function onFilterChange(e){
  if(e&&e.target){const id=e.target.id;if(id.includes('core'))S.showCore=e.target.checked;if(id.includes('base'))S.showBase=e.target.checked;if(id.includes('standalone'))S.showStandalone=e.target.checked;if(id.includes('external'))S.showExternal=e.target.checked;if(id.includes('hidden'))S.showHidden=e.target.checked;}
  else{S.showCore=document.getElementById('chk-show-core').checked;S.showBase=document.getElementById('chk-show-base').checked;S.showStandalone=document.getElementById('chk-show-standalone').checked;S.showExternal=document.getElementById('chk-show-external').checked;S.showHidden=document.getElementById('chk-show-hidden').checked;}
  // Sync all checkboxes
  document.querySelectorAll('[id*="show-core"],[id*="-core"]').forEach(cb=>cb.checked=S.showCore);
  document.querySelectorAll('.filter-base,[id*="-base"]').forEach(cb=>cb.checked=S.showBase);
  document.querySelectorAll('.filter-standalone,[id*="-standalone"]').forEach(cb=>cb.checked=S.showStandalone);
  document.querySelectorAll('.filter-external').forEach(cb=>cb.checked=S.showExternal);
  document.querySelectorAll('.filter-hidden').forEach(cb=>cb.checked=S.showHidden);
  localStorage.setItem('mindx_filter_state',JSON.stringify({showCore:S.showCore,showBase:S.showBase,showStandalone:S.showStandalone,showExternal:S.showExternal,showHidden:S.showHidden}));
  renderAll();
}

// ── Event listeners ──
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;if(e.ctrlKey&&e.key==='f'){e.preventDefault();document.getElementById('tree-filter').focus();}if(e.key==='Escape'){hideCtxMenu();hideSettings();document.getElementById('modal-confirm').style.display='none';document.getElementById('modal-error').style.display='none';}});
document.getElementById('btn-theme').addEventListener('click',()=>{const cur=document.documentElement.getAttribute('data-theme');const next=cur==='light'?'dark':'light';document.documentElement.setAttribute('data-theme',next);document.getElementById('btn-theme').textContent=next==='light'?'☀️':'🌙';localStorage.setItem('mindx_theme',next);renderAll();});
document.querySelectorAll('.filter-core').forEach(cb=>cb.addEventListener('change',e=>onFilterChange(e)));
document.querySelectorAll('.filter-base').forEach(cb=>cb.addEventListener('change',e=>onFilterChange(e)));
document.querySelectorAll('.filter-standalone').forEach(cb=>cb.addEventListener('change',e=>onFilterChange(e)));
document.querySelectorAll('.filter-external').forEach(cb=>cb.addEventListener('change',e=>onFilterChange(e)));
document.querySelectorAll('.filter-hidden').forEach(cb=>cb.addEventListener('change',e=>onFilterChange(e)));
['chk-ref-base','chk-ref-standalone','chk-dir-base','chk-dir-standalone','chk-dep-base','chk-dep-standalone'].forEach(id=>{const cb=document.getElementById(id);if(cb)cb.addEventListener('change',e=>onFilterChange(e));});
document.querySelectorAll('.history-toggle').forEach(btn=>btn.addEventListener('click',()=>toggleHistoryPanel(btn.dataset.panel)));
// Refresh buttons: clear saved positions and re-render with computed layout
document.getElementById('btn-ref-refresh')?.addEventListener('click',()=>{lsSet('reftree_positions',null);renderRefTreeGraph();});
document.getElementById('btn-dir-refresh')?.addEventListener('click',()=>{lsSet('dirtree_positions',null);renderDirTreeGraph();});
document.getElementById('btn-dep-refresh')?.addEventListener('click',()=>{lsSet('dep_positions',null);renderDepGraph();});
document.getElementById('btn-tree-ref').addEventListener('click',()=>{S.treeMode='ref';updateTreeButtons();renderFileTree();});
document.getElementById('btn-tree-dir').addEventListener('click',()=>{S.treeMode='dir';updateTreeButtons();renderFileTree();});
document.getElementById('btn-tree-select').addEventListener('click',toggleSelectMode);
document.getElementById('btn-tree-expand').addEventListener('click',()=>{document.querySelectorAll('#file-tree .tree-toggle:not(.leaf)').forEach(t=>t.classList.add('expanded'));document.querySelectorAll('#file-tree .tree-children').forEach(c=>c.classList.remove('collapsed'));});
document.getElementById('btn-tree-collapse').addEventListener('click',()=>{document.querySelectorAll('#file-tree .tree-toggle:not(.leaf)').forEach(t=>t.classList.remove('expanded'));document.querySelectorAll('#file-tree .tree-children').forEach(c=>c.classList.add('collapsed'));});
document.getElementById('btn-ref-save').addEventListener('click',()=>{saveRefTreePositions();showToast('引用树图布局已保存');});
document.getElementById('btn-dir-save').addEventListener('click',()=>{saveDirTreePositions();showToast('目录树图布局已保存');});
document.getElementById('btn-dep-save').addEventListener('click',()=>{saveDepPositions();showToast('依赖图布局已保存');});
document.querySelectorAll('.tab').forEach(tab=>{tab.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));tab.classList.add('active');document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));document.getElementById('tab-'+tab.dataset.tab).classList.add('active');if(tab.dataset.tab==='ref-tree'){setTimeout(()=>{if(S.netRefTree)S.netRefTree.redraw();},100);}if(tab.dataset.tab==='dir-tree'){setTimeout(()=>{if(S.netDirTree)S.netDirTree.redraw();},100);}if(tab.dataset.tab==='dep-graph'){setTimeout(()=>{if(S.netDepGraph)S.netDepGraph.redraw();},100);}});});
document.getElementById('fi-parents-header').addEventListener('click',()=>{const be=document.getElementById('fi-parents-list');be.style.display=be.style.display!=='none'?'none':'block';document.getElementById('fi-parents-header').querySelector('.fi-arrow').classList.toggle('expanded');});
document.getElementById('fi-children-header').addEventListener('click',()=>{const be=document.getElementById('fi-children-list');be.style.display=be.style.display!=='none'?'none':'block';document.getElementById('fi-children-header').querySelector('.fi-arrow').classList.toggle('expanded');});
document.getElementById('btn-show-detail').addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelector('[data-tab="detail"]').classList.add('active');document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));document.getElementById('tab-detail').classList.add('active');});
document.getElementById('btn-rescan').addEventListener('click',async()=>{
  const btn=document.getElementById('btn-rescan');
  const orig=btn.textContent;
  btn.textContent='⏳ 扫描中...';
  btn.disabled=true;
  try{
    const stats=await api('/api/scan');
    await fetchFiles();await fetchGraph();renderAll();
    showToast(`扫描完成：${stats.total_files} 个文件，${stats.total_edges} 条引用`);
  }catch(e){
    showToast('扫描失败：'+e.message);
  }finally{
    btn.textContent=orig;
    btn.disabled=false;
  }
});
document.getElementById('tree-filter').addEventListener('input',renderFileTree);
document.getElementById('btn-add-project').addEventListener('click',addProject);
document.getElementById('btn-no-project-add').addEventListener('click',addProject);
document.getElementById('modal-confirm-cancel').addEventListener('click',()=>document.getElementById('modal-confirm').style.display='none');
document.getElementById('modal-error-delete').addEventListener('click',handleErrorDelete);
document.getElementById('modal-error-rechoose').addEventListener('click',handleErrorRechoose);
document.getElementById('folder-picker').addEventListener('change',handleFolderPicked);
document.getElementById('btn-settings').addEventListener('click',showSettings);
document.getElementById('btn-settings-close').addEventListener('click',hideSettings);
document.getElementById('btn-settings-cancel').addEventListener('click',hideSettings);
document.getElementById('btn-settings-save').addEventListener('click',()=>{const s=getSettings();s.displayMode=document.getElementById('set-mode-ref').checked?'ref':'full';saveSettings(s);if(s.displayMode==='ref'&&s.activeRoot)computeReachable(s.activeRoot);else S.reachableSet=new Set();computeStaleMap();renderAll();hideSettings();});
document.getElementById('btn-settings-delete').addEventListener('click',()=>{if(!S.activeProject)return;hideSettings();showConfirmDelete(S.activeProject.name);});
document.getElementById('btn-add-root').addEventListener('click',addRootFile);
document.getElementById('btn-add-exclude').addEventListener('click',addExcludeDir);
document.getElementById('btn-pick-exclude').addEventListener('click',pickExcludeFolder);
document.getElementById('input-exclude-dir').addEventListener('keydown',e=>{if(e.key==='Enter')addExcludeDir();});
document.getElementById('btn-add-external').addEventListener('click',addExternal);
document.getElementById('btn-pick-external-file').addEventListener('click',pickExternalFile);
document.getElementById('btn-pick-external-folder').addEventListener('click',pickExternalFolder);
document.getElementById('input-external-path').addEventListener('keydown',e=>{if(e.key==='Enter')addExternal();});
document.getElementById('btn-batch-hide').addEventListener('click',batchHideSelected);
document.getElementById('btn-batch-cancel').addEventListener('click',batchCancel);
document.getElementById('btn-project-dropdown').addEventListener('click',e=>{e.stopPropagation();document.getElementById('project-dropdown').classList.toggle('show');});
document.addEventListener('click',()=>{document.getElementById('project-dropdown').classList.remove('show');});
document.getElementById('set-mode-full').addEventListener('change',()=>{document.getElementById('setting-roots').style.display='none';});
document.getElementById('set-mode-ref').addEventListener('change',()=>{document.getElementById('setting-roots').style.display='';});
// Classification buttons
document.getElementById('detail-classify').addEventListener('click',e=>{const btn=e.target.closest('.classify-btn');if(!btn)return;const path=S.selectedFile;if(!path)return;setClassification(path,btn.dataset.cls);renderAll();fetchFileDetail(path).then(d=>renderDetail(d));});
document.getElementById('btn-classify-default').addEventListener('click',()=>{const path=S.selectedFile;if(!path)return;setClassification(path,null);renderAll();fetchFileDetail(path).then(d=>renderDetail(d));});
function updateClock(){const t=new Date();document.getElementById('footer-time').textContent=t.toLocaleTimeString('zh-CN');}
setInterval(updateClock,1000);updateClock();
// Restore saved filter states from localStorage (global, not project-scoped)
try{const savedFilters=JSON.parse(localStorage.getItem('mindx_filter_state')||'null');
if(savedFilters){
  if('showCore' in savedFilters) S.showCore=savedFilters.showCore;
  if('showBase' in savedFilters) S.showBase=savedFilters.showBase;
  if('showStandalone' in savedFilters) S.showStandalone=savedFilters.showStandalone;
  if('showExternal' in savedFilters) S.showExternal=savedFilters.showExternal;
  if('showHidden' in savedFilters) S.showHidden=savedFilters.showHidden;
  // Sync restored S values to DOM checkboxes
  document.querySelectorAll('[id*="show-core"],[id*="-core"]').forEach(cb=>cb.checked=S.showCore);
  document.querySelectorAll('.filter-base,[id*="-base"]').forEach(cb=>cb.checked=S.showBase);
  document.querySelectorAll('.filter-standalone,[id*="-standalone"]').forEach(cb=>cb.checked=S.showStandalone);
  document.querySelectorAll('.filter-external').forEach(cb=>cb.checked=S.showExternal);
  document.querySelectorAll('.filter-hidden').forEach(cb=>cb.checked=S.showHidden);
}
}catch(e){}
connectSocket();

// ── Graph panel resize ──
(function(){
  let dragHandle=null, dragWrapper=null, startY=0, startH=0;
  document.addEventListener('mousedown',e=>{
    if(!e.target.classList.contains('graph-resize-handle'))return;
    dragHandle=e.target; dragWrapper=dragHandle.parentElement;
    // Capture current height before switching from flex to fixed
    startH=dragWrapper.offsetHeight;
    dragWrapper.style.height=startH+'px';
    startY=e.clientY;
    e.preventDefault();
  });
  document.addEventListener('mousemove',e=>{
    if(!dragHandle)return;
    const dy=e.clientY-startY, newH=Math.max(120,startH+dy);
    dragWrapper.style.height=newH+'px';
    // Resize vis-network to fit
    const netId=dragHandle.dataset.target;
    ['netRefTree','netDirTree','netDepGraph'].forEach(key=>{
      const net=S[key]; if(!net)return;
      const container=document.getElementById(netId);
      if(container&&container.parentElement===dragWrapper)net.redraw();
    });
  });
  document.addEventListener('mouseup',()=>{dragHandle=null;dragWrapper=null;});
})();
