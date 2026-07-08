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
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0d1017">
<title>Saved</title>
<style>
 body{font-family:system-ui;background:#0d1017;color:#eceef4;display:flex;
 align-items:center;justify-content:center;height:100vh;margin:0;flex-direction:column}
 .check{font-size:72px;color:#67dfe8}
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
<meta name="theme-color" content="#0d1017">
<title>Knowledge Vault</title>
<link rel="manifest" href="/manifest.json${t ? "?token=" + t : ""}">
<link rel="icon" href="/icon-192.png">
<style>
 :root{--ink:#0d1017;--ink2:#10141d;--panel:#151a24;--raised:#1c2230;--line:rgba(255,255,255,0.08);
  --text:#eceef4;--muted:#9aa3b5;--faint:#6b7385;--violet:#67dfe8;--violet2:#a9f0f6;
  --amber:#e9b26a;--soft:rgba(103,223,232,0.12);--serif:Georgia,"Palatino Linotype","Times New Roman",serif;
  --mono:"Cascadia Mono",ui-monospace,Consolas,monospace;--radius:12px;--radius-sm:9px}
 *{box-sizing:border-box}
 html{color-scheme:dark}
 body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--text);margin:0;
  background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260' viewBox='0 0 260 260'%3E%3Cg fill='none' stroke='%23aab6d8' stroke-opacity='0.05' stroke-width='1'%3E%3Cpath d='M20 40 L90 20 L150 70 L110 130 L40 110 Z'/%3E%3Cpath d='M150 70 L220 100 L240 180'/%3E%3Cpath d='M110 130 L160 200 L100 240'/%3E%3C/g%3E%3Cg fill='%23aab6d8' fill-opacity='0.09'%3E%3Ccircle cx='20' cy='40' r='1.6'/%3E%3Ccircle cx='90' cy='20' r='1.2'/%3E%3Ccircle cx='150' cy='70' r='1.8'/%3E%3Ccircle cx='110' cy='130' r='1.3'/%3E%3Ccircle cx='40' cy='110' r='1.2'/%3E%3Ccircle cx='220' cy='100' r='1.4'/%3E%3Ccircle cx='240' cy='180' r='1.1'/%3E%3Ccircle cx='160' cy='200' r='1.5'/%3E%3Ccircle cx='100' cy='240' r='1.2'/%3E%3C/g%3E%3C/svg%3E"),var(--ink);
  padding-bottom:calc(72px + env(safe-area-inset-bottom));-webkit-tap-highlight-color:transparent}
 header{padding:14px 16px;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;
  display:flex;align-items:center;gap:10px;background:rgba(13,16,23,0.85);backdrop-filter:blur(8px)}
 header .bn{font-family:var(--serif);font-weight:600;font-size:17px;flex:1;letter-spacing:0.01em}
 .icon-btn{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:10px;
  min-width:40px;min-height:40px;font-size:16px}
 main{padding:14px}
 .filters{display:flex;flex-direction:column;gap:9px;margin-bottom:12px}
 input,select,textarea{width:100%;padding:12px 14px;border:1px solid var(--line);border-radius:var(--radius);
  font:inherit;font-size:15px;background:var(--ink2);color:var(--text)}
 input::placeholder,textarea::placeholder{color:var(--faint)}
 select{color-scheme:dark}
 input:focus,select:focus,textarea:focus{outline:none;border-color:var(--violet);
  box-shadow:0 0 0 3px var(--soft)}
 .toggle{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:14px}
 .toggle input{width:auto;accent-color:var(--violet)}
 .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px;
  margin-bottom:12px}
 .c-title{font-family:var(--serif);font-weight:550;font-size:19px;line-height:1.25;color:var(--text)}
 .c-meta{color:var(--muted);font-size:12px;margin:6px 0 0;font-weight:500}
 .c-desc{margin:9px 0 0;font-size:14px;line-height:1.5;color:var(--muted)}
 .tag{display:inline;background:none;color:var(--muted);border-radius:0;
  padding:0;font-size:12px;margin:0 8px 0 0;font-family:inherit;font-weight:500}
 .msg{color:var(--muted);text-align:center;padding:40px 14px}
 textarea{min-height:130px}
 button.primary{width:100%;margin-top:12px;padding:13px;border:0;border-radius:var(--radius);font-size:16px;
  font-weight:600;background:#e9ebf2;color:#0d1017}
 nav.tabbar{position:fixed;bottom:0;left:0;right:0;background:rgba(13,16,23,0.94);
  backdrop-filter:blur(10px);border-top:1px solid var(--line);display:flex;
  padding-bottom:env(safe-area-inset-bottom)}
 nav.tabbar button{flex:1;border:0;background:none;padding:9px 2px 10px;color:var(--faint);
  min-height:56px;display:flex;flex-direction:column;align-items:center;gap:3px;
  font-size:10.5px;line-height:1.15;white-space:normal}
 nav.tabbar button .tico{font-size:17px;line-height:1}
 nav.tabbar button.active{color:var(--violet2);font-weight:600}
 #tab-graph{padding:0}
 .graph-holder{position:relative;height:calc(100vh - 72px - env(safe-area-inset-bottom) - 58px)}
 #gcanvas{display:block;width:100%;height:100%;touch-action:none;background:var(--ink2)}
 .gbar{position:absolute;top:10px;left:10px;right:10px;display:flex;gap:8px;pointer-events:none}
 .gbar>*{pointer-events:auto}
 .gbar .icon-btn{background:rgba(21,26,36,0.85)}
 .gcluster{position:absolute;right:10px;bottom:calc(10px + env(safe-area-inset-bottom));
  display:flex;flex-direction:column;gap:4px;background:rgba(13,16,23,0.85);border:1px solid var(--line);
  border-radius:10px;padding:4px;backdrop-filter:blur(6px)}
 .gcluster button{width:36px;height:36px;min-height:36px;border:0;background:transparent;color:var(--muted);
  font-size:16px;border-radius:8px}
 .ghint{position:absolute;bottom:calc(10px + env(safe-area-inset-bottom));left:10px;right:auto;
  font-family:var(--mono);font-size:11px;color:var(--faint)}
 #detail{display:flex;position:fixed;inset:0;background:rgba(5,7,12,0.68);z-index:20;
  align-items:flex-end;backdrop-filter:blur(3px);opacity:0;visibility:hidden;
  transition:opacity .2s ease,visibility 0s linear .2s}
 #detail.open{opacity:1;visibility:visible;transition:opacity .2s ease}
 #detail .sheet{background:var(--panel);border:1px solid var(--line);border-radius:16px 16px 0 0;
  padding:18px;max-height:88vh;overflow:auto;width:100%;transform:translateY(100%);transition:transform .22s ease}
 #detail.open .sheet{transform:none}
 #detail h2{font-family:var(--serif);font-weight:550;margin:6px 0;letter-spacing:0.005em}
 #detail h3{font-size:12px;color:var(--violet2);margin:16px 0 4px;text-transform:uppercase;
  letter-spacing:0.1em;font-family:var(--mono)}
 #detail a{color:var(--violet2);word-break:break-all}
 .close{float:right;border:1px solid var(--line);background:var(--raised);color:var(--text);
  border-radius:9px;padding:8px 14px;min-height:40px}
 :focus-visible{outline:2px solid var(--violet2);outline-offset:2px}
 button.secondary{width:100%;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);
  background:var(--raised);color:var(--text);font-size:15px;font-weight:600}
 .picker-btn{width:100%;display:flex;align-items:center;justify-content:space-between;gap:8px;
  padding:11px 14px;border:1px solid var(--line);border-radius:var(--radius);background:var(--ink2);
  color:var(--text);font:inherit;font-size:15px;text-align:left}
 .picker-btn[aria-expanded="true"]{border-color:var(--violet);box-shadow:0 0 0 3px var(--soft)}
 .picker-btn .chev{color:var(--faint)}
 .more-btn{color:var(--muted)}
 .more-panel{display:flex;flex-direction:column;gap:9px;margin-top:9px;padding:12px;
  border:1px solid var(--line);border-radius:var(--radius);background:rgba(21,26,36,0.5)}
 .picker-sheet{display:flex;position:fixed;inset:0;background:rgba(5,7,12,0.68);z-index:25;
  align-items:flex-end;backdrop-filter:blur(3px);opacity:0;visibility:hidden;
  transition:opacity .2s ease,visibility 0s linear .2s}
 .picker-sheet.open{opacity:1;visibility:visible;transition:opacity .2s ease}
 .picker-sheet .sheet-panel{background:var(--panel);border:1px solid var(--line);border-radius:16px 16px 0 0;
  width:100%;max-height:80vh;overflow:auto;padding:16px;
  padding-bottom:calc(16px + env(safe-area-inset-bottom));
  transform:translateY(100%);transition:transform .22s ease}
 .picker-sheet.open .sheet-panel{transform:none}
 .sheet-title{font-family:var(--serif);font-weight:550;margin-bottom:10px;font-size:18px}
 .sheet-row{display:flex;align-items:center;gap:8px;width:100%;padding:12px 8px;border:0;background:none;
  color:var(--text);font:inherit;font-size:15px;text-align:left;border-radius:9px}
 .sheet-row.selected{background:var(--soft);color:var(--violet2)}
 .sheet-row .sr-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
 .sheet-row .sr-count{font-family:var(--mono);font-size:12px;color:var(--faint)}
 .sheet-row.selected .sr-count{color:var(--violet2)}
 .sheet-twisty{flex-shrink:0;width:28px;height:28px;min-height:28px;border:0;background:none;color:var(--faint);
  font-size:12px;border-radius:8px}
 .sheet-twisty.leaf{visibility:hidden}
 .sheet-twisty.expanded{transform:rotate(90deg)}
 .rc-top{display:flex;align-items:flex-start;gap:10px}
 .rc-main{flex:1;min-width:0}
 .c-title{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
 .c-desc{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
 .rc-actions{display:flex;gap:4px;flex-shrink:0}
 .qa{width:32px;height:32px;min-height:32px;border:1px solid transparent;background:transparent;
  color:var(--faint);border-radius:8px;font-size:14px;display:flex;align-items:center;justify-content:center}
 .qa:active{background:rgba(255,255,255,0.07);color:var(--violet2)}
 .qa.ok{color:#5fd39a;border-color:transparent;background:rgba(95,211,154,.14)}
 .tag-more{color:var(--faint)}
 .src-label strong{color:var(--text)}
 .open-orig{display:inline-block;margin-left:8px;padding:5px 11px;border:1px solid var(--line);
  border-radius:999px;background:var(--raised);color:var(--violet2);font-size:13px}
 .src-list div{padding:7px 0;border-bottom:1px solid var(--line)}
 .src-list div:last-child{border-bottom:0}
 .toast{position:fixed;left:50%;bottom:calc(80px + env(safe-area-inset-bottom));
  transform:translateX(-50%) translateY(10px);background:var(--panel);border:1px solid var(--line);
  color:var(--text);padding:10px 15px;border-radius:12px;font-size:14px;z-index:40;opacity:0;
  pointer-events:none;transition:opacity .2s,transform .2s;box-shadow:0 12px 30px rgba(0,0,0,.5)}
 .toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
 .toast.err{border-color:rgba(255,128,149,.4);color:#ff8095}
 .event{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px;
  margin-bottom:11px;border-left:3px solid var(--line)}
 .event.saved{border-left-color:#5fd39a}.event.merged{border-left-color:#7fb4ff}
 .event.needs_input{border-left-color:#e9b26a}.event.failed{border-left-color:#ff8095}
 .ev-badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600}
 .b-ok{background:rgba(95,211,154,.14);color:#5fd39a}.b-info{background:var(--soft);color:var(--violet2)}
 .b-warn{background:rgba(233,178,106,.14);color:#e9b26a}.b-err{background:rgba(255,128,149,.14);color:#ff8095}
 .ev-time{color:var(--faint);font-size:12px;font-family:var(--mono);margin-left:6px}
 .ev-title{font-family:var(--serif);font-weight:550;font-size:16px;margin-top:8px}
 .ev-reason{color:var(--muted);font-size:13px;margin-top:6px}
 .ev-cat{color:var(--faint);font-size:12px;margin-top:2px}
 .glegend{position:absolute;left:10px;bottom:calc(64px + env(safe-area-inset-bottom));
  background:rgba(13,16,23,.85);border:1px solid var(--line);border-radius:10px;padding:8px 10px;
  font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:5px;backdrop-filter:blur(6px)}
 .glegend .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
 .glegend .ring{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;
  vertical-align:middle;background:#67dfe8;box-shadow:0 0 6px rgba(103,223,232,.8)}
 .gmsg{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;
  justify-content:center;color:var(--muted);text-align:center;padding:24px;gap:12px}
 .editor-note{color:var(--faint);font-size:13px;margin:0 0 8px}
 #add-box{border:none;background:transparent;font-family:var(--serif);font-size:19px;line-height:1.5;
  padding:12px 2px;min-height:180px;box-shadow:none}
 #add-box:focus{box-shadow:none;border:none}
 @media (prefers-reduced-motion: reduce){*{transition-duration:0.01ms !important}}
</style></head>
<body>
<header>
  <svg width="26" height="26" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <circle cx="16" cy="16" r="15" fill="#151a24" stroke="#67dfe8" stroke-opacity="0.35"/>
    <line x1="16" y1="16" x2="8" y2="9" stroke="#67dfe8" stroke-opacity="0.45"/>
    <line x1="16" y1="16" x2="24" y2="11" stroke="#67dfe8" stroke-opacity="0.45"/>
    <line x1="16" y1="16" x2="23" y2="22" stroke="#67dfe8" stroke-opacity="0.45"/>
    <circle cx="8" cy="9" r="2" fill="#3f6f82"/><circle cx="24" cy="11" r="2" fill="#3f6f82"/>
    <circle cx="23" cy="22" r="2.4" fill="#67dfe8"/><circle cx="16" cy="16" r="3.2" fill="#a9f0f6"/>
  </svg>
  <span class="bn">Knowledge Vault</span>
  <button class="icon-btn" id="refresh" aria-label="Refresh library">↻</button>
</header>
<main>
  <section id="tab-recent" style="display:none">
    <div id="recent-list"></div>
  </section>
  <section id="tab-library" style="display:none">
    <div class="filters">
      <input type="text" id="f-search" placeholder="Search your notes…" aria-label="Search notes"
        autocomplete="off" spellcheck="false">
      <button type="button" class="picker-btn" id="cat-picker-btn" aria-haspopup="dialog" aria-expanded="false">
        <span id="cat-current">All categories</span><span class="chev" aria-hidden="true">▾</span></button>
      <button type="button" class="picker-btn" id="plat-picker-btn" aria-haspopup="dialog" aria-expanded="false">
        <span id="plat-current">All sources</span><span class="chev" aria-hidden="true">▾</span></button>
      <button type="button" class="picker-btn more-btn" id="more-btn" aria-expanded="false">
        <span>More filters</span><span class="chev" aria-hidden="true">▾</span></button>
      <div class="more-panel" id="more-panel" style="display:none">
        <button type="button" class="picker-btn" id="tag-picker-btn" aria-haspopup="dialog" aria-expanded="false">
          <span id="tag-current">All tags</span><span class="chev" aria-hidden="true">▾</span></button>
        <label class="toggle"><input type="checkbox" id="f-done"> Show done items</label>
      </div>
    </div>
    <div id="card-list"></div>
  </section>
  <section id="tab-graph" style="display:none">
    <div class="graph-holder">
      <canvas id="gcanvas" aria-label="Knowledge graph"></canvas>
      <div class="gbar">
        <label class="toggle" style="background:rgba(21,26,36,0.85);padding:8px 10px;border-radius:10px;">
          <input type="checkbox" id="g-archived"> Archived</label>
      </div>
      <div class="glegend" aria-hidden="true">
        <div><span class="ring"></span> Category</div>
        <div><span class="dot" style="background:#4e8ba3"></span> Note</div>
        <div><span class="dot" style="background:#333d55"></span> Done / archived</div>
      </div>
      <div class="gcluster" role="group" aria-label="Graph controls">
        <button id="g-zin" aria-label="Zoom in">+</button>
        <button id="g-zout" aria-label="Zoom out">−</button>
        <button id="g-reset" aria-label="Reset graph view">⤢</button>
      </div>
      <div class="ghint">Drag · Pinch · Tap a node</div>
      <div class="gmsg" id="gmsg" style="display:none">
        <p>Your graph is empty — nothing saved yet.</p>
        <button class="secondary" style="width:auto;padding:10px 16px" onclick="showTab('add')">Add your first link</button>
      </div>
    </div>
  </section>
  <section id="tab-add" style="display:none">
    <p class="editor-note">Paste a link or text, or share to this app from Instagram / TikTok /
    YouTube. It is processed on your PC and shows up in your library.</p>
    <textarea id="add-box" placeholder="Start typing or paste a link here…" aria-label="Link or text to save"></textarea>
    <button class="primary" onclick="sendAdd()">Save to vault</button>
    <p class="c-meta" id="add-msg" style="font-family:system-ui"></p>
    <p class="editor-note" style="margin-top:10px">Tip: install this page (browser
    menu, Add to Home screen) so "Knowledge Vault" appears in your share sheet.</p>
  </section>
</main>
<nav class="tabbar">
  <button id="nav-recent" class="active" onclick="showTab('recent')"><span class="tico" aria-hidden="true">✦</span>Recently added</button>
  <button id="nav-library" onclick="showTab('library')"><span class="tico" aria-hidden="true">◈</span>Library</button>
  <button id="nav-graph" onclick="showTab('graph')"><span class="tico" aria-hidden="true">✧</span>Graph</button>
  <button id="nav-add" onclick="showTab('add')"><span class="tico" aria-hidden="true">＋</span>Add</button>
</nav>
<div id="detail" onclick="if(event.target===this)closeDetail()">
  <div class="sheet">
    <button class="close" onclick="closeDetail()">Close</button>
    <div id="detail-body"></div>
  </div>
</div>
<div id="picker-sheet" class="picker-sheet" onclick="if(event.target===this)closeSheet()">
  <div class="sheet-panel"><div class="sheet-title" id="sheet-title"></div><div id="sheet-body"></div></div>
</div>
<div id="toast" class="toast" role="status" aria-live="polite"></div>
<script src="/app.js"></script>
</body></html>`;
}

// Client app. IMPORTANT: no backticks and no ${...} in here — this whole string
// is itself embedded in a template literal on the PC side / worker responses.
const APP_JS = `(function(){
  var qs = new URLSearchParams(location.search);
  if (qs.get('token')) localStorage.setItem('kv_token', qs.get('token'));
  var TOKEN = localStorage.getItem('kv_token') || '';
  var NL = String.fromCharCode(10);
  var cards = [];
  var events = [];
  var filter = { cat: '', platform: '', tag: '' };
  function esc(s){ s=(s==null?'':String(s));
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function el(id){ return document.getElementById(id); }
  function byId(id){ for(var i=0;i<cards.length;i++){ if(cards[i].id===id) return cards[i]; } return null; }
  function cap(s){ s=String(s||''); return s? s.charAt(0).toUpperCase()+s.slice(1): s; }

  // ---------------------------------------------------------- tabs (R59)
  function showTab(name){
    ['recent','library','graph','add'].forEach(function(n){
      el('tab-'+n).style.display = (n===name)?'block':'none';
      el('nav-'+n).className = (n===name)?'active':'';
    });
    if(name==='recent') loadEvents();
    if(name==='library') loadCards();
    if(name==='graph'){
      if(cards.length){ gResize(); buildGraph(); }
      else loadCards().then(function(){ gResize(); buildGraph(); });
    }
  }
  window.showTab = showTab;

  // ---------------------------------------------------------- toast (R13)
  var toastT = null;
  function toast(msg, isErr){ var t=el('toast'); t.textContent=msg;
    t.className='toast'+(isErr?' err':''); requestAnimationFrame(function(){ t.classList.add('show'); });
    clearTimeout(toastT); toastT=setTimeout(function(){ t.classList.remove('show'); }, 2200); }

  // ---------------------------------------------------------- data loads
  async function loadCards(){
    var list = el('card-list');
    if(!TOKEN){ list.innerHTML='<p class="msg">Open this page once using the link from your PC setup to connect it.</p>'; return; }
    if(!cards.length) list.innerHTML='<p class="msg">Loading…</p>';
    try{
      var r = await fetch('/cards?token='+encodeURIComponent(TOKEN));
      if(r.status===401){ list.innerHTML='<p class="msg">Wrong or missing token. Re-open via the PC link.</p>'; return; }
      var data = await r.json();
      cards = data.cards || [];
      render();
    }catch(e){ list.innerHTML='<p class="msg">Could not load your notes. Check your connection.</p>'; }
  }
  async function loadEvents(){
    var list = el('recent-list');
    if(!TOKEN){ list.innerHTML='<p class="msg">Open this page once using the link from your PC setup to connect it.</p>'; return; }
    list.innerHTML='<p class="msg">Loading…</p>';
    try{
      var r = await fetch('/events?token='+encodeURIComponent(TOKEN));
      if(r.status===401){ list.innerHTML='<p class="msg">Wrong or missing token. Re-open via the PC link.</p>'; return; }
      var data = await r.json();
      events = data.events || [];
      renderEvents();
    }catch(e){ list.innerHTML='<p class="msg">Could not load recent activity. Check your connection.</p>'; }
  }

  // ------------------------------------------- recently added tab (R59-R62)
  function renderEvents(){
    var list = el('recent-list');
    if(!events.length){ list.innerHTML='<p class="msg">No notes yet. Share a reel, article, or video to start building your vault.</p>'; return; }
    list.innerHTML = events.map(function(e){
      var badge, cls='';
      if(e.state==='saved' && e.result_kind==='already_saved'){ badge='<span class="ev-badge b-info">already saved</span>'; cls='saved'; }
      else if(e.state==='saved'){ badge='<span class="ev-badge b-ok">saved</span>'; cls='saved'; }
      else if(e.state==='merged'){ badge='<span class="ev-badge b-info">merged</span>'; cls='merged'; }
      else if(e.state==='needs_input'){ badge='<span class="ev-badge b-warn">needs input</span>'; cls='needs_input'; }
      else if(e.state==='failed'){ badge='<span class="ev-badge b-err">failed</span>'; cls='failed'; }
      else { badge='<span class="ev-badge">waiting</span>'; }
      var time = (e.updated_at||'').slice(0,16).replace('T',' ');
      var titleRow;
      if(e.item_id && e.item_title){
        titleRow='<div class="ev-title" onclick="openEventCard('+e.item_id+')" style="cursor:pointer">'+esc(e.item_title)+'</div>'+
          (e.item_category?'<div class="ev-cat">'+esc(e.item_category)+'</div>':'');
      } else {
        titleRow='<div class="ev-title">'+esc(e.preview||'')+'</div>';
      }
      var reason = ((e.state==='failed'||e.state==='needs_input') && e.reason) ?
        '<div class="ev-reason">'+esc(e.reason)+' Open the PC dashboard to resolve it.</div>' : '';
      return '<div class="event '+cls+'"><div>'+badge+'<span class="ev-time">'+esc(time)+'</span></div>'+titleRow+reason+'</div>';
    }).join('');
  }

  // ----------------------------------------- category tree from cards (R3-R5)
  function buildCatTree(){
    var byPath = {};
    function ensure(path){
      if(byPath[path]) return byPath[path];
      var parts = path.split('/');
      var node = { path:path, name:parts[parts.length-1], depth:parts.length-1, children:[], count:0 };
      byPath[path] = node;
      if(parts.length>1){ ensure(parts.slice(0,-1).join('/')).children.push(node); }
      return node;
    }
    cards.forEach(function(c){ if(c.category_path) ensure(c.category_path); });
    Object.keys(byPath).forEach(function(p){
      byPath[p].count = cards.filter(function(c){
        return c.category_path===p || (c.category_path||'').indexOf(p+'/')===0; }).length;
    });
    var tops = [];
    Object.keys(byPath).forEach(function(p){ if(byPath[p].depth===0) tops.push(byPath[p]); });
    function sortRec(n){ n.children.sort(function(a,b){ return a.name.localeCompare(b.name); }); n.children.forEach(sortRec); }
    tops.sort(function(a,b){ return a.name.localeCompare(b.name); });
    tops.forEach(sortRec);
    return tops;
  }

  // --------------------------------------- bottom-sheet pickers (R1,R36,R39)
  function openSheet(){ el('picker-sheet').classList.add('open'); }
  function closeSheet(){ el('picker-sheet').classList.remove('open'); }
  window.closeSheet = closeSheet;

  function simpleRow(path, label, count, onclick, selected){
    var row = document.createElement('button'); row.type='button';
    row.className = 'sheet-row'+(selected?' selected':''); row.dataset.path = path;
    row.innerHTML = '<span class="sheet-twisty leaf"></span>';
    var nm = document.createElement('span'); nm.className='sr-name'; nm.textContent=label; row.appendChild(nm);
    if(count!=null){ var ct=document.createElement('span'); ct.className='sr-count'; ct.textContent=count; row.appendChild(ct); }
    row.addEventListener('click', onclick);
    return row;
  }
  function catNodeEl(n){
    var wrap = document.createElement('div');
    var row = document.createElement('div'); row.className='sheet-row'; row.dataset.path=n.path;
    row.style.paddingLeft = (8 + n.depth*16) + 'px';
    var tw = document.createElement('button'); tw.type='button';
    tw.className = 'sheet-twisty'+(n.children.length?'':' leaf'); tw.textContent='▸';
    tw.setAttribute('aria-label','Expand '+n.name);
    var nm = document.createElement('span'); nm.className='sr-name'; nm.textContent=n.name;
    var ct = document.createElement('span'); ct.className='sr-count'; ct.textContent=n.count;
    row.appendChild(tw); row.appendChild(nm); row.appendChild(ct);
    var kids = document.createElement('div'); kids.style.display='none';
    n.children.forEach(function(ch){ kids.appendChild(catNodeEl(ch)); });
    tw.addEventListener('click', function(ev){ ev.stopPropagation();
      var opening = kids.style.display==='none'; kids.style.display = opening?'block':'none';
      tw.classList.toggle('expanded', opening); });
    row.addEventListener('click', function(){ filter.cat=n.path; el('cat-current').textContent=n.path; closeSheet(); render(); });
    wrap.appendChild(row); wrap.appendChild(kids);
    return wrap;
  }
  function openCatPicker(){
    el('sheet-title').textContent='Category';
    var body = el('sheet-body'); body.innerHTML='';
    body.appendChild(simpleRow('', 'All categories', null, function(){
      filter.cat=''; el('cat-current').textContent='All categories'; closeSheet(); render(); }, filter.cat===''));
    buildCatTree().forEach(function(n){ body.appendChild(catNodeEl(n)); });
    body.querySelectorAll('.sheet-row').forEach(function(r){ r.classList.toggle('selected', r.dataset.path===filter.cat); });
    openSheet();
  }
  function openPlatPicker(){
    el('sheet-title').textContent='Source';
    var body = el('sheet-body'); body.innerHTML='';
    var plats = {}; cards.forEach(function(c){ if(c.platform) plats[c.platform]=(plats[c.platform]||0)+1; });
    body.appendChild(simpleRow('', 'All sources', null, function(){
      filter.platform=''; el('plat-current').textContent='All sources'; closeSheet(); render(); }, filter.platform===''));
    Object.keys(plats).sort().forEach(function(p){
      body.appendChild(simpleRow(p, cap(p), plats[p], function(){
        filter.platform=p; el('plat-current').textContent=cap(p); closeSheet(); render(); }, filter.platform===p));
    });
    openSheet();
  }
  function openTagPicker(){
    el('sheet-title').textContent='Tag';
    var body = el('sheet-body'); body.innerHTML='';
    var tags = {}; cards.forEach(function(c){ (c.tags||[]).forEach(function(t){ tags[t]=(tags[t]||0)+1; }); });
    body.appendChild(simpleRow('', 'All tags', null, function(){
      filter.tag=''; el('tag-current').textContent='All tags'; closeSheet(); render(); }, filter.tag===''));
    Object.keys(tags).sort().forEach(function(t){
      body.appendChild(simpleRow(t, '#'+t, tags[t], function(){
        filter.tag=t; el('tag-current').textContent='#'+t; closeSheet(); render(); }, filter.tag===t));
    });
    openSheet();
  }

  // ---------------------------------------------- library render (R9-R16,R40)
  function matches(c,q){
    if(!q) return true;
    var hay = (c.title+' '+c.short_description+' '+(c.tags||[]).join(' ')+' '+
      (c.main_points||[]).map(function(p){return p.name+' '+p.description;}).join(' ')).toLowerCase();
    return hay.indexOf(q)>=0;
  }
  function emptyMsg(showDone){
    if(!cards.length) return 'No notes yet. Share a reel, article, or video to start building your vault.';
    if(showDone && !cards.some(function(c){ return c.status==='done'; })) return 'No archived notes yet.';
    var q = el('f-search').value.trim();
    if(filter.cat && !q && !filter.platform && !filter.tag) return 'No notes in this category.';
    return 'Nothing found. Try another search or filter.';
  }
  function cardHtml(c){
    var tags = (c.tags||[]);
    var chips = tags.slice(0,3).map(function(t){ return '<span class="tag">#'+esc(t)+'</span>'; });
    if(tags.length>3) chips.push('<span class="tag tag-more">+'+(tags.length-3)+'</span>');
    var doneBtn = c.status==='done' ? '' :
      '<button class="qa" data-act="done" aria-label="Mark as done" title="Done">✓</button>';
    // Stitch meta line: "date · #tag1 #tag2" (category/platform live in the filters + detail sheet)
    var meta = esc(c.date_saved||'')+(chips.length?' · '+chips.join(' '):'');
    var doneBadge = c.status==='done' ? ' <span class="ev-badge b-info">done</span>' : '';
    return '<div class="card" data-id="'+c.id+'">'+
      '<div class="rc-top"><div class="rc-main">'+
        '<div class="c-title">'+esc(c.title)+'</div>'+
        '<div class="c-meta">'+meta+doneBadge+'</div></div>'+
        '<div class="rc-actions">'+
          '<button class="qa" data-act="open" aria-label="Open" title="Open">↗</button>'+
          '<button class="qa" data-act="copy" aria-label="Copy" title="Copy">⧉</button>'+
          doneBtn+
        '</div></div>'+
      (c.short_description?'<div class="c-desc">'+esc(c.short_description)+'</div>':'')+
    '</div>';
  }
  function render(){
    var q = el('f-search').value.trim().toLowerCase();
    var showDone = el('f-done').checked;
    var list = el('card-list');
    var rows = cards.filter(function(c){
      if(!showDone && c.status==='done') return false;
      if(filter.cat && !(c.category_path===filter.cat || (c.category_path||'').indexOf(filter.cat+'/')===0)) return false;
      if(filter.platform && c.platform!==filter.platform) return false;
      if(filter.tag && (c.tags||[]).indexOf(filter.tag)<0) return false;
      return matches(c,q);
    });
    rows.sort(function(a,b){ return (b.date_saved||'').localeCompare(a.date_saved||'')||(b.id-a.id); });
    if(!rows.length){ list.innerHTML='<p class="msg">'+esc(emptyMsg(showDone))+'</p>'; return; }
    list.innerHTML = rows.map(cardHtml).join('');
  }

  // ------------------------------------------- card quick actions (R12-R14)
  function cardCopyText(title, desc, points, url){
    var lines = [title||''];
    if(desc){ lines.push(''); lines.push(desc); }
    if(points && points.length){ lines.push(''); lines.push('Main points:');
      points.forEach(function(p){ lines.push('- '+(p.name||'')+(p.description?': '+p.description:'')); }); }
    lines.push(''); lines.push('Source: '+(url||'Pasted text'));
    return lines.join(NL);
  }
  function copyCard(id, btn){
    var c = byId(id); if(!c) return;
    var text = cardCopyText(c.title, c.short_description, c.main_points, c.source_url);
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(text).then(function(){
        btn.classList.add('ok'); setTimeout(function(){ btn.classList.remove('ok'); }, 1200); toast('Copied ✓');
      }, function(){ toast("Couldn't copy — try selecting the text instead.", true); });
    } else { toast("Couldn't copy — try selecting the text instead.", true); }
  }
  function doneCard(id){
    var c = byId(id); if(!c) return;
    c.status = 'done';
    render();
    toast('Marked as done ✓');
    if(TOKEN){
      fetch('/cards/put?token='+encodeURIComponent(TOKEN), {
        method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(c)
      }).catch(function(){ toast('Saved on this device — reconnect to sync.', true); });
    }
  }
  document.addEventListener('click', function(e){
    var card = e.target.closest('.card'); if(!card) return;
    var id = Number(card.getAttribute('data-id'));
    var btn = e.target.closest('.qa');
    if(btn){ e.stopPropagation(); var act=btn.getAttribute('data-act');
      if(act==='open') openCard(id);
      else if(act==='copy') copyCard(id, btn);
      else if(act==='done') doneCard(id);
      return; }
    openCard(id);
  });

  // ------------------------------------------------ detail sheet (R17,R20)
  function openCard(id){
    var c = byId(id); if(!c) return;
    var pts = (c.main_points||[]).map(function(p){ return '<li><b>'+esc(p.name)+'</b>'+(p.description?' — '+esc(p.description):'')+'</li>'; }).join('');
    var srcLabel = c.source_label || cap(c.platform||'');
    var srcLine = '<span class="src-label">Source: <strong>'+esc(srcLabel)+'</strong></span>'+
      (c.source_url?'<a class="open-orig" href="'+esc(c.source_url)+'" target="_blank" rel="noopener">Open original ↗</a>':'');
    var add = (c.additional_sources||[]).map(function(s){
      var u = (s && s.url) ? s.url : s; var lab = (s && s.label) ? s.label : '';
      return '<div><span class="src-label"><strong>'+esc(lab)+'</strong></span> '+
        '<a class="open-orig" href="'+esc(u)+'" target="_blank" rel="noopener">Open original ↗</a></div>';
    }).join('');
    var rel = (c.related||[]).map(function(t){ return '<li>'+esc(t)+'</li>'; }).join('');
    el('detail-body').innerHTML =
      '<h2>'+esc(c.title)+'</h2>'+
      '<div class="c-meta">'+esc(c.category_path||'')+' · '+esc(c.platform||'')+' · '+esc(c.date_saved||'')+' · '+esc(c.extraction_status||'')+'</div>'+
      '<h3>Main points</h3><ol>'+pts+'</ol>'+
      '<h3>Summary</h3><p>'+esc(c.short_description||'')+'</p>'+
      '<h3>Source</h3><p>'+srcLine+'</p>'+(add?'<div class="src-list">'+add+'</div>':'')+
      (rel?'<h3>Related notes</h3><ul>'+rel+'</ul>':'');
    el('detail').classList.add('open');
  }
  window.openCard = openCard;
  // Recently-added links may fire before the library has loaded its cards (R61);
  // fetch them on demand so the detail sheet always opens.
  window.openEventCard = function(id){
    if(byId(id)){ openCard(id); return; }
    loadCards().then(function(){ if(byId(id)) openCard(id); });
  };
  window.closeDetail = function(){ el('detail').classList.remove('open'); };

  // -------------------------------------------------------------- add
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
    alpha: 0, running: false, drag: null, dragged: false, pan: false, peek: null,
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

  function gTrunc(s){ if(s.length<=28) return s; var cut=s.slice(0,28); var sp=cut.lastIndexOf(' ');
    if(sp>16) cut=cut.slice(0,sp); return cut.replace(/[ ,.;:!?-]+$/,'')+'…'; }

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
    G.nb = {}; G.peek = null;
    nodes.forEach(function(n){ n.x = gW()/2 + (Math.random()-0.5)*260; n.y = gH()/2 + (Math.random()-0.5)*260;
      n.vx=0; n.vy=0; n.deg=0; G.nb[n.id] = new Set(); });
    links.forEach(function(l){ by[l.s].deg++; by[l.t].deg++; G.nb[l.s].add(l.t); G.nb[l.t].add(l.s); });
    G.nodes = nodes; G.links = links; G.by = by; G.built = true;
    el('gmsg').style.display = nodes.length ? 'none' : 'flex';
    if(!nodes.length){ gRender(); return; }
    if(reduce){ for(var i=0;i<300;i++) gStep(0.9); gFit(); gRender(); }
    else { G.alpha = 1; gFit(); gStartLoop(); }
  }
  function gRadius(n){ var b = n.type==='cat'?8:3.2;
    return b + Math.min(7, Math.sqrt(n.deg)*(n.type==='cat'?2.4:1.2)); }
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
    var active = G.peek; var hi = null;
    if(active){ hi = {}; hi[active.id]=1; (G.nb[active.id]||new Set()).forEach(function(x){ hi[x]=1; }); }
    G.links.forEach(function(l){ var s=G.by[l.s],t=G.by[l.t];
      var on = hi && (l.s===active.id || l.t===active.id);
      if(hi && !on) gctx.strokeStyle='rgba(170,182,216,0.05)';
      else if(on) gctx.strokeStyle='rgba(169,240,246,0.8)';
      else gctx.strokeStyle=l.rel?'rgba(103,223,232,0.25)':'rgba(170,182,216,0.14)';
      gctx.lineWidth=(on?1.6:0.9)/G.view.k; gctx.beginPath(); gctx.moveTo(s.x,s.y); gctx.lineTo(t.x,t.y); gctx.stroke(); });
    G.nodes.forEach(function(n){ var r=gRadius(n), done=n.status==='done'; var dim = hi && !hi[n.id];
      gctx.globalAlpha = dim?0.25:1;
      if(n===active && !dim){
        var glow = gctx.createRadialGradient(n.x,n.y,r,n.x,n.y,r+16/G.view.k);
        glow.addColorStop(0,'rgba(103,223,232,0.5)'); glow.addColorStop(1,'rgba(103,223,232,0)');
        gctx.beginPath(); gctx.arc(n.x,n.y,r+16/G.view.k,0,6.2832); gctx.fillStyle=glow; gctx.fill();
      } else if(hi && hi[n.id] && !dim){ gctx.beginPath(); gctx.arc(n.x,n.y,r+4/G.view.k+3,0,6.2832);
        gctx.fillStyle='rgba(103,223,232,0.18)'; gctx.fill(); }
      gctx.beginPath(); gctx.arc(n.x,n.y,r,0,6.2832);
      gctx.fillStyle= done?'#333d55':(n.type==='cat'?'#67dfe8':'#4e8ba3'); gctx.fill();
      gctx.lineWidth=1/G.view.k; gctx.strokeStyle='rgba(13,16,23,0.9)'; gctx.stroke();
      if(n.type==='cat'){ gctx.beginPath(); gctx.arc(n.x,n.y,r+3.5/G.view.k,0,6.2832);
        gctx.lineWidth=1.6/G.view.k; gctx.strokeStyle=done?'rgba(51,61,85,0.9)':'rgba(103,223,232,0.5)'; gctx.stroke(); }
      gctx.globalAlpha=1; });
    gctx.textAlign='center'; gctx.textBaseline='top';
    G.nodes.forEach(function(n){ var isCat=n.type==='cat'; var isActive=n===active;
      var show = isCat || G.view.k>1.2 || isActive || (active && (G.nb[active.id]||new Set()).has(n.id));
      if(!show) return;
      if(hi && !hi[n.id] && G.view.k<=1.2 && !isCat) return;
      var r=gRadius(n), size=(isCat?11:10)/G.view.k;
      gctx.font=(isCat?'600 ':'')+size+'px system-ui,sans-serif';
      var lab = isActive ? n.label : gTrunc(n.label);
      gctx.globalAlpha = hi && !hi[n.id] ? 0.2 : (isCat?0.95:0.8);
      gctx.lineWidth=3/G.view.k; gctx.strokeStyle='rgba(13,16,23,0.85)';
      gctx.strokeText(lab,n.x,n.y+r+3/G.view.k);
      gctx.fillStyle=isCat?'#bfeff4':'#c3cadf'; gctx.fillText(lab,n.x,n.y+r+3/G.view.k);
      gctx.globalAlpha=1; });
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
      if(!G.dragged){ if(G.drag) gTap(G.drag); else gTap(null); }
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
  // Two-step tap: peek (center/zoom + highlight) then commit (open/filter) (R24).
  function gTap(n){ if(!n){ if(G.peek){ G.peek=null; gRender(); } return; }
    if(G.peek && G.peek.id===n.id){ gCommit(n); return; }
    G.peek=n; gAnimateTo(n.x,n.y,Math.max(G.view.k,1.6)); gRender(); }
  function gCommit(n){ if(n.type==='note'){ openCard(n.card.id); }
    else { filter.cat=n.path; el('cat-current').textContent=n.path; showTab('library'); render(); } }
  function gAnimateTo(wx,wy,k){ var tx=gW()/2-wx*k, ty=gH()/2-wy*k;
    if(reduce){ G.view.x=tx; G.view.y=ty; G.view.k=k; gRender(); return; }
    var f={x:G.view.x,y:G.view.y,k:G.view.k}, t0=performance.now(), dur=320;
    (function frame(t){ var p=Math.min(1,(t-t0)/dur), e=1-Math.pow(1-p,3);
      G.view.x=f.x+(tx-f.x)*e; G.view.y=f.y+(ty-f.y)*e; G.view.k=f.k+(k-f.k)*e; gRender();
      if(p<1) requestAnimationFrame(frame); })(performance.now()); }
  // Reset re-centers and clears any active peek (R25).
  el('g-reset').addEventListener('click', function(){ G.peek=null; gFit(); gRender(); });
  el('g-zin').addEventListener('click', function(){ gZoom(gW()/2, gH()/2, 1.3); });
  el('g-zout').addEventListener('click', function(){ gZoom(gW()/2, gH()/2, 1/1.3); });
  el('g-archived').addEventListener('change', buildGraph);

  el('f-search').addEventListener('input', render);
  el('f-done').addEventListener('change', render);
  el('cat-picker-btn').addEventListener('click', openCatPicker);
  el('plat-picker-btn').addEventListener('click', openPlatPicker);
  el('tag-picker-btn').addEventListener('click', openTagPicker);
  el('more-btn').addEventListener('click', function(){ var pnl=el('more-panel');
    var opening = pnl.style.display==='none'; pnl.style.display = opening?'flex':'none';
    el('more-btn').setAttribute('aria-expanded', opening?'true':'false'); });
  el('refresh').addEventListener('click', function(){ G.built=false;
    if(el('tab-recent').style.display!=='none') loadEvents(); else loadCards(); });
  if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
  showTab('recent');
})();`;

function manifest(token) {
  const t = token ? "?token=" + encodeURIComponent(token) : "";
  return {
    name: "Knowledge Vault",
    short_name: "Knowledge Vault",
    description: "Capture and browse your Knowledge Vault notes.",
    start_url: "/" + t,
    display: "standalone",
    background_color: "#0d1017",
    theme_color: "#0d1017",
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

      if (path === "/events") {
        // Recent-activity feed for the phone's "Recently added" tab (R60).
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const keys = await listAll(env, "event:");
        const events = await Promise.all(keys.map(async (k) => {
          const v = await env.INBOX.get(k.name);
          return v ? JSON.parse(v) : null;
        }));
        const list = events.filter(Boolean).sort((a, b) =>
          String(b.updated_at || "").localeCompare(String(a.updated_at || ""))).slice(0, 50);
        return Response.json({ events: list });
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
      if (path === "/events/put") {
        // PC publishes one terminal queue event to the "Recently added" feed (R60).
        if (!tokenOk(request, env)) return new Response("unauthorized", { status: 401 });
        const ev = await request.json();
        if (ev && ev.id != null) {
          await env.INBOX.put("event:" + ev.id, JSON.stringify(ev));
          // Keep the feed bounded: queue ids grow monotonically, so pruning by
          // numeric id keeps the newest N and stops KV growing forever.
          const keys = await listAll(env, "event:");
          if (keys.length > 100) {
            const ids = keys.map((k) => Number(k.name.slice(6))).sort((a, b) => b - a);
            for (const id of ids.slice(100)) await env.INBOX.delete("event:" + id);
          }
        }
        return Response.json({ ok: true });
      }
    }
    return new Response("not found", { status: 404 });
  },
};
