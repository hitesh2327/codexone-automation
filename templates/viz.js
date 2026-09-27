// Data-structure visualizer shared by the carousel (static, pointers inline) and the
// reel (pointers rendered as separate sprites and animated in Python).
window.Viz = (() => {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const COLORS = ['var(--primary)', 'var(--accent)', '#7EE787', '#D2A8FF', '#FF9E64'];

  function pointerColor(visual, name) {
    const order = [];
    for (const st of visual.steps) for (const p of st.pointers || []) if (!order.includes(p.name)) order.push(p.name);
    return COLORS[Math.max(0, order.indexOf(name)) % COLORS.length];
  }

  function pointerEl(name, color, dir) {
    const el = document.createElement('div');
    el.className = 'viz-ptr' + (dir === 'left' ? ' left' : '');
    el.style.setProperty('--c', color);
    el.innerHTML = `<div class="tip"></div><div class="name">${esc(name)}</div>`;
    return el;
  }

  function stateValues(visual, step) {
    return step.values && step.values.length ? step.values : visual.values;
  }

  // Build the structure for one step. opts: {pointers, caption, maxWidth, cell}
  function build(root, visual, step, opts = {}) {
    root.innerHTML = '';
    const values = stateValues(visual, step);
    const hasCycle = visual.kind === 'linked_list' && visual.cycle_to >= 0 && visual.cycle_to < values.length;
    root.className = `viz viz-${visual.kind}` + (hasCycle ? ' has-cycle' : '');
    const hl = new Set(step.highlight || []), done = new Set(step.done || []);

    if (opts.caption !== false && step.caption) {
      const cap = document.createElement('div');
      cap.className = 'viz-caption';
      cap.textContent = step.caption;
      root.append(cap);
    }
    const row = document.createElement('div');
    row.className = 'viz-row';
    const cells = [];
    values.forEach((v, i) => {
      if (visual.kind === 'linked_list' && i > 0) {
        const a = document.createElement('div'); a.className = 'viz-arrow'; row.append(a);
      }
      const c = document.createElement('div');
      c.className = 'viz-cell' + (hl.has(i) ? ' hl' : done.has(i) ? ' done' : '');
      const showIdx = visual.kind === 'array' || visual.kind === 'string';
      c.innerHTML = `<span class="v">${esc(v)}</span>` + (showIdx ? `<span class="idx">${i}</span>` : '');
      row.append(c); cells.push(c);
    });
    if (visual.kind === 'linked_list') {
      const a = document.createElement('div'); a.className = 'viz-arrow'; row.append(a);
      if (!hasCycle) { const n = document.createElement('span'); n.className = 'viz-null'; n.textContent = 'null'; row.append(n); }
    }
    root.append(row);

    // Shrink cells until the row fits the available width.
    let cell = opts.cell || 96;
    const maxW = opts.maxWidth || root.parentElement.clientWidth;
    root.style.setProperty('--cell', cell + 'px');
    while (row.scrollWidth > maxW && cell > 40) { cell -= 4; root.style.setProperty('--cell', cell + 'px'); }

    if (hasCycle) drawCycle(root, row, cells, visual.cycle_to);

    const dir = visual.kind === 'stack' ? 'left' : 'up';
    const rootBox = root.getBoundingClientRect();
    const positions = cells.map(c => {
      const r = c.getBoundingClientRect();
      const idx = c.querySelector('.idx');
      const below = idx ? idx.getBoundingClientRect().bottom : r.bottom;
      return { cx: r.left + r.width / 2, cy: r.top + r.height / 2, bottom: below + 8, right: r.right + 10 };
    });

    if (opts.pointers) {
      const stacked = {};
      let lowest = 0;
      for (const p of step.pointers || []) {
        const pos = positions[p.index];
        if (!pos) continue;
        const k = stacked[p.index] = (stacked[p.index] ?? -1) + 1;
        const el = pointerEl(p.name, pointerColor(visual, p.name), dir);
        root.append(el);
        const b = el.getBoundingClientRect();
        if (dir === 'up') {
          el.style.left = (pos.cx - rootBox.left - b.width / 2) + 'px';
          el.style.top = (pos.bottom - rootBox.top + k * (b.height + 6)) + 'px';
          lowest = Math.max(lowest, pos.bottom - rootBox.top + (k + 1) * (b.height + 6));
        } else {
          el.style.left = (pos.right - rootBox.left + k * (b.width + 6)) + 'px';
          el.style.top = (pos.cy - rootBox.top - b.height / 2) + 'px';
        }
      }
      // Pointers are absolutely positioned; reserve their space so nothing overlaps them.
      root.style.paddingBottom = Math.max(0, lowest - rootBox.height) + 'px';
    }
    return { dir, positions };
  }

  // Tail → cycle_to drawn as an arc ABOVE the row (pointers live below it).
  function drawCycle(root, row, cells, to) {
    const rb = root.getBoundingClientRect();
    const tail = cells[cells.length - 1].getBoundingClientRect();
    const target = cells[to].getBoundingClientRect();
    const lastArrow = row.lastElementChild.getBoundingClientRect();
    const x1 = lastArrow.right - rb.left, y1 = tail.top + tail.height / 2 - rb.top;
    const x2 = target.left + target.width / 2 - rb.left, y2 = target.top - rb.top - 4;
    const top = tail.top - rb.top - tail.height * 0.6;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'cycle');
    svg.setAttribute('width', rb.width); svg.setAttribute('height', rb.height);
    svg.innerHTML = `
      <defs><marker id="ah" markerUnits="userSpaceOnUse" markerWidth="22" markerHeight="22" refX="11" refY="11" orient="auto">
        <path d="M0,2 L22,11 L0,20 z" fill="var(--accent)"/></marker></defs>
      <path d="M${x1},${y1} C${x1 + 30},${y1} ${x1 + 30},${top} ${x1 - 20},${top}
               L${x2 + 20},${top} C${x2},${top} ${x2},${top} ${x2},${y2 - 8}"
            fill="none" stroke="var(--accent)" stroke-width="4" stroke-dasharray="10 8" marker-end="url(#ah)"/>`;
    root.prepend(svg);
  }

  return { build, pointerEl, pointerColor };
})();
