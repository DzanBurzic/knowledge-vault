/* Knowledge graph — a force-directed constellation of notes and categories.
   Original canvas implementation: repulsion + link springs + gravity, with
   pan / zoom / drag, hover-to-highlight neighbors, and click-to-open. */

(function () {
  const canvas = document.getElementById("graph");
  const ctx = canvas.getContext("2d");
  const search = document.getElementById("graph-search");
  const archivedToggle = document.getElementById("graph-archived");
  const resetBtn = document.getElementById("graph-reset");
  const countEl = document.getElementById("graph-count");
  const emptyEl = document.getElementById("graph-empty");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let nodes = [], links = [], byId = {}, neighbors = {};
  let view = { x: 0, y: 0, k: 1 };
  let alpha = 0, running = false;
  let hover = null, dragNode = null, dragged = false;
  let panning = false, last = { x: 0, y: 0 };
  let dpr = Math.max(1, window.devicePixelRatio || 1);

  // --------------------------------------------------------------- sizing
  function resize() {
    dpr = Math.max(1, window.devicePixelRatio || 1);
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.round(r.width * dpr);
    canvas.height = Math.round(r.height * dpr);
    render();
  }
  window.addEventListener("resize", resize);

  function W() { return canvas.width / dpr; }
  function H() { return canvas.height / dpr; }

  // --------------------------------------------------------------- data
  async function load() {
    const inc = archivedToggle.checked ? "1" : "0";
    const r = await fetch("/api/graph?include_archived=" + inc);
    const data = await r.json();
    byId = {}; neighbors = {};
    nodes = data.nodes.map((n) => {
      const node = Object.assign({}, n, {
        x: W() / 2 + (Math.random() - 0.5) * 300,
        y: H() / 2 + (Math.random() - 0.5) * 300,
        vx: 0, vy: 0, deg: 0,
      });
      byId[node.id] = node; neighbors[node.id] = new Set();
      return node;
    });
    links = data.links.filter((l) => byId[l.source] && byId[l.target]);
    links.forEach((l) => {
      byId[l.source].deg++; byId[l.target].deg++;
      neighbors[l.source].add(l.target); neighbors[l.target].add(l.source);
    });
    countEl.textContent = nodes.length
      ? nodes.length + " nodes · " + links.length + " links" : "";
    emptyEl.style.display = nodes.length ? "none" : "";
    if (!nodes.length) { render(); return; }

    if (reduceMotion) {
      for (let i = 0; i < 320; i++) step(0.9);
      fit(); render();
    } else {
      alpha = 1; fit(); start();
    }
  }

  function radius(n) {
    const base = n.type === "category" ? 6.5 : 3.6;
    return base + Math.min(7, Math.sqrt(n.deg) * (n.type === "category" ? 2.2 : 1.4));
  }

  // --------------------------------------------------------------- physics
  function step(a) {
    const REPULSE = 5200, SPRING = 0.035, LINK_LEN = 62, GRAVITY = 0.025;
    const cx = W() / 2, cy = H() / 2;
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      n.vx += (cx - n.x) * GRAVITY * a;
      n.vy += (cy - n.y) * GRAVITY * a;
      for (let j = i + 1; j < nodes.length; j++) {
        const m = nodes[j];
        let dx = n.x - m.x, dy = n.y - m.y;
        let d2 = dx * dx + dy * dy || 0.01;
        if (d2 > 90000) continue;
        const f = (REPULSE * a) / d2;
        const d = Math.sqrt(d2);
        const fx = (dx / d) * f, fy = (dy / d) * f;
        n.vx += fx; n.vy += fy; m.vx -= fx; m.vy -= fy;
      }
    }
    for (const l of links) {
      const s = byId[l.source], t = byId[l.target];
      let dx = t.x - s.x, dy = t.y - s.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const target = LINK_LEN * (l.kind === "hier" ? 1.5 : 1);
      const f = (d - target) * SPRING * a;
      const fx = (dx / d) * f, fy = (dy / d) * f;
      s.vx += fx; s.vy += fy; t.vx -= fx; t.vy -= fy;
    }
    for (const n of nodes) {
      if (n === dragNode) { n.vx = 0; n.vy = 0; continue; }
      n.x += n.vx *= 0.82;
      n.y += n.vy *= 0.82;
    }
  }

  function start() { if (!running) { running = true; requestAnimationFrame(loop); } }
  function loop() {
    if (alpha > 0.005) { step(alpha); alpha *= 0.985; render(); requestAnimationFrame(loop); }
    else { running = false; render(); }
  }
  function reheat(a) { alpha = Math.max(alpha, a); start(); }

  // --------------------------------------------------------------- view
  function fit() {
    if (!nodes.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      minX = Math.min(minX, n.x); maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y); maxY = Math.max(maxY, n.y);
    }
    const pad = 80;
    const k = Math.min(2, Math.max(0.2,
      Math.min(W() / (maxX - minX + pad), H() / (maxY - minY + pad))));
    view.k = k;
    view.x = W() / 2 - ((minX + maxX) / 2) * k;
    view.y = H() / 2 - ((minY + maxY) / 2) * k;
  }

  function toWorld(px, py) {
    return { x: (px - view.x) / view.k, y: (py - view.y) / view.k };
  }

  // --------------------------------------------------------------- render
  function render() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W(), H());
    ctx.setTransform(view.k * dpr, 0, 0, view.k * dpr, view.x * dpr, view.y * dpr);

    const hi = hover ? new Set([hover.id, ...neighbors[hover.id]]) : null;

    // links
    for (const l of links) {
      const s = byId[l.source], t = byId[l.target];
      const on = hi && (l.source === hover.id || l.target === hover.id);
      if (hi && !on) ctx.strokeStyle = "rgba(150,162,214,0.05)";
      else if (on) ctx.strokeStyle = "rgba(180,168,255,0.85)";
      else ctx.strokeStyle = l.kind === "related"
        ? "rgba(139,123,255,0.28)" : "rgba(150,162,214,0.16)";
      ctx.lineWidth = (on ? 1.6 : 0.9) / view.k;
      ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke();
    }

    // nodes
    for (const n of nodes) {
      const r = radius(n);
      const dim = hi && !hi.has(n.id);
      const done = n.status === "done";
      let color;
      if (done) color = "#3a4472";
      else color = n.type === "category" ? "#e9b26a" : "#8b7bff";
      ctx.globalAlpha = dim ? 0.25 : 1;
      if ((n === hover || (hi && hi.has(n.id))) && !dim) {
        ctx.beginPath(); ctx.arc(n.x, n.y, r + 4 / view.k + 3, 0, 6.2832);
        ctx.fillStyle = n.type === "category" ? "rgba(233,178,106,0.22)" : "rgba(139,123,255,0.22)";
        ctx.fill();
      }
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, 6.2832);
      ctx.fillStyle = color; ctx.fill();
      ctx.lineWidth = 1.2 / view.k; ctx.strokeStyle = "rgba(11,14,28,0.9)"; ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // labels — categories always; notes when zoomed in or highlighted
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    for (const n of nodes) {
      const isCat = n.type === "category";
      const show = isCat || view.k > 1.15 || (hover && (n === hover || neighbors[hover.id].has(n.id)));
      if (!show) continue;
      if (hi && !hi.has(n.id) && view.k <= 1.15 && !isCat) continue;
      const r = radius(n);
      const size = (isCat ? 12 : 10.5) / view.k;
      ctx.font = (isCat ? "600 " : "") + size + "px system-ui, sans-serif";
      const label = n.label.length > 34 ? n.label.slice(0, 33) + "…" : n.label;
      ctx.globalAlpha = hi && !hi.has(n.id) ? 0.2 : (isCat ? 0.95 : 0.8);
      ctx.fillStyle = "#0b0e1c";
      ctx.lineWidth = 3 / view.k; ctx.strokeStyle = "rgba(11,14,28,0.85)";
      ctx.strokeText(label, n.x, n.y + r + 3 / view.k);
      ctx.fillStyle = isCat ? "#f0d7ad" : "#c9ccea";
      ctx.fillText(label, n.x, n.y + r + 3 / view.k);
      ctx.globalAlpha = 1;
    }
  }

  // --------------------------------------------------------------- picking
  function nodeAt(px, py) {
    const w = toWorld(px, py);
    let best = null, bestD = Infinity;
    for (const n of nodes) {
      const r = radius(n) + 6 / view.k;
      const dx = n.x - w.x, dy = n.y - w.y, d = dx * dx + dy * dy;
      if (d < r * r && d < bestD) { best = n; bestD = d; }
    }
    return best;
  }

  // --------------------------------------------------------------- events
  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    const p = pos(e); dragged = false; last = p;
    const n = nodeAt(p.x, p.y);
    if (n) { dragNode = n; } else { panning = true; canvas.classList.add("grabbing"); }
  });

  canvas.addEventListener("pointermove", (e) => {
    const p = pos(e);
    if (dragNode) {
      const w = toWorld(p.x, p.y);
      dragNode.x = w.x; dragNode.y = w.y; dragNode.vx = 0; dragNode.vy = 0;
      dragged = true; reheat(0.35); render();
    } else if (panning) {
      view.x += p.x - last.x; view.y += p.y - last.y; last = p;
      dragged = true; render();
    } else {
      const n = nodeAt(p.x, p.y);
      if (n !== hover) { hover = n; canvas.style.cursor = n ? "pointer" : "grab"; render(); }
    }
  });

  function endPointer() {
    if (dragNode && !dragged) open(dragNode);
    dragNode = null; panning = false; canvas.classList.remove("grabbing");
  }
  canvas.addEventListener("pointerup", endPointer);
  canvas.addEventListener("pointercancel", endPointer);

  canvas.addEventListener("click", (e) => {
    if (dragged) return;
    const p = pos(e); const n = nodeAt(p.x, p.y);
    if (n) open(n);
  });

  function open(n) { if (n && n.url) window.location.href = n.url; }

  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const p = pos(e);
    const factor = Math.exp(-e.deltaY * 0.0016);
    const k2 = Math.min(6, Math.max(0.12, view.k * factor));
    // zoom toward cursor
    view.x = p.x - (p.x - view.x) * (k2 / view.k);
    view.y = p.y - (p.y - view.y) * (k2 / view.k);
    view.k = k2; render();
  }, { passive: false });

  // keyboard: focus a node result quickly
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    if (!q) { hover = null; render(); return; }
    const found = nodes.find((n) => n.label.toLowerCase().includes(q));
    if (found) {
      hover = found;
      view.k = Math.max(view.k, 1.4);
      view.x = W() / 2 - found.x * view.k;
      view.y = H() / 2 - found.y * view.k;
      render();
    }
  });
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && hover) open(hover);
  });

  archivedToggle.addEventListener("change", load);
  resetBtn.addEventListener("click", () => { hover = null; search.value = ""; fit(); render(); });

  resize();
  load();
})();
