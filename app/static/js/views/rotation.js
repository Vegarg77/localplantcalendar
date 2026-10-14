import { api, cached, invalidate } from '../api.js';
import { h, fmtDate, FEEDER, statusIcon, select, toast } from '../ui.js';
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

  const head = h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, 'Rotation plan'),
      h('p', {}, `Each bed follows a ${n}-year cycle that repeats. Year 1 = ${rot.start_year}; this year is cycle year ${rot.current_cycle_year}.`)),
    h('div', { class: 'row' }, yearsSel, h('label', { class: 'check' }, 'Year 1 is', startIn),
      h('button', { onclick: coverCrops }, 'Add winter cover crops'),
      h('button', { class: 'primary', onclick: () => plantingDialog({ onSaved: rerender }) }, 'Add planting')));

  const legend = h('div', { class: 'legend' }, Object.values(FEEDER).map((f) =>
    h('span', { class: 'item' }, h('span', { class: 'key', style: { background: f.color } }), f.label)),
  h('span', { class: 'tiny' }, 'Classic sequence: legumes → heavy feeders → leafy → roots → legumes.'));

  // issues
  const issues = h('div', { class: 'card' }, h('h2', {}, 'Rotation check'));
  if (!rot.issues.length) {
    issues.append(h('div', { class: 'alert' }, statusIcon('good'), h('div', { class: 'title' }, rot.rows.length ? 'No problems found' : 'Add beds and crops to check your rotation'),
      h('div', { class: 'text' }, 'Family spacing, feeding order, companions, bed space and winter cover all look fine.')));
  }
  const order = { high: 0, warn: 1, info: 2 };
  // by cycle year so the list reads left to right like the grid; most serious first within a year
  const yr = (i) => i.cycle_year ?? Infinity;
  for (const i of [...rot.issues].sort((a, b) => yr(a) - yr(b) || order[a.severity] - order[b.severity])) {
    issues.append(h('div', { class: 'alert' }, statusIcon(i.severity),
      h('div', { class: 'title' }, `Year ${i.cycle_year ?? '–'}`), h('div', { class: 'text' }, i.text)));
  }

  // grid
  if (!rot.rows.length) {
    return h('div', { class: 'stack' }, head, h('div', { class: 'empty' }, 'No beds yet. ',
      h('a', { href: '#/setup' }, 'Add your beds'), ' on the Setup page, then plan what grows in each one, year by year.'));
  }
  const cols = `minmax(140px, 170px) repeat(${n}, minmax(190px, 1fr))`;
  const grid = h('div', { class: 'rot' },
    h('div', { class: 'rot-head', style: { gridTemplateColumns: cols } }, h('div', {}, 'Bed'),
      Array.from({ length: n }, (_, i) => h('div', {}, `Year ${i + 1} · ${rot.start_year + i}`,
        i + 1 === rot.current_cycle_year ? ' (now)' : ''))));
  for (const row of rot.rows) {
    const b = row.bed;
    const r = h('div', { class: 'rot-row', style: { gridTemplateColumns: cols } },
      h('div', { class: 'rot-bed' }, h('strong', {}, b.name),
        h('div', { class: 'tiny' }, `${b.length_ft}×${b.width_ft} ft · ${b.area_sqft} sq ft`),
        h('div', { class: 'tiny' }, `${b.soil_profile.texture}, ${b.soil_profile.om_pct}% OM`),
        h('a', { class: 'tiny', href: `#/soil/${b.id}` }, 'Nitrogen →')));
    for (const cell of row.cells) {
      const c = h('div', { class: `rot-cell${cell.cycle_year === rot.current_cycle_year ? ' current' : ''}` });
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
    h('p', { class: 'tiny' }, 'Tip: plant a winter cover crop (cereal rye, hairy vetch, crimson clover) after your last harvest — it holds nitrogen over winter and legumes add more for next year. See the Soil & N tab for the numbers.'));
}
