// Minimal SVG charts: line/area with crosshair tooltip, grouped columns with
// per-mark tooltips.  Rendered at the container's real pixel width so text
// stays legible, and re-rendered on resize.
import { h, s, showTip, hideTip, fmtDate, parseDate } from './ui.js';

function niceTicks(min, max, count = 4) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => span / st <= count + 0.5) || mag * 10;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.round(v * 1000) / 1000);
  return ticks;
}

function legend(series) {
  if (series.length < 2) return null;
  return h('div', { class: 'legend', style: { marginBottom: '.4rem' } },
    series.map((sr) => h('span', { class: 'item' },
      sr.dashed
        ? h('span', { class: 'key', style: { height: '2px', background: sr.color, borderRadius: '1px' } })
        : h('span', { class: 'key', style: { background: sr.color } }),
      sr.name)));
}

function responsive(wrap, draw) {
  let last = 0;
  const go = () => {
    const w = Math.round(wrap.clientWidth);
    if (!w || w === last) return;
    last = w;
    draw(w);
  };
  requestAnimationFrame(go);
  if ('ResizeObserver' in window) new ResizeObserver(go).observe(wrap);
}

/**
 * x: array of ISO dates; series: [{name, color, values, area}]
 * opts: height, yFormat, unit, refs [{y, label}], yMin, yMax, xLabel(fn)
 */
export function lineChart({ x, series, height = 220, yFormat = (v) => v, unit = '',
  refs = [], yMin, yMax, title, bands = [], xFormat }) {
  const wrap = h('div', { class: 'chart' });
  const box = h('div', {});
  wrap.append(legend(series) || '', box);
  responsive(box, (W) => {
    const m = { l: 40, r: 16, t: 10, b: 24 };
    const iw = W - m.l - m.r, ih = height - m.t - m.b;
    const all = series.flatMap((sr) => sr.values).filter((v) => v !== null && v !== undefined);
    refs.forEach((r) => all.push(r.y));
    const lo = yMin ?? Math.min(...all), hi = yMax ?? Math.max(...all);
    const ticks = niceTicks(lo, hi);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const n = x.length;
    const X = (i) => m.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
    const Y = (v) => m.t + ih - ((v - y0) / (y1 - y0 || 1)) * ih;
    const svg = s('svg', { viewBox: `0 0 ${W} ${height}`, width: W, height, role: 'img',
      'aria-label': title || series.map((sr) => sr.name).join(', ') });
    for (const b of bands) {
      const i0 = Math.max(0, b.from), i1 = Math.min(n - 1, b.to);
      if (i1 < i0) continue;
      svg.append(s('rect', { x: X(i0), y: m.t, width: Math.max(1, X(i1) - X(i0)), height: ih,
        fill: b.color, opacity: 0.08 }));
    }
    for (const t of ticks) {
      svg.append(s('line', { class: t === y0 ? 'baseline' : 'grid-line', x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
      svg.append(s('text', { x: m.l - 6, y: Y(t) + 4, 'text-anchor': 'end' }, `${yFormat(t)}`));
    }
    // x labels: month starts (or every k-th label)
    const step = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 70))));
    let lastMonth = -1;
    x.forEach((d, i) => {
      const dt = parseDate(d);
      const multiYear = n > 120;
      if (multiYear) {
        if (dt.getMonth() % 6 === 0 && dt.getMonth() !== lastMonth && dt.getDate() <= 7) {
          svg.append(s('text', { x: X(i), y: height - 6, 'text-anchor': 'middle' },
            dt.getMonth() === 0 ? String(dt.getFullYear()) : 'Jul'));
        }
        lastMonth = dt.getMonth();
      } else if (i % step === 0) {
        svg.append(s('text', { x: X(i), y: height - 6, 'text-anchor': 'middle' }, xFormat ? xFormat(d) : fmtDate(d)));
      }
    });
    for (const r of refs) {
      svg.append(s('line', { class: 'ref', x1: m.l, x2: W - m.r, y1: Y(r.y), y2: Y(r.y) }));
      svg.append(s('text', { class: 'ref-label', x: W - m.r, y: Y(r.y) - 4, 'text-anchor': 'end' }, r.label));
    }
    for (const sr of series) {
      let d = '', area = '', started = false, firstI = 0, lastI = 0;
      sr.values.forEach((v, i) => {
        if (v === null || v === undefined) { started = false; return; }
        d += `${started ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`;
        if (!started && !area) firstI = i;
        lastI = i;
        started = true;
      });
      if (sr.area && d) {
        area = `${d}L${X(lastI)},${Y(y0)}L${X(firstI)},${Y(y0)}Z`;
        svg.append(s('path', { d: area, fill: sr.color, opacity: 0.1 }));
      }
      svg.append(s('path', { d, fill: 'none', stroke: sr.color, 'stroke-width': 2,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round',
        'stroke-dasharray': sr.dashed ? '5 4' : null }));
    }
    const cross = s('line', { class: 'crosshair', y1: m.t, y2: m.t + ih, visibility: 'hidden' });
    const dots = series.map((sr) => s('circle', { r: 4, fill: sr.color, stroke: 'var(--surface)',
      'stroke-width': 2, visibility: 'hidden' }));
    svg.append(cross, ...dots);
    const hit = s('rect', { class: 'hit', x: m.l, y: m.t, width: iw, height: ih });
    hit.addEventListener('pointermove', (e) => {
      const rect = svg.getBoundingClientRect();
      const px = (e.clientX - rect.left) * (W / rect.width);
      const i = Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / iw) * (n - 1))));
      cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i));
      cross.setAttribute('visibility', 'visible');
      series.forEach((sr, k) => {
        const v = sr.values[i];
        if (v === null || v === undefined) { dots[k].setAttribute('visibility', 'hidden'); return; }
        dots[k].setAttribute('cx', X(i)); dots[k].setAttribute('cy', Y(v));
        dots[k].setAttribute('visibility', 'visible');
      });
      showTip(e, xFormat ? xFormat(x[i]) : fmtDate(x[i], { weekday: n < 60 ? 'short' : undefined, month: 'short', day: 'numeric', year: n > 120 ? 'numeric' : undefined }),
        series.filter((sr) => sr.values[i] !== null && sr.values[i] !== undefined)
          .map((sr) => ({ color: sr.color, value: `${yFormat(sr.values[i])}${unit}`, label: sr.name })));
    });
    hit.addEventListener('pointerleave', () => {
      cross.setAttribute('visibility', 'hidden');
      dots.forEach((d) => d.setAttribute('visibility', 'hidden'));
      hideTip();
    });
    svg.append(hit);
    box.replaceChildren(svg);
  });
  return wrap;
}

/** labels: category labels; series: [{name, color, values}] */
export function columnChart({ labels, series, height = 180, yFormat = (v) => v, unit = '', title,
  tipLabel = (i) => labels[i] }) {
  const wrap = h('div', { class: 'chart' });
  const box = h('div', {});
  wrap.append(legend(series) || '', box);
  responsive(box, (W) => {
    const m = { l: 40, r: 10, t: 10, b: 24 };
    const iw = W - m.l - m.r, ih = height - m.t - m.b;
    const all = series.flatMap((sr) => sr.values).filter((v) => v !== null && v !== undefined);
    const ticks = niceTicks(0, Math.max(...all, 0.01));
    const y1 = ticks[ticks.length - 1];
    const Y = (v) => m.t + ih - (v / y1) * ih;
    const n = labels.length;
    const band = iw / n;
    const k = series.length;
    const bw = Math.min(24, (band * 0.7 - (k - 1) * 2) / k);
    const svg = s('svg', { viewBox: `0 0 ${W} ${height}`, width: W, height, role: 'img',
      'aria-label': title || series.map((sr) => sr.name).join(', ') });
    for (const t of ticks) {
      svg.append(s('line', { class: t === 0 ? 'baseline' : 'grid-line', x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
      svg.append(s('text', { x: m.l - 6, y: Y(t) + 4, 'text-anchor': 'end' }, yFormat(t)));
    }
    const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(iw / 44))));
    labels.forEach((lab, i) => {
      const cx = m.l + band * i + band / 2;
      if (i % every === 0) svg.append(s('text', { x: cx, y: height - 6, 'text-anchor': 'middle' }, lab));
      const groupW = k * bw + (k - 1) * 2;
      series.forEach((sr, j) => {
        const v = sr.values[i] || 0;
        const x0 = cx - groupW / 2 + j * (bw + 2);
        const top = Y(v), base = Y(0);
        const hgt = Math.max(0, base - top);
        const r = Math.min(4, hgt, bw / 2);
        const path = hgt > 0
          ? `M${x0},${base}V${top + r}Q${x0},${top} ${x0 + r},${top}H${x0 + bw - r}Q${x0 + bw},${top} ${x0 + bw},${top + r}V${base}Z`
          : '';
        if (path) svg.append(s('path', { d: path, fill: sr.color }));
        const hit = s('rect', { class: 'hit', x: x0 - 1, y: m.t, width: bw + 2, height: ih });
        hit.addEventListener('pointermove', (e) => showTip(e, tipLabel(i),
          series.map((ss) => ({ color: ss.color, value: `${yFormat(ss.values[i] || 0)}${unit}`, label: ss.name }))));
        hit.addEventListener('pointerleave', hideTip);
        svg.append(hit);
      });
    });
    box.replaceChildren(svg);
  });
  return wrap;
}

/** Year strip: windows as segments on a 12-month bar (single series, no legend). */
export function yearStrip(windows, todayIdx) {
  const el = h('div', { class: 'yearstrip', role: 'img',
    'aria-label': windows.length ? windows.map((w) => w.label).join('; ') : 'No planting window' });
  for (const w of windows) {
    const segs = w.end >= 365 ? [[w.start, 364], [0, w.end - 365]] : [[w.start, w.end]];
    for (const [a, b] of segs) {
      el.append(h('div', { class: 'seg', style: { left: `${(a / 365) * 100}%`, width: `${Math.max(((b - a + 1) / 365) * 100, 0.6)}%` } }));
    }
  }
  if (todayIdx !== undefined) el.append(h('div', { class: 'today', style: { left: `${(todayIdx / 365) * 100}%` } }));
  return el;
}
