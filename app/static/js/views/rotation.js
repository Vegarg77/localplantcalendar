import { api, cached, invalidate } from '../api.js';
import { h, fmtDate, FEEDER, statusIcon, select, toast, getScope, scopeToggle } from '../ui.js';
import { plantingDialog } from './planting-modal.js';
import { coverCrops } from './food.js';
import { rerender } from '../app.js';

export async function renderRotation() {
  const rot = await cached('/rotation');
  const n = rot.cycle_years;

  const yearsSel = select(Array.from({ length: 8 }, (_, i) => ({ value: i + 1, label: `${i + 1}-year cycle` })), n);
  const startIn = h('input', { type: 'number', value: rot.start_year, min: 1990, max: 2200, style: { width: '6.5rem' } });
  const save = async () => {
    await api('/settings', { method: 'PUT', body: { cycle_years: Number(yearsSel.value), start_year: Number(startIn.value) } });
    invalidate(); toast('Rotation cycle updated'); rerender();
  };
  yearsSel.onchange = save; startIn.onchange = save;

  const scope = getScope();
  const cur = rot.current_cycle_year;
  const thisYear = rot.start_year + cur - 1;
  const shown = scope === 'year' ? [cur] : Array.from({ length: n }, (_, i) => i + 1);
  const toggle = scopeToggle(n, rerender);

  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, scope === 'year' ? `What grows where in ${thisYear}` : 'Rotation plan'),
      h('p', {}, scope === 'year'
        ? `Your beds this season. Crops move to a different bed each year so the soil gets a rest and pests lose track of them; switch to the full ${n}-year plan to see or change later years.`
        : `Each bed follows a ${n}-year cycle that repeats. Year 1 = ${rot.start_year}; this year is cycle year ${cur}.`)),
    h('div', { class: 'row' }, toggle,
      scope === 'all' ? [yearsSel, h('label', { class: 'check' }, 'Year 1 is', startIn)] : null,
      h('button', { class: 'primary', onclick: () => plantingDialog({ onSaved: rerender }) }, 'Add planting')));

  const legend = h('div', { class: 'legend' }, Object.values(FEEDER).map((f) =>
    h('span', { class: 'item' }, h('span', { class: 'key', style: { background: f.color } }), f.label)),
  h('span', { class: 'tiny' }, 'Classic sequence: legumes → heavy feeders → leafy → roots → legumes.'));

  // issues: only this season's unless the whole plan is shown
  const KIND = { family: 'Same crop family too soon', sequence: 'Hungry crops back to back',
    companion: 'Bad neighbors', space: 'Bed overfilled', cover: 'Bare over winter', timing: 'Timing' };
  const relevant = rot.issues.filter((i) => scope === 'all' || !i.years.length || i.years.includes(cur));
  const issues = h('div', { class: 'card' }, h('h2', {}, scope === 'year' ? `Things to check for ${thisYear}` : 'Rotation check'));
  if (!relevant.length) {
    issues.append(h('div', { class: 'alert' }, statusIcon('good'), h('div', { class: 'title' }, rot.rows.length ? 'No problems found' : 'Add beds and crops to check your rotation'),
      h('div', { class: 'text' }, 'Crop families, feeding order, neighbors, bed space and winter cover all look fine.')));
  }
  const order = { high: 0, warn: 1, info: 2 };
  // most serious first, then in rotation order
  const yr = (i) => i.cycle_year ?? Infinity;
  for (const i of [...relevant].sort((a, b) => order[a.severity] - order[b.severity] || yr(a) - yr(b))) {
    let text = i.text;
    if (i.kind === 'cover' && scope === 'year') {
      const names = i.by_year[cur] || [];
      text = `${names.length} bed${names.length === 1 ? '' : 's'} (${names.join(', ')}) will sit bare this winter. `
        + 'A winter cover crop keeps the soil from washing away, holds nitrogen that rain would carry off, and legumes like crimson clover add more for next year.';
    }
    const title = KIND[i.kind] || 'Note';
    issues.append(h('div', { class: 'alert' }, statusIcon(i.severity),
      h('div', { class: 'title' }, scope === 'all' && i.cycle_year ? `${title} · year ${i.cycle_year}` : title),
      h('div', { class: 'text' }, text),
      i.action === 'cover_crops' ? h('div', { class: 'text' }, h('button', { class: 'small', onclick: coverCrops }, 'Add winter cover crops')) : null));
  }

  // grid
  if (!rot.rows.length) {
    return h('div', { class: 'stack' }, head, h('div', { class: 'empty' }, 'No beds yet. ',
      h('a', { href: '#/setup' }, 'Add your beds'), ' on the Setup page, then plan what grows in each one, year by year.'));
  }
  const cols = `minmax(140px, 170px) repeat(${shown.length}, minmax(190px, 1fr))`;
  const grid = h('div', { class: 'rot' },
    h('div', { class: 'rot-head', style: { gridTemplateColumns: cols } }, h('div', {}, 'Bed'),
      shown.map((c) => h('div', {}, scope === 'year' ? `${rot.start_year + c - 1}` : `Year ${c} · ${rot.start_year + c - 1}`,
        scope === 'all' && c === cur ? ' (now)' : ''))));
  for (const row of rot.rows) {
    const b = row.bed;
    const r = h('div', { class: 'rot-row', style: { gridTemplateColumns: cols } },
      h('div', { class: 'rot-bed' }, h('strong', {}, b.name),
        h('div', { class: 'tiny' }, `${b.length_ft}×${b.width_ft} ft · ${b.area_sqft} sq ft`),
        h('div', { class: 'tiny' }, `${b.soil_profile.texture}, ${b.soil_profile.om_pct}% OM`),
        h('a', { class: 'tiny', href: `#/soil/${b.id}` }, 'Soil & feeding →')));
    for (const cell of row.cells.filter((x) => shown.includes(x.cycle_year))) {
      const c = h('div', { class: `rot-cell${scope === 'all' && cell.cycle_year === cur ? ' current' : ''}` });
      for (const pl of cell.plantings) {
        const inst = pl.instances.find((x) => x.year === cell.calendar_year) || pl.instances[0];
        const when = inst ? `${fmtDate(inst.establish || inst.start)} → ${fmtDate(inst.harvest_end)}` : '';
        c.append(h('button', { class: 'pchip', type: 'button', title: 'Edit',
          onclick: () => plantingDialog({ planting: pl, onSaved: rerender }) },
          h('span', { class: 'key', style: { background: FEEDER[pl.feeder].color } }),
          h('span', {}, pl.name, pl.successions > 1 ? ` ×${pl.successions}` : '',
            h('small', {}, [when, pl.lifecycle === 'perennial' ? 'perennial' : null,
              pl.area_sqft ? `${pl.area_sqft} sq ft` : 'whole bed', pl.category === 'cover' ? 'cover crop' : null]
              .filter(Boolean).join(' · ')))));
      }
      if (!cell.plantings.length && cell.suggest) c.append(h('div', { class: 'suggest' }, `Suggested: ${cell.suggest}`));
      c.append(h('button', { class: 'small', style: { marginTop: 'auto', alignSelf: 'flex-start' },
        onclick: () => plantingDialog({ bedId: b.id, cycleYear: cell.cycle_year, onSaved: rerender }) }, '+ Add'));
      r.append(c);
    }
    grid.append(r);
  }

  return h('div', { class: 'stack' }, head, legend, h('div', { class: 'card', style: { overflowX: 'auto' } }, grid), issues,
    h('p', { class: 'tiny' }, 'Tip: plant a winter cover crop (cereal rye, hairy vetch, crimson clover) after your last harvest — it holds nitrogen over winter and legumes add more for next year.'));
}
