import { cached } from '../api.js';
import { h, MONTHS, parseDate, fmtDate, showTip, hideTip } from '../ui.js';

const PHASES = {
  indoor: { label: 'Indoors (seed starting)', color: 'var(--s1)' },
  ground: { label: 'In the ground', color: 'var(--axis)' },
  harvest: { label: 'Harvest window', color: 'var(--s2)' },
};
const EVENT_LABEL = {
  indoor: 'Start indoors', harden: 'Harden off', plant: 'Plant', harvest: 'Harvest',
  terminate: 'Cover crop', amend: 'Amend soil',
};

export async function renderCalendar(yearArg) {
  const year = Number(yearArg) || new Date().getFullYear();
  const cal = await cached(`/calendar?year=${year}`);
  const start = new Date(year, 0, 1);
  const days = (new Date(year + 1, 0, 1) - start) / 86400000;
  const pos = (iso) => {
    const d = Math.round((parseDate(iso) - start) / 86400000);
    return Math.max(0, Math.min(days, d)) / days * 100;
  };

  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, `${year} garden calendar`),
      h('p', {}, `Rotation year ${cal.cycle_year}. Dates come from your planting plan and local climate; mark plantings on the Today page to re-time them.`)),
    h('div', { class: 'row' },
      h('a', { class: 'btn', href: `#/calendar/${year - 1}` }, `← ${year - 1}`),
      h('a', { class: 'btn', href: `#/calendar/${year + 1}` }, `${year + 1} →`),
      h('button', { onclick: () => window.print() }, 'Print')));

  const legend = h('div', { class: 'legend' },
    Object.values(PHASES).map((p) => h('span', { class: 'item' }, h('span', { class: 'key', style: { background: p.color } }), p.label)),
    h('span', { class: 'item' }, h('span', { class: 'key', style: { background: 'var(--critical)', width: '2px' } }), 'Median frost dates'),
    h('span', { class: 'item' }, h('span', { class: 'key', style: { background: 'var(--ink)', width: '2px' } }), 'Today'));

  const monthHead = h('div', { class: 'tl-months' }, MONTHS.map((m, i) =>
    h('span', { style: { left: `${pos(`${year}-${String(i + 1).padStart(2, '0')}-01`)}%` } }, m)));
  const tl = h('div', { class: 'timeline' }, h('div', { class: 'tl-head' }, h('div', {}), monthHead));

  const overlays = () => {
    const out = [];
    for (let i = 0; i < 12; i++) out.push(h('div', { class: 'tl-grid', style: { left: `${pos(`${year}-${String(i + 1).padStart(2, '0')}-01`)}%` } }));
    for (const f of [cal.frost.last_spring, cal.frost.first_fall]) {
      if (f) out.push(h('div', { class: 'tl-marker', style: { left: `${pos(f)}%`, background: 'var(--critical)', opacity: 0.6 } }));
    }
    const today = new Date();
    if (today.getFullYear() === year) out.push(h('div', { class: 'tl-marker', style: { left: `${pos(today.toISOString().slice(0, 10))}%`, background: 'var(--ink)' } }));
    return out;
  };

  let lastBed = null;
  for (const r of cal.rows) {
    if (r.bed !== lastBed) { tl.append(h('div', { class: 'tl-group' }, r.bed)); lastBed = r.bed; }
    const track = h('div', { class: 'tl-track' }, overlays());
    const segs = [];
    if (r.indoor_start && r.establish) segs.push(['indoor', r.indoor_start[0], r.establish]);
    const gStart = r.establish || r.start;
    if (r.harvest_this_year && r.category !== 'cover') {
      segs.push(['ground', gStart, r.maturity]);
      segs.push(['harvest', r.maturity, r.harvest_end]);
    } else {
      segs.push(['ground', gStart, r.end]);
    }
    for (const [phase, a, b] of segs) {
      if (!a || !b || b < `${year}-01-01` || a > `${year}-12-31`) continue;
      const left = pos(a), width = Math.max(pos(b) - left, 0.4);
      const bar = h('div', { class: 'tl-bar', style: { left: `${left}%`, width: `${width}%`, background: PHASES[phase].color }, tabindex: 0 });
      const tipRows = [{ color: PHASES[phase].color, value: `${fmtDate(a)} – ${fmtDate(b)}`, label: PHASES[phase].label }];
      bar.addEventListener('pointermove', (e) => showTip(e, `${r.name} · ${r.bed}`, tipRows));
      bar.addEventListener('pointerleave', hideTip);
      track.append(bar);
    }
    tl.append(h('div', { class: 'tl-row' },
      h('div', { class: 'lab', title: r.name }, r.name + (r.succession ? ` #${r.succession + 1}` : ''),
        h('small', {}, [r.kind === 'perennial' ? 'perennial' : r.method === 'transplant' ? 'transplant' : 'direct sow',
          `${r.area_sqft} sq ft`, r.notes.find((n) => n.startsWith('Warning')) ? '⚠ check timing' : null].filter(Boolean).join(' · '))),
      track));
  }
  if (!cal.rows.length) tl.append(h('div', { class: 'empty' }, 'Nothing planned for this year yet. Add crops on the Plants or Rotation pages.'));

  // month-by-month task list
  const byMonth = {};
  for (const e of cal.events) (byMonth[Number(e.date.slice(5, 7)) - 1] ||= []).push(e);
  const months = h('div', { class: 'grid grid-3' });
  for (let m = 0; m < 12; m++) {
    const evs = byMonth[m] || [];
    months.append(h('div', { class: 'card' }, h('h3', {}, `${MONTHS[m]} ${year}`),
      evs.length ? h('div', {}, evs.map((e) => h('div', { style: { padding: '.3rem 0', borderTop: '1px solid var(--border)' } },
        h('div', { class: 'row', style: { gap: '.4rem' } }, h('span', { class: 'tiny num' }, fmtDate(e.date)),
          h('span', { class: 'badge' }, EVENT_LABEL[e.type])),
        h('div', {}, e.title, e.bed ? h('span', { class: 'muted' }, ` · ${e.bed}`) : null),
        e.detail ? h('div', { class: 'tiny' }, e.detail) : null)))
        : h('p', { class: 'tiny' }, 'Nothing scheduled.')));
  }

  return h('div', { class: 'stack' }, head,
    h('div', { class: 'card stack' }, legend, tl),
    h('h2', { class: 'section-title' }, 'Month by month'), months);
}
