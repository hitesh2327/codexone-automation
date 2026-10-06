// Shared diagram engine for v2 reels + carousels.
// makeDiagram(spec, W, H) lays the nodes out once; .draw(view, t) returns an SVG string.
// view = { states: {id: {state, note, since}}, flows: [{src, dst, tone, bad, alpha}] }
(function () {
  const TONE = {
    blue: '#3B82F6', green: '#22C55E', cyan: '#00E5FF', amber: '#FFB800', red: '#FF4D5E',
    purple: '#A78BFA', gray: '#8B949E', white: '#E6EDF3',
  };
  const HI = {
    blue: '#7DB3FF', green: '#7CF0A6', cyan: '#7DF3FF', amber: '#FFD36B', red: '#FF8A95',
    purple: '#C9B8FF', gray: '#C9D1D9', white: '#FFFFFF',
  };
  const MUTED = '#8B949E', LINE = 'rgba(255,255,255,.12)', CARD = 'rgba(22,27,34,.94)';
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const ROUND = new Set(['router', 'balancer', 'brain']);

  // ---- icons: drawn in a 48x48 box, stroke = color ------------------------------------
  function icon(name, c, a = 0) {
    const s = `fill="none" stroke="${c}" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"`;
    const f = `fill="${c}"`;
    switch (name) {
      case 'users': return `<g ${s}><circle cx="17" cy="16" r="6"/><path d="M6 38c1-8 6-12 11-12s10 4 11 12"/><circle cx="33" cy="18" r="5"/><path d="M30 27c6 0 11 4 12 11"/></g>`;
      case 'client': return `<g ${s}><rect x="6" y="8" width="36" height="24" rx="3"/><path d="M18 40h12M24 32v8"/></g>`;
      case 'phone': return `<g ${s}><rect x="14" y="5" width="20" height="38" rx="4"/></g><circle cx="24" cy="36" r="2.4" ${f}/>`;
      case 'server': return `<g ${s}><rect x="7" y="7" width="34" height="14" rx="3"/><rect x="7" y="27" width="34" height="14" rx="3"/></g><circle cx="14" cy="14" r="2.6" ${f}/><circle cx="14" cy="34" r="2.6" ${f}/>`;
      case 'router': case 'balancer': return `<g ${s}><path d="M24 40V24M24 24L11 11M24 24L37 11M11 11v7M11 11h7M37 11v7M37 11h-7"/></g><circle cx="24" cy="40" r="3" ${f}/>`;
      case 'service': return `<g ${s}><path d="M24 5l16 9v20l-16 9-16-9V14z"/><path d="M24 24l16-9M24 24L8 15M24 24v19"/></g>`;
      case 'database': return `<g ${s}><ellipse cx="24" cy="11" rx="15" ry="5.5"/><path d="M9 11v26c0 3 7 5.5 15 5.5s15-2.5 15-5.5V11"/><path d="M9 24c0 3 7 5.5 15 5.5s15-2.5 15-5.5"/></g>`;
      case 'cache': return `<path d="M27 4L11 27h11l-3 17 17-24H25z" ${s}/>`;
      case 'queue': return `<g ${s}><rect x="4" y="16" width="9" height="16" rx="2"/><rect x="15" y="16" width="9" height="16" rx="2"/><rect x="26" y="16" width="9" height="16" rx="2"/><path d="M38 24h7M41 20l4 4-4 4"/></g>`;
      case 'storage': return `<g ${s}><rect x="6" y="10" width="36" height="28" rx="4"/><path d="M6 28h36"/></g><circle cx="34" cy="33" r="2.4" ${f}/>`;
      case 'cloud': return `<path d="M14 36h21a8 8 0 0 0 1-16 11 11 0 0 0-21-3 9 9 0 0 0-1 19z" ${s}/>`;
      case 'lock': return `<g ${s}><rect x="10" y="22" width="28" height="20" rx="4"/><path d="M16 22v-6a8 8 0 0 1 16 0v6"/></g><circle cx="24" cy="32" r="2.6" ${f}/>`;
      case 'key': return `<g ${s}><circle cx="16" cy="24" r="8"/><path d="M24 24h18M36 24v7M41 24v5"/></g>`;
      case 'brain': return `<g ${s}><circle cx="12" cy="14" r="4"/><circle cx="36" cy="14" r="4"/><circle cx="24" cy="34" r="4"/><circle cx="12" cy="34" r="3"/><circle cx="36" cy="34" r="3"/><path d="M16 14h16M14 17l8 14M34 17l-8 14M15 34h5M28 34h5"/></g>`;
      case 'doc': return `<g ${s}><path d="M12 5h16l9 9v29H12z"/><path d="M28 5v9h9M18 25h13M18 32h13"/></g>`;
      case 'gear': return `<g transform="rotate(${a} 24 24)"><circle cx="24" cy="24" r="13" fill="none" stroke="${c}" stroke-width="7" stroke-dasharray="5.1 5.1"/><circle cx="24" cy="24" r="10" ${s}/><circle cx="24" cy="24" r="4" ${f}/></g>`;
      case 'globe': return `<g ${s}><circle cx="24" cy="24" r="17"/><ellipse cx="24" cy="24" rx="7" ry="17"/><path d="M7 24h34"/></g>`;
      case 'cpu': return `<g ${s}><rect x="12" y="12" width="24" height="24" rx="3"/><rect x="19" y="19" width="10" height="10" rx="1"/><path d="M18 6v6M24 6v6M30 6v6M18 36v6M24 36v6M30 36v6M6 18h6M6 24h6M6 30h6M36 18h6M36 24h6M36 30h6"/></g>`;
      case 'memory': return `<g ${s}><rect x="5" y="14" width="38" height="18" rx="3"/><path d="M12 32v6M20 32v6M28 32v6M36 32v6M12 20v6M20 20v6M28 20v6M36 20v6"/></g>`;
      case 'code': return `<g ${s}><path d="M17 14L7 24l10 10M31 14l10 10-10 10M27 10l-6 28"/></g>`;
      case 'container': return `<g ${s}><path d="M24 5l17 9v20l-17 9-17-9V14z"/><path d="M7 14l17 9 17-9M24 23v20"/></g>`;
      case 'shield': return `<g ${s}><path d="M24 4l16 6v12c0 10-7 17-16 21C15 39 8 32 8 22V10z"/><path d="M17 24l5 5 9-10"/></g>`;
      case 'clock': return `<g ${s}><circle cx="24" cy="24" r="17"/><path d="M24 13v11l7 5"/></g>`;
      default: return `<circle cx="24" cy="24" r="14" ${s}/>`;
    }
  }
  const spinner = (a) => `<circle cx="24" cy="24" r="17" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="5"/>
    <circle cx="24" cy="24" r="17" fill="none" stroke="${TONE.amber}" stroke-width="5" stroke-linecap="round" stroke-dasharray="30 200" transform="rotate(${a} 24 24)"/>`;
  const cross = `<circle cx="24" cy="24" r="19" fill="rgba(255,77,94,.15)" stroke="${TONE.red}" stroke-width="3.6"/>
    <path d="M16 16L32 32M32 16L16 32" stroke="${TONE.red}" stroke-width="5" stroke-linecap="round"/>`;

  // ---- layout --------------------------------------------------------------------------
  function makeDiagram(spec, W, H) {
    const groups = Object.fromEntries((spec.groups || []).map(g => [g.id, g]));
    const rowsUsed = [...new Set(spec.nodes.map(n => n.row))].sort((a, b) => a - b);
    const L = {}, G = {};
    const rowInfo = rowsUsed.map(r => {
      const ns = spec.nodes.filter(n => n.row === r);
      const blocks = [];
      for (const n of ns) {
        const last = blocks[blocks.length - 1];
        if (n.group && last && last.group === n.group) last.nodes.push(n);
        else blocks.push({ group: n.group || '', nodes: [n] });
      }
      const grouped = blocks.some(b => b.group);
      return { r, blocks, grouped, single: ns.length === 1 };
    });
    // widths: shrink until the widest row fits
    const PAD = 18, TG = 14, BG = 30;
    // each row sizes itself: tiles/pills shrink only as much as that row needs
    const rowW = (ri, TW, SW) => ri.blocks.reduce((w, b) => w + (b.group ? b.nodes.length * TW + (b.nodes.length - 1) * TG + 2 * PAD : SW), 0) + (ri.blocks.length - 1) * BG;
    for (const ri of rowInfo) {
      ri.TW = 190; ri.SW = ri.single ? 360 : 260;
      for (let k = 0; k < 80 && rowW(ri, ri.TW, ri.SW) > W; k++) { ri.TW *= .97; ri.SW *= .97; }
    }
    const TW = Math.min(...rowInfo.filter(r => r.grouped).map(r => r.TW), 190);
    const TH = Math.min(170, TW * 1.15), HDR = 54;
    // heights + vertical distribution
    const hOf = ri => ri.grouped ? HDR + TH + PAD : (ri.blocks.some(b => b.nodes.some(n => ROUND.has(n.icon))) ? 136 : 100);
    const total = rowInfo.reduce((s, ri) => s + hOf(ri), 0);
    // if the rows can't fit with minimum spacing, grow the viewBox; the SVG scales down to fit
    const VH = Math.max(H, total + 54 * (rowInfo.length - 1));
    const gap = Math.max(54, (VH - total) / Math.max(1, rowInfo.length - 1));
    let y = Math.max(0, (VH - total - gap * (rowInfo.length - 1)) / 2);
    for (const ri of rowInfo) {
      const h = hOf(ri), SW = ri.SW, rw = rowW(ri, TW, SW);
      let x = (W - rw) / 2;
      for (const b of ri.blocks) {
        if (b.group) {
          const bw = b.nodes.length * TW + (b.nodes.length - 1) * TG + 2 * PAD;
          G[b.group] = { x, y, w: bw, h, ...groups[b.group] };
          b.nodes.forEach((n, i) => {
            const nx = x + PAD + i * (TW + TG);
            L[n.id] = { ...n, shape: 'tile', x: nx, y: y + HDR, w: TW, h: TH, cx: nx + TW / 2,
                        inTop: y, outBottom: y + h, gTone: groups[b.group].tone };
          });
          x += bw + BG;
        } else {
          const n = b.nodes[0], round = ROUND.has(n.icon);
          const w = round ? 136 : SW, hh = round ? 136 : 96, ny = y + (h - hh) / 2;
          L[n.id] = { ...n, shape: round ? 'round' : 'pill', x: x + (SW - w) / 2, y: ny, w, h: hh, cx: x + SW / 2,
                      inTop: ny, outBottom: ny + hh, gTone: 'cyan' };
          x += SW + BG;
        }
      }
      y += h + gap;
    }
    for (const id in L) L[id].cy = L[id].y + L[id].h / 2;

    // edges as cubic beziers [p0, p1, p2, p3]
    const E = {};
    for (const e of spec.edges) {
      const a = L[e.src], b = L[e.dst];
      if (!a || !b) continue;
      let P;
      if (b.row > a.row) {
        const y0 = a.outBottom, y1 = b.inTop, d = (y1 - y0) * .55;
        P = [[a.cx, y0], [a.cx, y0 + d], [b.cx, y1 - d], [b.cx, y1]];
      } else if (b.row < a.row) {
        const y0 = a.inTop, y1 = b.outBottom, d = (y0 - y1) * .55;
        P = [[a.cx, y0], [a.cx, y0 - d], [b.cx, y1 + d], [b.cx, y1]];
      } else {
        const dir = b.cx > a.cx ? 1 : -1, y0 = a.cy;
        const x0 = a.cx + dir * a.w / 2, x1 = b.cx - dir * b.w / 2;
        P = [[x0, y0], [x0 + dir * 30, y0], [x1 - dir * 30, y0], [x1, y0]];
      }
      E[e.src + '>' + e.dst] = P;
    }
    const bez = (P, f) => { const u = 1 - f; return [0, 1].map(d => u*u*u*P[0][d] + 3*u*u*f*P[1][d] + 3*u*f*f*P[2][d] + f*f*f*P[3][d]); };
    const len = P => { let l = 0, p = P[0]; for (let i = 1; i <= 20; i++) { const q = bez(P, i / 20); l += Math.hypot(q[0] - p[0], q[1] - p[1]); p = q; } return l; };
    const pathD = P => `M${P[0][0]} ${P[0][1]} C${P[1][0]} ${P[1][1]}, ${P[2][0]} ${P[2][1]}, ${P[3][0]} ${P[3][1]}`;
    const edgeFor = (s, d) => E[s + '>' + d] ? { P: E[s + '>' + d], rev: false } : E[d + '>' + s] ? { P: E[d + '>' + s], rev: true } : null;

    function draw(view, t) {
      const st = id => view.states[id] || { state: 'idle', note: '' };
      const flows = view.flows || [];
      let wires = '', dots = '', boxes = '', nodes = '';
      // wires
      for (const k in E) {
        const [s, d] = k.split('>');
        const f = flows.find(f => (f.src === s && f.dst === d) || (f.src === d && f.dst === s));
        const empty = st(s).state === 'empty' || st(d).state === 'empty';
        const a = f ? f.alpha : 0, col = f ? TONE[f.tone] : 'rgba(255,255,255,.12)';
        wires += `<path d="${pathD(E[k])}" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="3" ${empty ? 'stroke-dasharray="6 12"' : ''}/>`;
        if (a > 0) wires += `<path d="${pathD(E[k])}" fill="none" stroke="${col}" stroke-width="5" stroke-opacity="${.75 * a}" stroke-linecap="round"/>`;
      }
      // dots
      for (const f of flows) {
        const e = edgeFor(f.src, f.dst);
        if (!e || f.alpha <= 0) continue;
        const L_ = len(e.P), n = Math.max(2, Math.round(L_ / 70)), speed = 380 / L_;
        for (let k = 0; k < n; k++) {
          const ph = ((t * speed + k / n) % 1 + 1) % 1;
          const [x, y] = bez(e.P, e.rev ? 1 - ph : ph);
          const col = f.bad && ph > .62 ? TONE.red : HI[f.tone];
          const op = f.alpha * (ph > .9 ? (1 - ph) * 10 : 1);
          dots += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${f.bad && ph > .85 ? 10 : 7.5}" fill="${col}" opacity="${op.toFixed(2)}"/>`;
        }
      }
      // groups
      for (const id in G) {
        const g = G[id], kids = Object.values(L).filter(n => n.group === id), ss = kids.map(n => st(n.id).state);
        const live = ss.includes('live') || ss.includes('busy');
        let badge = 'STANDBY', bc = MUTED;
        if (live) { badge = '● LIVE'; bc = HI[g.tone]; }
        else if (ss.every(s => s === 'empty')) badge = 'EMPTY';
        else if (ss.includes('boot')) { badge = 'BOOTING'; bc = TONE.amber; }
        else if (ss.includes('testing')) { badge = 'TESTING'; bc = TONE.amber; }
        else if (ss.includes('error')) { badge = 'ERROR'; bc = TONE.red; }
        else if (ss.every(s => s === 'off')) badge = 'OFF';
        const empty = ss.every(s => s === 'empty');
        const bw = badge.length * 12 + 26;
        boxes += `<g opacity="${empty ? .5 : 1}">
          ${live ? `<rect x="${g.x}" y="${g.y}" width="${g.w}" height="${g.h}" rx="24" fill="none" stroke="${TONE[g.tone]}" stroke-width="10" stroke-opacity=".18"/>` : ''}
          <rect x="${g.x}" y="${g.y}" width="${g.w}" height="${g.h}" rx="24" fill="rgba(22,27,34,.9)" stroke="${live ? TONE[g.tone] : LINE}" stroke-width="2.5"/>
          <text x="${g.x + 22}" y="${g.y + 37}" font-family="Poppins" font-weight="800" font-size="27" fill="${HI[g.tone]}">${esc(g.label)}<tspan font-family="JetBrains Mono" font-weight="500" font-size="19" fill="${MUTED}" dx="8">${esc(empty ? '' : g.sub || '')}</tspan></text>
          <rect x="${g.x + g.w - 18 - bw}" y="${g.y + 14}" width="${bw}" height="32" rx="16" fill="none" stroke="${bc}" stroke-width="2"/>
          <text x="${g.x + g.w - 18 - bw / 2}" y="${g.y + 36}" text-anchor="middle" font-family="JetBrains Mono" font-weight="700" font-size="17" fill="${bc}">${badge}</text></g>`;
      }
      // nodes
      for (const id in L) {
        const n = L[id], s = st(id), tone = n.gTone || 'cyan';
        const pulse = s.since != null ? Math.max(0, 1 - (t - s.since) / .45) : 0;
        const sc = 1 + .1 * Math.sin(Math.PI * pulse) * (pulse > 0 ? 1 : 0);
        const shake = s.state === 'error' ? 3.5 * Math.sin(t * 50) : 0;
        const live = s.state === 'live' || s.state === 'busy';
        let border = LINE, ic = '#6E7681', note = s.note, noteCol = MUTED, glow = '';
        if (live) { border = TONE[s.state === 'busy' ? 'amber' : tone]; ic = HI[s.state === 'busy' ? 'amber' : tone]; noteCol = ic; }
        if (s.state === 'ok') { border = 'rgba(255,255,255,.2)'; ic = '#AEB7C0'; }
        if (s.state === 'boot' || s.state === 'testing') { border = TONE.amber; noteCol = TONE.amber; }
        if (s.state === 'error') { border = TONE.red; noteCol = TONE.red; }
        if (live) glow = `filter="url(#dglow)"`;
        const load = s.state === 'busy' ? .92 + .05 * Math.sin(t * 7) : .45 + .3 * Math.sin(t * 2.6 + n.cx);
        if (!note && live && n.shape === 'tile') note = Math.round(load * 100) + '%';
        if (!note && s.state === 'idle' && n.shape === 'tile') note = 'idle';
        const tx = `translate(${shake.toFixed(1)} 0) translate(${n.cx} ${n.cy}) scale(${sc.toFixed(3)}) translate(${-n.cx} ${-n.cy})`;
        const inner = s.state === 'empty' ? '' : s.state === 'boot' ? spinner(t * 420) : s.state === 'error' ? cross : icon(n.icon, ic, t * 90);
        if (n.shape === 'tile') {
          const iz = Math.min(56, n.w * .45), ix = n.cx - iz / 2, iy = n.y + 16;
          nodes += `<g transform="${tx}"><rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="16" fill="rgba(255,255,255,.03)" stroke="${border}" stroke-width="2.2" ${s.state === 'empty' ? 'stroke-dasharray="6 8"' : ''}/>
            ${s.state === 'empty' ? '' : `<g transform="translate(${ix} ${iy}) scale(${iz / 48})">${inner}</g>
            <text x="${n.cx}" y="${n.y + n.h * .62}" text-anchor="middle" font-family="JetBrains Mono" font-weight="600" font-size="17" fill="${MUTED}">${esc(n.label)}</text>
            ${live ? `<rect x="${n.cx - n.w * .33}" y="${n.y + n.h * .7}" width="${n.w * .66}" height="8" rx="4" fill="rgba(255,255,255,.08)"/><rect x="${n.cx - n.w * .33}" y="${n.y + n.h * .7}" width="${n.w * .66 * clamp(load)}" height="8" rx="4" fill="${ic}"/>` : ''}
            <text x="${n.cx}" y="${n.y + n.h - 14}" text-anchor="middle" font-family="JetBrains Mono" font-weight="700" font-size="17" fill="${noteCol}">${esc(note || '')}</text>`}</g>`;
        } else if (n.shape === 'round') {
          const r = n.w / 2, ring = live ? `<circle cx="${n.cx}" cy="${n.cy}" r="${r + 9}" fill="none" stroke="${border}" stroke-width="3" stroke-dasharray="14 18" transform="rotate(${t * 60} ${n.cx} ${n.cy})" opacity=".7"/>` : '';
          nodes += `<g transform="${tx}">${ring}<circle cx="${n.cx}" cy="${n.cy}" r="${r}" fill="${CARD}" stroke="${border}" stroke-width="3" ${glow}/>
            <g transform="translate(${n.cx - 27} ${n.cy - 34}) scale(1.12)">${inner}</g>
            <text x="${n.cx}" y="${n.cy + 44}" text-anchor="middle" font-family="JetBrains Mono" font-weight="700" font-size="17" fill="${MUTED}" letter-spacing="2">${esc(n.label)}</text>
            ${note && s.state !== 'idle' ? `<text x="${n.cx + r + 16}" y="${n.cy + 6}" font-family="JetBrains Mono" font-weight="700" font-size="20" fill="${noteCol}">${esc(note)}</text>` : ''}</g>`;
        } else {
          nodes += `<g transform="${tx}"><rect x="${n.x}" y="${n.y}" width="${n.w}" height="${n.h}" rx="20" fill="${CARD}" stroke="${border}" stroke-width="2.4" ${glow} ${s.state === 'empty' ? 'stroke-dasharray="6 8"' : ''}/>
            <g transform="translate(${n.x + 18} ${n.y + n.h / 2 - 26}) scale(1.08)">${inner}</g>
            <text x="${n.x + 84}" y="${n.y + n.h / 2 + (note ? -4 : 10)}" font-family="JetBrains Mono" font-weight="700" font-size="${n.label.length > 9 ? 22 : 28}" fill="#E6EDF3" letter-spacing="2">${esc(n.label)}</text>
            ${note ? `<text x="${n.x + 84}" y="${n.y + n.h / 2 + 26}" font-family="JetBrains Mono" font-weight="600" font-size="20" fill="${noteCol}">${esc(note)}</text>` : ''}</g>`;
        }
      }
      return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${VH}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
        <defs><filter id="dglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
        ${wires}${boxes}<g filter="url(#dglow)">${dots}</g>${nodes}</svg>`;
    }
    return { draw, layout: L };
  }

  // spec state at time t, given trigger times per beat (null = carousel: apply beats 0..k fully)
  function viewAt(spec, triggers, t) {
    const states = {};
    for (const s of spec.initial) states[s.node] = { state: s.state, note: s.note || '', since: null };
    let cur = 0;
    spec.beats.forEach((b, i) => {
      if (t >= triggers[i]) {
        cur = i;
        for (const s of b.states) states[s.node] = { state: s.state, note: s.note || '', since: triggers[i] };
      }
    });
    const FADE = .35, key = f => f.src + '>' + f.dst;
    const now = spec.beats[cur].flows, prev = cur > 0 ? spec.beats[cur - 1].flows : [];
    const since = cur > 0 ? t - triggers[cur] : 99;
    const flows = now.map(f => ({ ...f, alpha: prev.some(p => key(p) === key(f)) ? 1 : clamp(since / FADE) }));
    for (const p of prev) if (!now.some(f => key(f) === key(p))) flows.push({ ...p, alpha: 1 - clamp(since / FADE) });
    return { states, flows, beat: cur };
  }

  window.ReelDiagram = { makeDiagram, viewAt, TONE, HI };
})();
