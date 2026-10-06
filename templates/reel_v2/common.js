// Small helpers shared by reel.html and carousel.html.
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
// *word* -> <em>word</em>
function emph(s) { return esc(s).replace(/\*([^*]+)\*/g, '<em>$1</em>'); }
function titleHtml(parts) {
  return parts.map(p => {
    const c = ReelDiagram.HI[p.tone] || '#fff', glow = p.tone === 'white' ? '' : `text-shadow:0 0 40px ${ReelDiagram.TONE[p.tone]}99;`;
    return `<span style="color:${c};${glow}">${esc(p.text)}</span>`;
  }).join('');
}
// Tween "48,200" -> "52,307" (or "0.0s" -> "1.2s"); non-numeric values switch at the end.
function tween(a, b, k) {
  if (a === b || k >= 1) return b;
  const re = /^([^0-9-]*)(-?[\d,]*\.?\d+)(.*)$/, ma = String(a).match(re), mb = String(b).match(re);
  if (!ma || !mb || ma[1] !== mb[1] || ma[3] !== mb[3]) return k < .5 ? a : b;
  const na = parseFloat(ma[2].replace(/,/g, '')), nb = parseFloat(mb[2].replace(/,/g, ''));
  const dec = (mb[2].split('.')[1] || '').length, v = na + (nb - na) * k;
  const txt = mb[2].includes(',') ? Math.round(v).toLocaleString('en-US') : v.toFixed(dec);
  return mb[1] + txt + mb[3];
}
function statHtml(label, value, tone, flash) {
  const c = ReelDiagram.HI[tone] || '#fff';
  return `<div class="stat" style="${flash ? `border-color:${c}` : ''}"><div class="k">${esc(label)}</div><div class="v" style="color:${c}">${esc(value)}</div></div>`;
}
