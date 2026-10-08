// Month grid + agenda list of every dated garden task, with the 16-day
// forecast (weather, alerts, watering) folded in.
import { api, cached, invalidate } from '../api.js';
import { h, MONTHS, parseDate, isoDate, fmtDate, fmtDay, statusIcon, toast, modal, field, select } from '../ui.js';
import { renderTimeline, viewToggle } from './calendar.js';
import { rerender } from '../app.js';

// Categorical slots in fixed palette order; care is neutral; frost & alerts
// are states and carry a status icon.
export const KIND_STYLE = {
  indoor: { color: 'var(--s1)', label: 'Start indoors' },
  plant: { color: 'var(--s2)', label: 'Sow & transplant' },
  harvest: { color: 'var(--s3)', label: 'Harvest' },
  soil: { color: 'var(--s4)', label: 'Soil & cover crops' },
  water: { color: 'var(--s5)', label: 'Watering (forecast)' },
  care: { color: 'var(--muted)', label: 'Care' },
  frost: { color: 'var(--critical)', label: 'Frost dates', status: 'info' },
  alert: { color: 'var(--critical)', label: 'Weather alerts', status: 'high' },
};
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

// -------------------------------------------------------------- filters
function loadFilters() {
  try { return JSON.parse(localStorage.getItem('calFilters') || 'null') || { bed: '', off: [] }; } catch { return { bed: '', off: [] }; }
}
function saveFilters(f) { try { localStorage.setItem('calFilters', JSON.stringify(f)); } catch { /* ignore */ } }

function filtersBar(data, filters, onChange) {
  const bedSel = select([{ value: '', label: 'All beds' }, ...data.beds.map((b) => ({ value: b.id, label: b.name }))], filters.bed);
  bedSel.onchange = () => { filters.bed = bedSel.value; onChange(); };
  const chips = h('div', { class: 'chips' }, Object.entries(KIND_STYLE).map(([k, st]) => {
    const on = !filters.off.includes(k);
    const c = h('button', { type: 'button', class: `chip${on ? ' on' : ''}`, 'aria-pressed': String(on) },
      st.status ? statusIcon(k === 'alert' ? 'high' : 'info')
        : h('span', { class: 'key', style: { background: st.color, marginRight: '.3rem' } }), ' ', st.label);
    c.onclick = () => {
      filters.off = filters.off.includes(k) ? filters.off.filter((x) => x !== k) : [...filters.off, k];
      onChange();
    };
    return c;
  }));
  return h('div', { class: 'row' }, bedSel, chips);
}

function visible(events, filters) {
  return events.filter((e) => !filters.off.includes(e.kind) &&
    (!filters.bed || e.bed_id === null || String(e.bed_id) === String(filters.bed)));
}

function uniq(spans) {
  const seen = new Set();
  return spans.filter((s) => { const k = `${s.name}|${s.bed_id}`; if (seen.has(k)) return false; seen.add(k); return true; });
}

function eventDot(e) {
  const st = KIND_STYLE[e.kind];
  if (st.status) return statusIcon(e.kind === 'alert' ? (e.severity || 'warn') : 'info');
  return h('span', { class: 'key', style: { background: st.color } });
}

// ------------------------------------------------------------ dispatcher
export async function renderCalendar(arg) {
  if (arg === 'agenda') return renderAgenda();
  if (arg && arg.startsWith('timeline')) return renderTimeline(arg.split('/')[1]);
  if (arg && /^\d{4}$/.test(arg)) return renderTimeline(arg);
  return renderMonth(arg);
}

// ----------------------------------------------------------------- month
async function renderMonth(ym) {
  const now = new Date();
  let [y, m] = ym && /^\d{4}-\d{2}$/.test(ym) ? ym.split('-').map(Number) : [now.getFullYear(), now.getMonth() + 1];
  const first = new Date(y, m - 1, 1);
  const gridStart = new Date(first); gridStart.setDate(1 - first.getDay());
  const last = new Date(y, m, 0);
  const gridEnd = new Date(last); gridEnd.setDate(last.getDate() + (6 - last.getDay()));
  const data = await cached(`/calendar/events?start=${isoDate(gridStart)}&end=${isoDate(gridEnd)}`);
  const filters = loadFilters();
  const prev = new Date(y, m - 2, 1), next = new Date(y, m, 1);
  const ymOf = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  const todayIso = data.today;

  const root = h('div', { class: 'stack' });
  const gridBox = h('div', {});
  const dayBox = h('div', {});
  let selected = todayIso >= isoDate(first) && todayIso <= isoDate(last) ? todayIso : isoDate(first);

  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, `${MONTHS[m - 1]} ${y}`),
      h('p', {}, 'Every sowing, transplant and harvest in your plan, plus frost dates — and for the next 16 days, the forecast, alerts and watering.')),
    h('div', { class: 'row' }, viewToggle('month', ymOf(first)),
      h('a', { class: 'btn', href: `#/calendar/${ymOf(prev)}`, 'aria-label': 'Previous month' }, '←'),
      h('a', { class: 'btn', href: `#/calendar/${ymOf(now)}` }, 'Today'),
      h('a', { class: 'btn', href: `#/calendar/${ymOf(next)}`, 'aria-label': 'Next month' }, '→'),
      h('button', { onclick: () => subscribeDialog(data) }, 'Add to my phone calendar')));

  function draw() {
    saveFilters(filters);
    const evs = visible(data.events, filters);
    const spans = data.spans.filter((s) => !filters.bed || String(s.bed_id) === String(filters.bed));
    const byDay = {};
    for (const e of evs) (byDay[e.date] ||= []).push(e);
    const grid = h('div', { class: 'month-grid', role: 'grid', 'aria-label': `${MONTHS[m - 1]} ${y}` },
      WEEKDAYS.map((w) => h('div', { class: 'mg-head', role: 'columnheader' }, w)));
    for (let d = new Date(gridStart); d <= gridEnd; d.setDate(d.getDate() + 1)) {
      const iso = isoDate(d);
      const dayEvents = byDay[iso] || [];
      const wx = data.weather[iso];
      const harvesting = uniq(spans.filter((s) => s.kind === 'harvesting' && s.start <= iso && s.end >= iso));
      const cell = h('button', {
        type: 'button', role: 'gridcell',
        class: `mg-cell${d.getMonth() !== m - 1 ? ' out' : ''}${iso === todayIso ? ' today' : ''}${iso === selected ? ' sel' : ''}`,
        'aria-label': `${fmtDay(iso)}: ${dayEvents.length} item${dayEvents.length === 1 ? '' : 's'}`,
        onclick: () => { selected = iso; draw(); dayBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); },
      },
      h('div', { class: 'mg-top' }, h('span', { class: 'mg-num' }, d.getDate()),
        wx ? h('span', { class: `mg-wx${wx.frost ? ' frost' : ''}`, title: `High ${wx.hi}°, low ${wx.lo}°${wx.rain >= 0.1 ? `, ${wx.rain}" rain` : ''}` },
          `${wx.hi}°/${wx.lo}°`, wx.rain >= 0.1 ? h('span', { class: 'mg-rain' }, ` ${wx.rain}"`) : null) : null),
      h('div', { class: 'mg-events' },
        dayEvents.slice(0, 3).map((e) => h('div', { class: `mg-ev k-${e.kind}`, title: `${e.title}${e.bed ? ` — ${e.bed}` : ''}` },
          eventDot(e), h('span', { class: 'mg-ev-t' }, e.title))),
        dayEvents.length > 3 ? h('div', { class: 'mg-more' }, `+${dayEvents.length - 3} more`) : null),
      harvesting.length && !filters.off.includes('harvest') ? h('div', { class: 'mg-harv' }, `${harvesting.length} to pick`) : null);
      grid.append(cell);
    }
    gridBox.replaceChildren(grid);
    dayBox.replaceChildren(dayPanel(selected, data, evs, spans));
  }

  const legend = h('div', { class: 'tiny' }, 'Tip: click a day for details. Filters are remembered on this device.');
  root.append(head, h('div', { class: 'card stack' }, filtersBar(data, filters, draw), gridBox, legend), dayBox);
  draw();
  return root;
}

function dayPanel(iso, data, evs, spans) {
  const dayEvents = evs.filter((e) => e.date === iso);
  const ongoing = evs.filter((e) => e.date < iso && e.end >= iso && e.kind === 'indoor');
  const wx = data.weather[iso];
  const harvesting = uniq(spans.filter((s) => s.kind === 'harvesting' && s.start <= iso && s.end >= iso));
  const growing = spans.filter((s) => s.kind === 'growing' && s.start <= iso && s.end >= iso);
  const card = h('div', { class: 'card stack day-panel' },
    h('div', { class: 'row between' }, h('h2', {}, fmtDate(iso, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })),
      wx ? h('div', { class: 'muted' }, `High ${wx.hi}°F · low ${wx.lo}°F`, wx.rain >= 0.01 ? ` · ${wx.rain}" rain${wx.rain_prob != null ? ` (${wx.rain_prob}%)` : ''}` : '',
        wx.soil != null ? ` · soil ${wx.soil}°F` : '', wx.frost ? ' · frost' : '') : null));
  if (!dayEvents.length && !ongoing.length) card.append(h('p', { class: 'muted' }, 'Nothing scheduled.'));
  for (const e of dayEvents) card.append(eventRow(e));
  if (ongoing.length) {
    card.append(h('div', { class: 'tiny' }, 'Still in the window: ' + ongoing.map((e) => `${e.title} (until ${fmtDate(e.end)})`).join('; ')));
  }
  if (harvesting.length) {
    card.append(h('div', {}, h('strong', {}, 'Ready to pick: '),
      harvesting.map((s) => `${s.name} (${s.bed})`).join(', ')));
  }
  if (growing.length) {
    const byBed = {};
    for (const s of growing) (byBed[s.bed] ||= new Set()).add(s.name);
    card.append(h('div', { class: 'tiny' }, h('strong', {}, 'In the ground: '),
      Object.entries(byBed).map(([b, names]) => `${b}: ${[...names].join(', ')}`).join(' · ')));
  }
  return card;
}

function eventRow(e) {
  const st = KIND_STYLE[e.kind];
  const actions = h('div', { class: 'row' });
  if (e.plant_id) actions.append(h('a', { class: 'btn small', href: `#/plants/${e.plant_id}` }, 'Plant info'));
  if (e.kind === 'plant' && e.planting_id) {
    actions.append(h('button', { class: 'small', onclick: () => markDone(e, 'established') }, 'I planted this'));
  }
  if (e.kind === 'harvest' && e.title.startsWith('Last') && e.planting_id) {
    actions.append(h('button', { class: 'small', onclick: () => markDone(e, 'finished') }, 'Record end of harvest'));
  }
  if (e.kind === 'water' && e.bed_id) {
    actions.append(h('button', { class: 'small', onclick: () => logWater(e) }, 'I watered'));
  }
  return h('div', { class: 'alert' }, eventDot(e),
    h('div', { class: 'title' }, e.title, e.bed ? h('span', { class: 'muted' }, ` · ${e.bed}`) : null,
      h('span', { class: 'badge', style: { marginLeft: '.4rem' } }, st.label)),
    e.detail ? h('div', { class: 'text' }, e.detail) : null,
    e.end !== e.date && e.kind !== 'care' ? h('div', { class: 'text' }, `Through ${fmtDate(e.end)}`) : null,
    actions.childNodes.length ? h('div', { class: 'text' }, actions) : null);
}

function markDone(e, field_) {
  const dateIn = h('input', { type: 'date', value: e.date });
  modal(field_ === 'established' ? 'Record planting' : 'Record the end of harvest', h('div', { class: 'stack' },
    h('p', {}, `${e.title}${e.bed ? ` (${e.bed})` : ''}. The real date re-times harvest, watering and the nitrogen plan.`),
    field('Date', dateIn)), [
    { label: 'Cancel' },
    { label: 'Save', class: 'primary', onClick: async () => {
      // only the field being recorded is sent; the other one is kept server-side
      const body = { year: Number(e.date.slice(0, 4)), [field_]: dateIn.value };
      await api(`/plantings/${e.planting_id}/actual`, { method: 'PUT', body });
      invalidate(); toast('Recorded'); rerender();
    } }]);
}

function logWater(e) {
  const inches = Number((e.detail || '').match(/([\d.]+)"/)?.[1] || 0.5);
  api('/waterings', { method: 'POST', body: { bed_id: e.bed_id, date: e.date <= isoDate(new Date()) ? e.date : isoDate(new Date()), inches } })
    .then(() => { invalidate(); toast(`Logged ${inches}" for ${e.bed}`); rerender(); })
    .catch((err) => toast(err.message));
}

// ---------------------------------------------------------------- agenda
async function renderAgenda() {
  const today = new Date();
  const end = new Date(today); end.setDate(end.getDate() + 90);
  const data = await cached(`/calendar/events?start=${isoDate(today)}&end=${isoDate(end)}`);
  const filters = loadFilters();
  const list = h('div', { class: 'stack' });
  function draw() {
    saveFilters(filters);
    const evs = visible(data.events, filters).filter((e) => e.date >= data.today || e.end >= data.today);
    const byDay = {};
    for (const e of evs) (byDay[e.date < data.today ? data.today : e.date] ||= []).push(e);
    const days = Object.keys(byDay).sort();
    list.replaceChildren(...(days.length ? days.map((iso) => {
      const wx = data.weather[iso];
      return h('div', { class: 'card agenda-day' },
        h('div', { class: 'row between' }, h('h3', {}, iso === data.today ? `Today · ${fmtDay(iso)}` : fmtDay(iso)),
          wx ? h('span', { class: 'muted' }, `${wx.hi}° / ${wx.lo}°${wx.rain >= 0.1 ? ` · ${wx.rain}" rain` : ''}`) : null),
        byDay[iso].map(eventRow));
    }) : [h('div', { class: 'empty' }, 'Nothing in the next 90 days with these filters.')]));
  }
  draw();
  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', {}, 'Coming up'), h('p', {}, 'The next 90 days, day by day.')),
      h('div', { class: 'row' }, viewToggle('agenda'), h('button', { onclick: () => subscribeDialog(data) }, 'Add to my phone calendar'))),
    h('div', { class: 'card' }, filtersBar(data, filters, draw)), list);
}

// ------------------------------------------------------------ subscribe
function subscribeDialog(data) {
  const filters = loadFilters();
  const kinds = Object.keys(KIND_STYLE).filter((k) => !['water', 'alert'].includes(k) && !filters.off.includes(k));
  const params = new URLSearchParams();
  if (kinds.length < 6) params.set('kinds', kinds.join(','));
  if (filters.bed) params.set('bed', filters.bed);
  const q = params.toString() ? `?${params}` : '';
  const url = `${location.origin}/api/calendar.ics${q}`;
  const webcal = url.replace(/^https?:/, 'webcal:');
  const input = h('input', { type: 'text', value: url, readonly: true, style: { width: '100%' }, onfocus: (e) => e.target.select() });
  modal('Add your garden to your calendar', h('div', { class: 'stack' },
    h('p', {}, 'Subscribe once and your sowing, transplanting and harvest dates appear in your normal calendar, updating as your plan changes.',
      filters.bed || filters.off.length ? ' Uses your current filters.' : ''),
    field('Calendar feed address', input),
    h('div', { class: 'row' },
      h('button', { onclick: async () => { try { await navigator.clipboard.writeText(url); toast('Copied'); } catch { input.select(); } } }, 'Copy address'),
      h('a', { class: 'btn', href: webcal }, 'Open in Apple Calendar / Outlook'),
      h('a', { class: 'btn', href: url, download: 'garden.ics' }, 'Download .ics')),
    h('ul', { class: 'tiny' },
      h('li', {}, 'iPhone/iPad: Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar, paste the address.'),
      h('li', {}, 'Mac, Outlook, Thunderbird: “New calendar subscription” and paste the address.'),
      h('li', {}, 'Google Calendar can’t reach a server on your home network — use “Download .ics”, then Google Calendar → Settings → Import (a one-time copy).'),
      h('li', {}, 'Your phone only refreshes the feed while it can reach this server (on your home Wi-Fi or VPN).'))),
  [{ label: 'Done' }]);
  return data;
}
