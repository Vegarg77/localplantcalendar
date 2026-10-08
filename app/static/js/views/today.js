import { api, cached, invalidate } from '../api.js';
import { lineChart, columnChart } from '../charts.js';
import { h, fmtDate, fmtDay, f0, f1, f2, statusBadge, statusIcon, toast, modal, field, isoDate } from '../ui.js';
import { rerender } from '../app.js';

export async function renderToday() {
  const [site, fc] = await Promise.all([cached('/site'), cached('/forecast')]);
  const c = site.climate;
  const today = fc.today;
  const td = fc.days.find((d) => d.date === today) || {};

  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, site.location.name),
      h('p', {}, `${fmtDate(today, { weekday: 'long', month: 'long', day: 'numeric' })} · climate from ${c.years}`)),
    h('button', { onclick: async () => {
      await api('/refresh', { method: 'POST' }); invalidate(); toast('Forecast refreshed'); rerender();
    } }, 'Refresh forecast'));

  const risk = (obj) => obj['0.5'] ? `${obj['0.5']}` : 'none';
  const stats = h('div', { class: 'stats' },
    stat('Hardiness zone', site.zone ? site.zone.zone : c.zone_estimate, site.zone ? site.zone.temperature_range ? `${site.zone.temperature_range} °F` : 'estimated' : 'estimated'),
    stat('Last spring frost', risk(c.last_spring_frost), c.last_spring_frost['0.1'] ? `1-in-10 risk after ${c.last_spring_frost['0.1']}` : 'frost-free most years'),
    stat('First fall frost', risk(c.first_fall_frost), c.first_fall_frost['0.1'] ? `1-in-10 risk before ${c.first_fall_frost['0.1']}` : ''),
    stat('Frost-free season', `${c.season_days} days`, 'median'),
    stat('Today', td.tmax_f != null ? `${f0(td.tmax_f)}° / ${f0(td.tmin_f)}°` : '—',
      `normal ${f0(fc.normals.high)}° / ${f0(fc.normals.low)}°` + (td.soil_f != null ? ` · soil ${f0(td.soil_f)}°` : '')),
  );

  // ---------------------------------------------------------------- alerts
  const alerts = h('div', { class: 'card' }, h('h2', {}, 'Weather alerts'));
  if (!fc.alerts.length) alerts.append(h('p', { class: 'muted' }, 'Nothing to worry about in the 16-day forecast for what you have planted.'));
  const list = h('div', {});
  for (const a of fc.alerts) {
    list.append(h('div', { class: 'alert' }, statusIcon(a.severity),
      h('div', { class: 'title' }, a.title), h('div', { class: 'text' }, a.text)));
  }
  alerts.append(list);

  // ----------------------------------------------------------------- tasks
  const tasks = h('div', { class: 'card' }, h('h2', {}, 'Next two weeks'));
  if (!fc.tasks.length) {
    tasks.append(h('p', { class: 'muted' }, 'No sowing, transplanting or harvests scheduled in the next two weeks. ',
      h('a', { href: '#/plants' }, 'Browse plants'), ' to add crops to your rotation.'));
  }
  for (const t of fc.tasks) {
    const sev = t.kind === 'plant' ? (t.verdict === 'go' ? 'good' : 'warn') : 'info';
    const label = t.kind === 'plant' ? (t.verdict === 'go' ? 'Go' : 'Wait') :
      { indoor: 'Indoors', harden: 'Harden off', harvest: 'Harvest', terminate: 'Cover crop' }[t.kind];
    const row = h('div', { class: 'alert' }, statusBadge(sev, label),
      h('div', { class: 'title' }, `${fmtDay(t.date)} — ${t.title}${t.bed ? ` (${t.bed})` : ''}`),
      h('div', { class: 'text' }, t.text));
    if (t.kind === 'plant') {
      row.append(h('div', { class: 'text' }, h('button', { class: 'small', onclick: () => markPlanted(t) }, 'I planted this')));
    }
    tasks.append(row);
  }

  // -------------------------------------------------------------- forecast
  const days = fc.days.filter((d) => d.date >= today);
  const strip = h('div', { class: 'forecast-strip' }, days.map((d) => h('div', { class: `fday${d.date === today ? ' today' : ''}` },
    h('div', {}, fmtDate(d.date, { weekday: 'short' })),
    h('div', { class: 'tiny' }, fmtDate(d.date)),
    h('div', { class: 'hi' }, `${f0(d.tmax_f)}°`),
    h('div', { class: 'lo' }, `${f0(d.tmin_f)}°`),
    h('div', { class: 'rain' }, d.precip_in >= 0.01 ? `${f2(d.precip_in)}"` : '·'))));
  const temps = lineChart({
    x: days.map((d) => d.date), unit: '°F', height: 210,
    series: [
      { name: 'High', color: 'var(--s2)', values: days.map((d) => d.tmax_f && Math.round(d.tmax_f)) },
      { name: 'Low', color: 'var(--s1)', values: days.map((d) => d.tmin_f && Math.round(d.tmin_f)) },
      { name: 'Soil (2–3")', color: 'var(--s3)', dashed: true, values: days.map((d) => d.soil_f && Math.round(d.soil_f)) },
    ],
    refs: [{ y: 32, label: 'Frost 32°F' }], title: '16-day temperature forecast',
  });
  const rain = columnChart({
    labels: days.map((d) => fmtDate(d.date)), unit: '"', height: 130, yFormat: (v) => f2(v),
    series: [{ name: 'Rain', color: 'var(--s1)', values: days.map((d) => d.precip_in) }],
    title: 'Forecast rain (inches)',
  });
  const forecast = h('div', { class: 'card stack' }, h('h2', {}, '16-day forecast'), strip,
    h('h3', {}, 'Temperature (°F)'), temps, h('h3', {}, 'Rain (inches)'), rain);

  // -------------------------------------------------------------- watering
  const water = h('div', { class: 'card stack' }, h('h2', {}, 'Watering'),
    h('p', { class: 'tiny' }, 'FAO-56 water balance: crop water use (ET₀ × crop coefficient) minus rain, using your soil’s water-holding capacity. Log waterings for better accuracy; otherwise it assumes you watered when due.'));
  if (!fc.watering.length) water.append(h('p', { class: 'muted' }, 'Add beds on the Setup page to get watering advice.'));
  for (const w of fc.watering) {
    const pct = w.available_water_pct;
    const row = h('div', { class: 'stack', style: { borderTop: '1px solid var(--border)', paddingTop: '.6rem' } },
      h('div', { class: 'row between' }, h('strong', {}, w.bed),
        h('button', { class: 'small', onclick: () => logWater(w) }, 'Log watering')));
    if (pct === null) {
      row.append(h('div', { class: 'muted' }, 'Nothing growing right now — no watering needed.'));
    } else {
      row.append(h('div', { class: 'row' }, h('div', { class: 'meter', style: { flex: 1 } },
        h('div', { style: { width: `${Math.max(0, Math.min(100, pct))}%` } })),
      h('span', { class: 'num' }, `${pct}% of available water left`)));
      row.append(h('div', {}, w.next
        ? [h('strong', {}, `Water ${fmtDay(w.next.date)}: `), `${f2(w.next.inches)}" ≈ ${f0(w.next.gallons)} gal`]
        : h('span', {}, 'No watering needed in the forecast period.')));
      row.append(h('div', { class: 'tiny' }, `Next 7 days: crops use ${f2(w.week.crop_use_in)}", rain supplies ~${f2(w.week.rain_in)}", plan to add ${f2(w.week.irrigation_in)}".`));
    }
    water.append(row);
  }

  // -------------------------------------------------------------- progress
  const prog = h('div', { class: 'card' }, h('h2', {}, 'Growth vs. normal'));
  if (!fc.progress.length) prog.append(h('p', { class: 'muted' }, 'Crops in the ground appear here, with harvest dates re-projected from actual temperatures (growing degree days).'));
  else {
    prog.append(h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Crop'), h('th', {}, 'Bed'),
      h('th', {}, 'Planned'), h('th', {}, 'Now projected'), h('th', {}, ''))),
    h('tbody', {}, fc.progress.map((p) => h('tr', {}, h('td', {}, p.name), h('td', {}, p.bed),
      h('td', {}, fmtDate(p.planned)), h('td', {}, fmtDate(p.projected)), h('td', { class: 'muted' }, p.text))))));
  }

  // -------------------------------------------------------------- plant now
  const now = h('div', { class: 'card' }, h('h2', {}, 'Open planting windows this week'),
    h('p', { class: 'tiny' }, 'From the whole plant library, based on your 30-year climate.'));
  const groups = {};
  for (const p of fc.plant_now) (groups[p.category] ||= []).push(p);
  for (const [cat, ps] of Object.entries(groups)) {
    now.append(h('h3', { style: { marginTop: '.6rem' } }, cat[0].toUpperCase() + cat.slice(1)),
      h('div', { class: 'chips' }, ps.map((p) => h('a', { class: 'chip', href: `#/plants/${p.id}`,
        title: `${p.method === 'transplant' ? 'Transplant' : 'Sow'} until ${p.until}` }, `${p.name} · until ${p.until}`))));
  }
  if (!fc.plant_now.length) now.append(h('p', { class: 'muted' }, 'Nothing is in its outdoor window this week — a good time to plan.'));

  return h('div', { class: 'stack' }, head, stats,
    h('div', { class: 'grid grid-2' }, alerts, tasks),
    forecast,
    h('div', { class: 'grid grid-2' }, water, prog),
    now);
}

function stat(label, value, sub) {
  return h('div', { class: 'stat' }, h('div', { class: 'label' }, label),
    h('div', { class: 'value' }, value), sub ? h('div', { class: 'sub' }, sub) : null);
}

function markPlanted(t) {
  const dateIn = h('input', { type: 'date', value: isoDate(new Date()) });
  modal('Record planting', h('div', { class: 'stack' },
    h('p', {}, `${t.title}. Recording the actual date re-times the harvest, watering and nitrogen plan for this year.`),
    field('Planted on', dateIn)), [
    { label: 'Cancel' },
    { label: 'Save', class: 'primary', onClick: async () => {
      await api(`/plantings/${t.planting_id}/actual`, { method: 'PUT',
        body: { year: Number(dateIn.value.slice(0, 4)), established: dateIn.value } });
      invalidate(); toast('Recorded'); rerender();
    } }]);
}

function logWater(w) {
  const dateIn = h('input', { type: 'date', value: isoDate(new Date()) });
  const inIn = h('input', { type: 'number', step: 0.1, min: 0.1, value: w.next ? w.next.inches : 0.5 });
  const gal = h('span', { class: 'tiny' });
  const upd = () => { gal.textContent = `≈ ${f1(Number(inIn.value || 0) * w.area_sqft * 0.623)} gallons for ${w.area_sqft} sq ft`; };
  inIn.oninput = upd; upd();
  modal(`Log watering — ${w.bed}`, h('div', { class: 'form-grid' }, field('Date', dateIn), field('Inches applied', inIn), gal), [
    { label: 'Cancel' },
    { label: 'Save', class: 'primary', onClick: async () => {
      await api('/waterings', { method: 'POST', body: { bed_id: w.bed_id, date: dateIn.value, inches: Number(inIn.value) } });
      invalidate(); toast('Logged'); rerender();
    } }]);
}
