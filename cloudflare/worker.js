/**
 * Knowledge Vault — phone Worker (capture + library view).
 *
 * Paste this whole file into a Cloudflare Worker. It needs:
 *   1. a KV namespace bound as   INBOX
 *   2. a secret / variable named TOKEN   (same token as the PC's config.json)
 *
 * It serves an installable PWA that can BOTH:
 *   - capture: share a reel / paste a link (stored under "s:" keys, R7–R10), and
 *   - view: browse the whole note library the PC publishes (under "card:" keys).
 *
 * KV holds only shared links (s:) and read-only card summaries (card:) — never
 * transcripts or raw text. All endpoints require the secret token.
 */

const ICON_192 = "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAIAAADdvvtQAAAB3UlEQVR42u3asQkAIAwAQaezdWx7d3ANdQURhCgnP4CEgzRJJXfpuGQEAkgACSABJAEkgASQAJIAEkACSABJAAkgASSAJIAEkAASQAJIAkgACSABJAEkgASQAJIAEkACSABJAAkgASSABJAEkAASQAJIAkgACSABJAEkgASQAJIAEkACSABJAOk1QDP8++/nAAEEEEAAAQQQQAABBBBAAAEEEEAAAQQQQAABBBBAAAEEEEAAAQQQQAABBBBAAAEEEEAAAQQQQAABBBBAAAG08Wobl7oNKObPAQIIICvMCgMIIIAAAggggAACCCCAAAIIIIAAAggggAACCCCAAAIIIIAAAggggAACCCCAAHKR6CIRIICsMCsMIIAAAggggAACCCCAAAIIIIAAAggggAACCCCAAAIIIIAAAggggAACCCCAAAIIIICctDppBQgggKwwKwwggAACCCCAAAIIIIAAAggggAACCCCAAAIIIIAAAggggAACCCCAAAIIIIAAAkgCSAAJIAEkASSABJAAEkASQAJIAAkgCSABJIAEkASQABJAAkgCSAAJIAEkgCSABJAAEkASQAJIAAkgCSABJIAEkASQABJAAkgAmYIAEkACSABJAAkgASSAJIAEkMK2AGfSyH5Vo6HfAAAAAElFTkSuQmCC";
const ICON_512 = "iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAIAAAB7GkOtAAAJs0lEQVR42u3asQ2AMAxE0UxHy9juvQNrONS0dNG905sAS/kN674eAAItnwBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABABAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABABAAHwFAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAHwFQAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQgDNtO2pu7dYIgAB4FNzarREAAfAouLVbIwAeBY+CW7u1AOBR8Ci4tQAIAB4Fj4JbC4AA4FEQABMAAcCjIAAmAAIgACYAJgACIAAmACYAAiAAJgAmAAIgACYAJgACIAAmACYAAiAAJgAmAAIgACYAJgACIAAmACYAAiAAJgAmAAIgACYAJgACIAAmACYAAiAAJgAmAAIgACYAJgACIAAmACYAAiAAJgBujQAIgAmAWyMAAuBRcGu3RgAEwKPg1m6NAHgUPApu7dYCgEfBo+DWAiAAeBQ8Cm4tAAKAR0EATAAEAI+CAJgACAAeBQEwARAAATABMAEQAAEwATABEAABMAEwARAAATABMAEQAAEwATABEAABMAEwARAAATABMAEQAAEwATABEAABMAEwARAAATABMAEQAAEwATABEAABMAEwARAAATABMAEQAAEwAXBrBEAATADcGgEQAI+CW7s1AiAAHgW3dmsEQAA8Cm7t1giAR8Gj4NZuLQB4FDwKbi0AAoBHwaPg1gIgAHgUBMAEQADwKAiACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAjAd9UTJTkAbi0AAiAAHgUBcGsBEAAB8CgIgFsLgAAIgEdBANxaAARAADwKAuDWAiAA/gIyfwGZAAiAAJgAmAAIgACYAJgACIAAmAC4NQIgACYAbo0ACIBHwa3dGgEQAI+CW7s1AuBR8Ci4tVsLAB4Fj4JbC4AA4FHwKLi1AAgAHgUBMAEQADwKAmACIAACYAJgAiAAAmACYAIgAAJgAmACIAACYAJgAiAAAmACYAIgAAJgAmACIAACYAJgAiAAAmACYAIgAAJgAmACIAACYAJgAiAAAmACYAIgAAJgAmACIAACYAJgAiAAAmACYAIgAAJgAuDWCIAAmAC4NQIgAB4Ft3ZrBEAAPApu7dYIgEfBo+DWbi0APoFHwaPg1m4tAHgUPApuLQACgEfBo+DWAiAAeBQEwARAAPAoCIAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAARAWgeqIkB8CtBUAABMCjIABuLQACIAAeBQFwawEQAAHwKAiAWwuAAAiAR0EA3FoABMBfQOYvIBMAARAAEwATAAEQABMAEwABEAATALdGAATABMCtEQAB8Ci4tVsjAALgUXBrt0YAPAoeBbd2awHAo+BRcGsBEAA8Ch4FtxYAAcCjIAAmAAKAR0EATAAEQABMAEwABEAATABMAARAAEwATAAEQABMAEwABEAATABMAARAAEwATAAEQABMAEwABEAATABMAARAAEwATAAEQABMAEwABEAATABMAARAAEwATAAEQABMAEwABEAATABMAARAAEwA3BoBEAATALdGAATAo+DWbo0ACIBHwa3dGgHwKHgU3NqtBcAn8Ch4FNzarQUAj4JHwa0FQADwKHgU3FoABACPggCYAAgAHgUBMAEQAAEwATABEAABMAEwARAAATABMAEQAAEwATABEAABMAEwARAAATABMAEQAAEwATABEAABMAEwARAAATABMAEQAAEwATABEICoAFRPlOQAuLUACIAAeBQEwK0FQAAEwKMgAG4tAAIgAB4FAXBrARAAAfAoCIBbC4AA+AvI/AVkAiAAAmACYAIgAAJgAmACIAACYALg1giAAJgAuDUCIAAeBbd2awRAADwKbu3WCIBHwaPg1m4tAHgUPApuLQACgEfBo+DWAiAAeBQEwARAAPAoCIAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAiACYAJgAAIgAmACYAACIAJgAmAAAiACYBbIwACYALg1giAAHgU3NqtEQAB8Ci4tVsjAB4Fj4Jbu7UA+AQeBY+CW7u1AOBR8Ci4tQAIAB4Fj4JbC4AA4FEQABMAAcCjIAAmAAIgACYAJgACIAAmACYAAiAAJgAmAAIgACYAJgACIAAmACYAAiAAJgAmAAIgACYAJgACIAAmACYAAiAAJgAmAAIgACYAJgACAIAAACAAAAgAAAIAgAAAIAAACAAAAgAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgAgAL4CgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAgAD4CgACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAA8NcLFNlXL31jblsAAAAASUVORK5CYII=";

function b64ToBytes(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function tokenOk(request, env) {
  const url = new URL(request.url);
  const token = url.searchParams.get("token") || request.headers.get("x-inbox-token");
  return Boolean(env.TOKEN) && token === env.TOKEN;
}

function html(body, status = 200) {
  return new Response(body, {
    status,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

async function listAll(env, prefix) {
  let keys = [];
  let cursor;
  for (;;) {
    const r = await env.INBOX.list({ prefix, cursor });
    keys = keys.concat(r.keys);
    if (r.list_complete) break;
    cursor = r.cursor;
    if (!cursor) break;
  }
  return keys;
}

const SAVED_PAGE = `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Saved</title>
<style>
 body{font-family:system-ui;background:#4f46e5;color:#fff;display:flex;
 align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column}
 .check{font-size:72px}
</style></head>
<body><div class="check">✓</div><h1>Saved</h1>
<p>It will appear in your library once the PC processes it.</p>
<script>setTimeout(function(){window.close()},1500)</script>
</body></html>`;

function page(token) {
  const t = token ? token.replace(/[^A-Za-z0-9_-]/g, "") : "";
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0b0e1c">
<title>Knowledge Vault</title>
<link rel="manifest" href="/manifest.json${t ? "?token=" + t : ""}">
<link rel="icon" href="/icon-192.png">
<style>
 :root{--ink:#0b0e1c;--panel:#12172c;--raised:#1a2140;--line:rgba(150,162,214,0.14);
  --text:#e8e9f6;--muted:#969dc4;--faint:#6b7099;--violet:#8b7bff;--violet2:#b4a8ff;
  --amber:#e9b26a;--soft:rgba(139,123,255,0.14);--mono:"Cascadia Mono",ui-monospace,Consolas,monospace}
 *{box-sizing:border-box}
 html{color-scheme:dark}
 body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);margin:0;
  background:radial-gradient(700px 500px at 80% -5%,rgba(139,123,255,0.12),transparent 60%),var(--ink);
  padding-bottom:calc(66px + env(safe-area-inset-bottom));-webkit-tap-highlight-color:transparent}
 header{padding:14px 16px;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;
  display:flex;align-items:center;gap:10px;background:rgba(11,14,28,0.82);backdrop-filter:blur(8px)}
 header .bn{font-weight:650;font-size:16px;flex:1;letter-spacing:-0.01em}
 .icon-btn{border:1px solid var(--line);background:var(--soft);color:var(--violet2);border-radius:10px;
  min-width:40px;min-height:40px;font-size:16px}
 main{padding:14px}
 .filters{display:flex;flex-direction:column;gap:9px;margin-bottom:12px}
 input,select,textarea{width:100%;padding:11px 12px;border:1px solid var(--line);border-radius:11px;
  font:inherit;font-size:15px;background:var(--ink);color:var(--text)}
 input::placeholder,textarea::placeholder{color:var(--faint)}
 select{color-scheme:dark}
 input:focus,select:focus,textarea:focus{outline:none;border-color:var(--violet);
  box-shadow:0 0 0 3px var(--soft)}
 .toggle{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:14px}
 .toggle input{width:auto}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:13px;
  margin-bottom:11px}
 .c-title{font-weight:600}
 .c-meta{color:var(--muted);font-size:12px;margin:3px 0;font-family:var(--mono)}
 .c-desc{margin:7px 0;font-size:14px;color:var(--text)}
 .tag{display:inline-block;background:var(--soft);color:var(--violet2);border-radius:999px;
  padding:2px 9px;font-size:12px;margin:2px 4px 0 0;font-family:var(--mono)}
 .msg{color:var(--muted);text-align:center;padding:40px 14px}
 textarea{min-height:130px}
 button.primary{width:100%;margin-top:12px;padding:13px;border:0;border-radius:11px;font-size:16px;
  font-weight:600;background:linear-gradient(180deg,var(--violet),#6f5cf0);color:#0b0e1c}
 nav.tabbar{position:fixed;bottom:0;left:0;right:0;background:rgba(15,19,38,0.94);
  backdrop-filter:blur(10px);border-top:1px solid var(--line);display:flex;
  padding-bottom:env(safe-area-inset-bottom)}
 nav.tabbar button{flex:1;border:0;background:none;padding:13px 4px;font-size:13px;color:var(--faint);
  min-height:52px}
 nav.tabbar button.active{color:var(--violet2);font-weight:600}
 #tab-graph{padding:0}
 .graph-holder{position:relative;height:calc(100vh - 66px - env(safe-area-inset-bottom) - 58px)}
 #gcanvas{display:block;width:100%;height:100%;touch-action:none;background:var(--ink-2)}
 .gbar{position:absolute;top:10px;left:10px;right:10px;display:flex;gap:8px;pointer-events:none}
 .gbar>*{pointer-events:auto}
 .gbar .icon-btn{background:rgba(18,23,44,0.85)}
 .ghint{position:absolute;bottom:10px;left:10px;font-family:var(--mono);font-size:11px;color:var(--faint)}
 #detail{display:none;position:fixed;inset:0;background:rgba(4,6,14,0.62);z-index:20;
  align-items:flex-end;backdrop-filter:blur(3px)}
 #detail .sheet{background:var(--panel);border:1px solid var(--line);border-radius:18px 18px 0 0;
  padding:18px;max-height:88vh;overflow:auto;width:100%}
 #detail h2{margin:6px 0;letter-spacing:-0.01em}
 #detail h3{font-size:13px;color:var(--violet2);margin:16px 0 4px;text-transform:uppercase;
  letter-spacing:0.08em;font-family:var(--mono)}
 #detail a{color:var(--violet2);word-break:break-all}
 .close{float:right;border:1px solid var(--line);background:var(--raised);color:var(--text);
  border-radius:9px;padding:8px 14px;min-height:40px}
 :focus-visible{outline:2px solid var(--violet2);outline-offset:2px}
</style></head>
<body>
<header>
  <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <circle cx="16" cy="16" r="15" fill="#12172c" stroke="#8b7bff" stroke-opacity="0.4"/>
    <line x1="16" y1="16" x2="8" y2="9" stroke="#8b7bff" stroke-opacity="0.5"/>
    <line x1="16" y1="16" x2="24" y2="11" stroke="#8b7bff" stroke-opacity="0.5"/>
    <line x1="16" y1="16" x2="23" y2="22" stroke="#e9b26a" stroke-opacity="0.5"/>
    <circle cx="8" cy="9" r="2" fill="#8b7bff"/><circle cx="24" cy="11" r="2" fill="#8b7bff"/>
    <circle cx="23" cy="22" r="2.4" fill="#e9b26a"/><circle cx="16" cy="16" r="3.2" fill="#b4a8ff"/>
  </svg>
  <span class="bn">Knowledge Vault</span>
  <button class="icon-btn" id="refresh" aria-label="Refresh library">↻</button>
</header>
<main>
  <section id="tab-library">
    <div class="filters">
      <input type="text" id="f-search" placeholder="Search your notes…" aria-label="Search notes"
        autocomplete="off" spellcheck="false">
      <select id="f-cat" aria-label="Filter by category"><option value="">All categories</option></select>
      <label class="toggle"><input type="checkbox" id="f-done"> Show archived / done</label>
    </div>
    <div id="card-list"></div>
  </section>
  <section id="tab-graph" style="display:none">
    <div class="graph-holder">
      <canvas id="gcanvas" aria-label="Knowledge graph"></canvas>
      <div class="gbar">
        <button class="icon-btn" id="g-reset" aria-label="Reset graph view">⤢</button>
        <label class="toggle" style="background:rgba(18,23,44,0.85);padding:8px 10px;border-radius:10px;">
          <input type="checkbox" id="g-archived"> Archived</label>
      </div>
      <div class="ghint">drag · pinch · tap a star</div>
    </div>
  </section>
  <section id="tab-add" style="display:none">
    <p class="c-meta" style="font-family:system-ui;font-size:14px;color:var(--muted)">Paste a link or
    text, or share to this app from Instagram / TikTok / YouTube. It is processed on your PC and shows
    up in your library.</p>
    <textarea id="add-box" placeholder="Paste a link or some text…" aria-label="Link or text to save"></textarea>
    <button class="primary" onclick="sendAdd()">Save to vault</button>
    <p class="c-meta" id="add-msg" style="font-family:system-ui"></p>
    <p class="c-meta" style="font-family:system-ui;color:var(--faint)">Tip: install this page (browser
    menu, Add to Home screen) so "Knowledge Vault" appears in your share sheet.</p>
  </section>
</main>
<nav class="tabbar">
  <button id="nav-library" class="active" onclick="showTab('library')">Library</button>
  <button id="nav-graph" onclick="showTab('graph')">Graph</button>
  <button id="nav-add" onclick="showTab('add')">Add</button>
</nav>
<div id="detail" onclick="if(event.target===this)closeDetail()">
  <div class="sheet">
    <button class="close" onclick="closeDetail()">Close</button>
    <div id="detail-body"></div>
  </div>
</div>
<script src="/app.js"></script>
</body></html>`;
}

// Client app. IMPORTANT: no backticks and no ${...} in here — this whole string
// is itself embedded in a template literal on the PC side / worker responses.
const APP_JS = `(function(){
  var qs = new URLSearchParams(location.search);
  if (qs.get('token')) localStorage.setItem('kv_token', qs.get('token'));
  var TOKEN = localStorage.getItem('kv_token') || '';
  var cards = [];
  function esc(s){ s=(s==null?'':String(s));
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function el(id){ return document.getElementById(id); }
  function showTab(name){
    el('tab-library').style.display = name==='library'?'block':'none';
    el('tab-graph').style.display = name==='graph'?'block':'none';
    el('tab-add').style.display = name==='add'?'block':'none';
    el('nav-library').className = name==='library'?'active':'';
    el('nav-graph').className = name==='graph'?'active':'';
    el('nav-add').className = name==='add'?'active':'';
    if (name==='library') loadCards();
    if (name==='graph'){
      if (cards.length){ gResize(); buildGraph(); }
      else loadCards().then(function(){ gResize(); buildGraph(); });
    }
  }
  window.showTab = showTab;
  async function loadCards(){
    var list = el('card-list');
    if (!TOKEN){ list.innerHTML = '<p class="msg">Open this page once using the link from your PC setup to connect it.</p>'; return; }
    list.innerHTML = '<p class="msg">Loading…</p>';
    try{
      var r = await fetch('/cards?token=' + encodeURIComponent(TOKEN));
      if (r.status===401){ list.innerHTML = '<p class="msg">Wrong or missing token. Re-open via the PC link.</p>'; return; }
      var data = await r.json();
      cards = data.cards || [];
      buildCategoryFilter();
      render();
    }catch(e){ list.innerHTML = '<p class="msg">Could not load your notes. Check your connection.</p>'; }
  }
  function buildCategoryFilter(){
    var sel = el('f-cat'); var paths = {};
    cards.forEach(function(c){ if(c.category_path) paths[c.category_path]=1; });
    var opts = ['<option value="">All categories</option>'];
    Object.keys(paths).sort().forEach(function(p){ opts.push('<option value="'+esc(p)+'">'+esc(p)+'</option>'); });
    var cur = sel.value; sel.innerHTML = opts.join(''); sel.value = cur;
  }
  function matches(c,q){
    if(!q) return true;
    var hay = (c.title+' '+c.short_description+' '+(c.tags||[]).join(' ')+' '+
      (c.main_points||[]).map(function(p){return p.name+' '+p.description;}).join(' ')).toLowerCase();
    return hay.indexOf(q)>=0;
  }
  function render(){
    var q = el('f-search').value.trim().toLowerCase();
    var cat = el('f-cat').value; var showDone = el('f-done').checked;
    var list = el('card-list');
    var rows = cards.filter(function(c){
      if(!showDone && c.status==='done') return false;
      if(cat && !(c.category_path===cat || (c.category_path||'').indexOf(cat+'/')===0)) return false;
      return matches(c,q);
    });
    rows.sort(function(a,b){ return (b.date_saved||'').localeCompare(a.date_saved||'')||(b.id-a.id); });
    if(!rows.length){ list.innerHTML = '<p class="msg">No notes'+(cards.length?' match your filters.':' yet. Share a reel to get started!')+'</p>'; return; }
    list.innerHTML = rows.map(function(c){
      return '<div class="card" onclick="openCard('+c.id+')">'+
        '<div class="c-title">'+esc(c.title)+(c.status==='done'?' <span class="tag">done</span>':'')+'</div>'+
        '<div class="c-meta">'+esc(c.category_path||'')+' · '+esc(c.platform||'')+' · '+esc(c.date_saved||'')+'</div>'+
        '<div class="c-desc">'+esc(c.short_description||'')+'</div>'+
        '<div>'+(c.tags||[]).map(function(t){return '<span class="tag">#'+esc(t)+'</span>';}).join('')+'</div>'+
      '</div>';
    }).join('');
  }
  function openCard(id){
    var c = cards.filter(function(x){return x.id===id;})[0];
    if(!c) return;
    var pts = (c.main_points||[]).map(function(p){ return '<li><b>'+esc(p.name)+'</b>'+(p.description?' — '+esc(p.description):'')+'</li>'; }).join('');
    var src = c.source_url ? '<a href="'+esc(c.source_url)+'" target="_blank" rel="noopener">'+esc(c.source_url)+'</a>' : esc(c.platform);
    var add = (c.additional_sources||[]).map(function(u){return '<div><a href="'+esc(u)+'" target="_blank" rel="noopener">'+esc(u)+'</a></div>';}).join('');
    var rel = (c.related||[]).map(function(t){return '<li>'+esc(t)+'</li>';}).join('');
    el('detail-body').innerHTML =
      '<h2>'+esc(c.title)+'</h2>'+
      '<div class="c-meta">'+esc(c.category_path||'')+' · '+esc(c.platform||'')+' · '+esc(c.date_saved||'')+' · '+esc(c.extraction_status||'')+'</div>'+
      '<h3>Main points</h3><ol>'+pts+'</ol>'+
      '<h3>Summary</h3><p>'+esc(c.short_description||'')+'</p>'+
      '<h3>Source</h3><p>'+src+'</p>'+(add?'<div class="c-meta">Also from:</div>'+add:'')+
      (rel?'<h3>Related notes</h3><ul>'+rel+'</ul>':'');
    el('detail').style.display='flex';
  }
  window.openCard = openCard;
  window.closeDetail = function(){ el('detail').style.display='none'; };
  async function send(){
    var box = el('add-box'); var msg = el('add-msg'); var text = box.value.trim();
    if(!text){ msg.textContent='Paste something first.'; return; }
    if(!TOKEN){ msg.textContent='Not connected — open via the PC link first.'; return; }
    var body = new URLSearchParams(); body.append('text', text);
    var r = await fetch('/submit?token='+encodeURIComponent(TOKEN), {method:'POST', body:body});
    msg.textContent = r.ok ? 'Saved ✓ — it will appear here once your PC processes it.' : 'Error saving.';
    if(r.ok) box.value='';
  }
  window.sendAdd = send;

  // ------------------------------------------------------------- graph
  var G = { nodes: [], links: [], by: {}, nb: {}, view: {x:0,y:0,k:1},
    alpha: 0, running: false, drag: null, dragged: false, pan: false,
    ptrs: {}, pinch: 0, last: {x:0,y:0}, built: false };
  var gcanvas = el('gcanvas'), gctx = gcanvas.getContext('2d');
  var gdpr = Math.max(1, window.devicePixelRatio || 1);
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function gW(){ return gcanvas.width / gdpr; }
  function gH(){ return gcanvas.height / gdpr; }
  function gResize(){
    gdpr = Math.max(1, window.devicePixelRatio || 1);
    var r = gcanvas.getBoundingClientRect();
    gcanvas.width = Math.round(r.width * gdpr); gcanvas.height = Math.round(r.height * gdpr);
    gRender();
  }
  window.addEventListener('resize', function(){ if(el('tab-graph').style.display!=='none') gResize(); });

  function buildGraph(){
    var showDone = el('g-archived').checked;
    var vis = cards.filter(function(c){ return showDone || c.status !== 'done'; });
    var nodes = [], links = [], by = {}, catBy = {}, titleTo = {};
    function catNode(path){
      if(!path) return null;
      if(catBy[path]) return catBy[path];
      var n = { id:'c:'+path, type:'cat', label:path.split('/').pop(), path:path };
      catBy[path] = n; by[n.id] = n; nodes.push(n);
      var parts = path.split('/');
      if(parts.length > 1){ var p = catNode(parts.slice(0,-1).join('/')); links.push({s:p.id,t:n.id}); }
      return n;
    }
    vis.forEach(function(c){
      var n = { id:'n:'+c.id, type:'note', label:c.title, status:c.status, card:c };
      by[n.id] = n; nodes.push(n); titleTo[c.title] = n.id;
      if(c.category_path){ links.push({ s: catNode(c.category_path).id, t: n.id }); }
    });
    vis.forEach(function(c){
      (c.related||[]).forEach(function(tt){ var rid = titleTo[tt];
        if(rid) links.push({ s:'n:'+c.id, t:rid, rel:1 }); });
    });
    links = links.filter(function(l){ return by[l.s] && by[l.t]; });
    G.nb = {};
    nodes.forEach(function(n){ n.x = gW()/2 + (Math.random()-0.5)*260; n.y = gH()/2 + (Math.random()-0.5)*260;
      n.vx=0; n.vy=0; n.deg=0; G.nb[n.id] = new Set(); });
    links.forEach(function(l){ by[l.s].deg++; by[l.t].deg++; G.nb[l.s].add(l.t); G.nb[l.t].add(l.s); });
    G.nodes = nodes; G.links = links; G.by = by; G.built = true;
    if(!nodes.length){ gRender(); return; }
    if(reduce){ for(var i=0;i<300;i++) gStep(0.9); gFit(); gRender(); }
    else { G.alpha = 1; gFit(); gStartLoop(); }
  }
  function gRadius(n){ var b = n.type==='cat'?6:3.4;
    return b + Math.min(6, Math.sqrt(n.deg)*(n.type==='cat'?2:1.3)); }
  function gStep(a){
    var R=4600,S=0.04,L=58,GR=0.03, cx=gW()/2, cy=gH()/2, N=G.nodes;
    for(var i=0;i<N.length;i++){ var n=N[i]; n.vx+=(cx-n.x)*GR*a; n.vy+=(cy-n.y)*GR*a;
      for(var j=i+1;j<N.length;j++){ var m=N[j]; var dx=n.x-m.x,dy=n.y-m.y,d2=dx*dx+dy*dy||0.01;
        if(d2>80000) continue; var f=R*a/d2, d=Math.sqrt(d2), fx=dx/d*f, fy=dy/d*f;
        n.vx+=fx;n.vy+=fy;m.vx-=fx;m.vy-=fy; } }
    G.links.forEach(function(l){ var s=G.by[l.s],t=G.by[l.t],dx=t.x-s.x,dy=t.y-s.y,
      d=Math.sqrt(dx*dx+dy*dy)||0.01, f=(d-L)*S*a, fx=dx/d*f, fy=dy/d*f;
      s.vx+=fx;s.vy+=fy;t.vx-=fx;t.vy-=fy; });
    N.forEach(function(n){ if(n===G.drag){n.vx=0;n.vy=0;return;} n.x+=n.vx*=0.82; n.y+=n.vy*=0.82; });
  }
  function gStartLoop(){ if(!G.running){ G.running=true; requestAnimationFrame(gLoop); } }
  function gLoop(){ if(G.alpha>0.006){ gStep(G.alpha); G.alpha*=0.985; gRender(); requestAnimationFrame(gLoop); }
    else { G.running=false; gRender(); } }
  function gReheat(a){ G.alpha=Math.max(G.alpha,a); gStartLoop(); }
  function gFit(){ if(!G.nodes.length) return; var mnX=1e9,mnY=1e9,mxX=-1e9,mxY=-1e9;
    G.nodes.forEach(function(n){ mnX=Math.min(mnX,n.x);mxX=Math.max(mxX,n.x);mnY=Math.min(mnY,n.y);mxY=Math.max(mxY,n.y); });
    var pad=70, k=Math.min(2,Math.max(0.2,Math.min(gW()/(mxX-mnX+pad),gH()/(mxY-mnY+pad))));
    G.view.k=k; G.view.x=gW()/2-(mnX+mxX)/2*k; G.view.y=gH()/2-(mnY+mxY)/2*k; }
  function gToWorld(px,py){ return { x:(px-G.view.x)/G.view.k, y:(py-G.view.y)/G.view.k }; }
  function gRender(){
    gctx.setTransform(gdpr,0,0,gdpr,0,0); gctx.clearRect(0,0,gW(),gH());
    gctx.setTransform(G.view.k*gdpr,0,0,G.view.k*gdpr,G.view.x*gdpr,G.view.y*gdpr);
    G.links.forEach(function(l){ var s=G.by[l.s],t=G.by[l.t];
      gctx.strokeStyle=l.rel?'rgba(139,123,255,0.30)':'rgba(150,162,214,0.16)';
      gctx.lineWidth=0.9/G.view.k; gctx.beginPath(); gctx.moveTo(s.x,s.y); gctx.lineTo(t.x,t.y); gctx.stroke(); });
    G.nodes.forEach(function(n){ var r=gRadius(n), done=n.status==='done';
      gctx.beginPath(); gctx.arc(n.x,n.y,r,0,6.2832);
      gctx.fillStyle= done?'#3a4472':(n.type==='cat'?'#e9b26a':'#8b7bff'); gctx.fill();
      gctx.lineWidth=1/G.view.k; gctx.strokeStyle='rgba(11,14,28,0.9)'; gctx.stroke(); });
    gctx.textAlign='center'; gctx.textBaseline='top';
    G.nodes.forEach(function(n){ var isCat=n.type==='cat';
      if(!isCat && G.view.k<=1.2) return; var r=gRadius(n), size=(isCat?11:10)/G.view.k;
      gctx.font=(isCat?'600 ':'')+size+'px system-ui,sans-serif';
      var lab=n.label.length>30?n.label.slice(0,29)+'…':n.label;
      gctx.lineWidth=3/G.view.k; gctx.strokeStyle='rgba(11,14,28,0.85)';
      gctx.strokeText(lab,n.x,n.y+r+3/G.view.k);
      gctx.fillStyle=isCat?'#f0d7ad':'#c9ccea'; gctx.fillText(lab,n.x,n.y+r+3/G.view.k); });
  }
  function gNodeAt(px,py){ var w=gToWorld(px,py), best=null, bd=1e9;
    G.nodes.forEach(function(n){ var r=gRadius(n)+8/G.view.k, dx=n.x-w.x, dy=n.y-w.y, d=dx*dx+dy*dy;
      if(d<r*r && d<bd){ best=n; bd=d; } }); return best; }
  function gPos(e){ var r=gcanvas.getBoundingClientRect(); return {x:e.clientX-r.left,y:e.clientY-r.top}; }
  gcanvas.addEventListener('pointerdown', function(e){ gcanvas.setPointerCapture(e.pointerId);
    var p=gPos(e); G.ptrs[e.pointerId]=p; G.dragged=false; G.last=p;
    var ids=Object.keys(G.ptrs);
    if(ids.length===2){ G.drag=null; G.pan=false; G.pinch=gDist(); return; }
    var n=gNodeAt(p.x,p.y); if(n){ G.drag=n; } else { G.pan=true; } });
  function gDist(){ var k=Object.keys(G.ptrs); if(k.length<2) return 0;
    var a=G.ptrs[k[0]],b=G.ptrs[k[1]]; return Math.hypot(a.x-b.x,a.y-b.y); }
  function gMid(){ var k=Object.keys(G.ptrs), a=G.ptrs[k[0]],b=G.ptrs[k[1]];
    return {x:(a.x+b.x)/2,y:(a.y+b.y)/2}; }
  gcanvas.addEventListener('pointermove', function(e){ if(!(e.pointerId in G.ptrs)) return;
    var p=gPos(e); G.ptrs[e.pointerId]=p;
    if(Object.keys(G.ptrs).length===2){ var d=gDist(); if(G.pinch){ var m=gMid();
      gZoom(m.x,m.y,d/G.pinch); } G.pinch=d; G.dragged=true; return; }
    if(G.drag){ var w=gToWorld(p.x,p.y); G.drag.x=w.x; G.drag.y=w.y; G.drag.vx=0; G.drag.vy=0;
      G.dragged=true; gReheat(0.3); gRender(); }
    else if(G.pan){ G.view.x+=p.x-G.last.x; G.view.y+=p.y-G.last.y; G.last=p; G.dragged=true; gRender(); } });
  function gEnd(e){ if(e.pointerId in G.ptrs){
    if(G.drag && !G.dragged){ gOpen(G.drag); }
    delete G.ptrs[e.pointerId]; }
    if(Object.keys(G.ptrs).length<2) G.pinch=0;
    if(!Object.keys(G.ptrs).length){ G.drag=null; G.pan=false; } }
  gcanvas.addEventListener('pointerup', gEnd);
  gcanvas.addEventListener('pointercancel', gEnd);
  gcanvas.addEventListener('wheel', function(e){ e.preventDefault(); var p=gPos(e);
    gZoom(p.x,p.y,Math.exp(-e.deltaY*0.0016)); }, {passive:false});
  function gZoom(px,py,factor){ var k2=Math.min(6,Math.max(0.12,G.view.k*factor));
    G.view.x=px-(px-G.view.x)*(k2/G.view.k); G.view.y=py-(py-G.view.y)*(k2/G.view.k);
    G.view.k=k2; gRender(); }
  function gOpen(n){ if(n.type==='note'){ openCard(n.card.id); }
    else { el('f-cat').value=n.path; showTab('library'); render(); } }
  el('g-reset').addEventListener('click', function(){ gFit(); gRender(); });
  el('g-archived').addEventListener('change', buildGraph);

  el('f-search').addEventListener('input', render);
  el('f-cat').addEventListener('change', render);
  el('f-done').addEventListener('change', render);
  el('refresh').addEventListener('click', function(){ G.built=false; loadCards(); });
  if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
  showTab('library');
})();`;

function manifest(token) {
  const t = token ? "?token=" + encodeURIComponent(token) : "";
  return {
    name: "Knowledge Vault",
    short_name: "Knowledge Vault",
    description: "Capture and browse your Knowledge Vault notes.",
    start_url: "/" + t,
    display: "standalone",
    background_color: "#f6f7fb",
    theme_color: "#4f46e5",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any maskable" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
    ],
    share_target: {
      action: "/share" + t,
      method: "POST",
      enctype: "application/x-www-form-urlencoded",
      params: { url: "url", text: "text", title: "title" },
    },
  };
}

const SW_JS = `self.addEventListener('install', function(e){ self.skipWaiting(); });
self.addEventListener('activate', function(e){ self.clients.claim(); });
self.addEventListener('fetch', function(e){});`;

async function storeShare(request, env) {
  let url = "", text = "", title = "";
  const ct = request.headers.get("content-type") || "";
  if (ct.includes("json")) {
    const data = await request.json();
    url = data.url || ""; text = data.text || ""; title = data.title || "";
  } else {
    const form = await request.formData();
    url = form.get("url") || ""; text = form.get("text") || ""; title = form.get("title") || "";
  }
  if (!url && !text && !title) return false;
  const key = "s:" + Date.now() + ":" + Math.random().toString(36).slice(2, 8);
  await env.INBOX.put(key, JSON.stringify({
    url, text, title, ts: new Date().toISOString(),
  }));
  return true;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "GET") {
      if (path === "/") return html(page(url.searchParams.get("token")));
      if (path === "/app.js")
        return new Response(APP_JS, { headers: { "content-type": "application/javascript; charset=utf-8" } });
      if (path === "/manifest.json")
        return new Response(JSON.stringify(manifest(url.searchParams.get("token"))), {
          headers: { "content-type": "application/manifest+json" },
        });
      if (path === "/sw.js")
        return new Response(SW_JS, { headers: { "content-type": "application/javascript" } });
      if (path === "/icon-192.png")
        return new Response(b64ToBytes(ICON_192), { headers: { "content-type": "image/png" } });
      if (path === "/icon-512.png")
        return new Response(b64ToBytes(ICON_512), { headers: { "content-type": "image/png" } });

      if (path === "/inbox") {
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const keys = await listAll(env, "s:");
        const items = [];
        for (const k of keys) {
          const value = await env.INBOX.get(k.name);
          if (value) items.push({ key: k.name, ...JSON.parse(value) });
        }
        return Response.json({ items });
      }

      if (path === "/cards") {
        // Phone library reads the PC-published card summaries.
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const keys = await listAll(env, "card:");
        if (url.searchParams.get("ids")) {
          return Response.json({ cards: keys.map((k) => ({ id: Number(k.name.slice(5)) })) });
        }
        const cards = await Promise.all(keys.map(async (k) => {
          const v = await env.INBOX.get(k.name);
          return v ? JSON.parse(v) : null;
        }));
        return Response.json({ cards: cards.filter(Boolean) });
      }
      return new Response("not found", { status: 404 });
    }

    if (request.method === "POST") {
      if (path === "/share" || path === "/submit") {
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const ok = await storeShare(request, env);
        if (path === "/share") return html(SAVED_PAGE);
        return ok ? Response.json({ ok: true })
                  : Response.json({ ok: false, error: "empty share" }, { status: 400 });
      }
      if (path === "/delete") {
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const { keys } = await request.json();
        for (const key of keys || []) await env.INBOX.delete(key);
        return Response.json({ ok: true });
      }
      if (path === "/cards/put") {
        // PC publishes / updates one card summary.
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const card = await request.json();
        if (card && card.id != null)
          await env.INBOX.put("card:" + card.id, JSON.stringify(card));
        return Response.json({ ok: true });
      }
      if (path === "/cards/delete") {
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const body = await request.json();
        const ids = body.ids || (body.id != null ? [body.id] : []);
        for (const id of ids) await env.INBOX.delete("card:" + id);
        return Response.json({ ok: true });
      }
    }
    return new Response("not found", { status: 404 });
  },
};
