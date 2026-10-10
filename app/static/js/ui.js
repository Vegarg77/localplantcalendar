// Small DOM + formatting helpers. All text goes through textContent.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v; // only for trusted static SVG
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const svgNS = 'http://www.w3.org/2000/svg';
export function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, v);
  for (const c of children.flat()) if (c) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

// ------------------------------------------------------------------ dates
const CUM = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365];
export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function parseDate(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d);
}
export function isoDate(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
export function fmtDate(iso, opts = { month: 'short', day: 'numeric' }) {
  const d = typeof iso === 'string' ? parseDate(iso) : iso;
  return d ? d.toLocaleDateString(undefined, opts) : '—';
}
export function fmtDay(iso) { return fmtDate(iso, { weekday: 'short', month: 'short', day: 'numeric' }); }
export function idxToLabel(idx) {
  const i = ((idx % 365) + 365) % 365;
  let m = 0;
  while (i >= CUM[m + 1]) m++;
  return `${MONTHS[m]} ${i - CUM[m] + 1}`;
}
export function idxToMonthDay(idx) {
  const i = ((idx % 365) + 365) % 365;
  let m = 0;
  while (i >= CUM[m + 1]) m++;
  return `${String(m + 1).padStart(2, '0')}-${String(i - CUM[m] + 1).padStart(2, '0')}`;
}
export function doyOf(d) {
  const day = d.getMonth() === 1 ? Math.min(d.getDate(), 28) : d.getDate();
  return CUM[d.getMonth()] + day - 1;
}
export function monthDayToIdx(md) {
  const [m, d] = md.split('-').slice(-2).map(Number);
  return CUM[m - 1] + d - 1;
}
export function daysBetween(a, b) { return Math.round((parseDate(b) - parseDate(a)) / 86400000); }

export const f0 = (x) => (x === null || x === undefined ? '—' : (Math.round(x) || 0).toLocaleString());
export const f1 = (x) => (x === null || x === undefined ? '—' : (Math.round(x * 10) / 10).toLocaleString());
export const f2 = (x) => (x === null || x === undefined ? '—' : (Math.round(x * 100) / 100).toLocaleString());

// ------------------------------------------------------------- feedback
const ICONS = {
  high: '<svg width="14" height="14" viewBox="0 0 16 16"><path d="M8 1 15 14H1z" fill="var(--critical)"/><path d="M8 6v4M8 12v.5" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/></svg>',
  warn: '<svg width="14" height="14" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--warning)"/><path d="M8 4.5v4.5M8 11.2v.4" stroke="#0b0b0b" stroke-width="1.6" stroke-linecap="round"/></svg>',
  info: '<svg width="14" height="14" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--s1)"/><path d="M8 7.2V12M8 4.4v.4" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/></svg>',
  good: '<svg width="14" height="14" viewBox="0 0 16 16"><circle cx="8" cy="8" r="7" fill="var(--good)"/><path d="m4.8 8.2 2.2 2.2 4.2-4.6" stroke="#fff" stroke-width="1.7" fill="none" stroke-linecap="round"/></svg>',
};
const LABELS = { high: 'Urgent', warn: 'Watch', info: 'Note', good: 'Go' };
export function statusBadge(sev, label) {
  return h('span', { class: 'status', html: ICONS[sev] || ICONS.info }, label || LABELS[sev]);
}
export function statusIcon(sev) { return h('span', { class: 'status', html: ICONS[sev] || ICONS.info }); }

let toastTimer;
export function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 2800);
}

export function errorBox(err) {
  if (err && err.code === 'no_location') {
    return h('div', { class: 'card stack' },
      h('h2', {}, 'Where is your garden?'),
      h('p', {}, 'Everything here — frost dates, planting windows, watering and soil — is computed for your exact location. Set it once on the Setup page.'),
      h('a', { class: 'btn primary', href: '#/setup' }, 'Set location'));
  }
  return h('div', { class: 'error' }, (err && err.message) || String(err));
}

export function loading(text = 'Loading…') { return h('div', { class: 'empty' }, text); }

// ----------------------------------------------------------------- modal
export function modal(title, body, actions = []) {
  const dlg = h('dialog', {});
  const close = () => { dlg.close(); dlg.remove(); };
  const foot = h('div', { class: 'modal-foot' });
  for (const a of actions) {
    foot.append(h('button', {
      class: a.class || '', type: 'button',
      onclick: async (e) => {
        if (!a.onClick) return close();
        e.target.disabled = true;
        try {
          const keep = await a.onClick();
          if (keep !== false) close();
        } catch (err) {
          toast(err.message || String(err));
        } finally { e.target.disabled = false; }
      },
    }, a.label));
  }
  dlg.append(
    h('div', { class: 'modal-head' }, h('h2', {}, title),
      h('button', { class: 'icon-btn', 'aria-label': 'Close', onclick: close }, '✕')),
    h('div', { class: 'modal-body' }, body), foot);
  dlg.addEventListener('cancel', (e) => { e.preventDefault(); close(); });
  document.body.append(dlg);
  dlg.showModal();
  return { close, dialog: dlg };
}

export function field(label, input, hint) {
  return h('label', { class: 'field' }, h('span', {}, label), input, hint ? h('small', { class: 'tiny' }, hint) : null);
}

export function select(options, value, attrs = {}) {
  const el = h('select', attrs);
  for (const o of options) {
    const opt = h('option', { value: o.value }, o.label);
    if (String(o.value) === String(value)) opt.selected = true;
    el.append(opt);
  }
  return el;
}

// --------------------------------------------------------------- tooltip
const tip = () => document.getElementById('tooltip');
export function showTip(evt, head, rows) {
  const t = tip();
  t.replaceChildren(h('div', { class: 't-head' }, head),
    ...rows.map((r) => h('div', { class: 't-row' },
      r.color ? h('span', { class: 'key', style: { background: r.color } }) : null,
      h('strong', {}, r.value), h('span', {}, r.label))));
  t.hidden = false;
  const x = evt.clientX, y = evt.clientY;
  const w = t.offsetWidth, hh = t.offsetHeight;
  t.style.left = `${Math.min(x + 14, window.innerWidth - w - 8)}px`;
  t.style.top = `${y + hh + 20 > window.innerHeight ? y - hh - 10 : y + 14}px`;
}
export function hideTip() { tip().hidden = true; }

// Feeder groups are the categorical identity used across rotation views,
// assigned in fixed palette order.
export const FEEDER = {
  fixer: { label: 'Legume / N-fixer', color: 'var(--s1)' },
  heavy: { label: 'Heavy feeder', color: 'var(--s2)' },
  medium: { label: 'Medium feeder', color: 'var(--s3)' },
  light: { label: 'Light feeder', color: 'var(--s4)' },
};
export const CATEGORY_LABEL = {
  vegetable: 'Vegetables', herb: 'Herbs', fruit: 'Fruit', flower: 'Flowers', cover: 'Cover crops',
};
export const FROST_LABEL = {
  tender: 'Tender (killed at 32°F)', semi: 'Semi-hardy (to ~28°F)',
  hardy: 'Hardy (to ~24°F)', very_hardy: 'Very hardy (to ~15°F)',
};
