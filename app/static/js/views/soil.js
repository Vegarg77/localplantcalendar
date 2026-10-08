import { api, cached, invalidate } from '../api.js';
import { lineChart } from '../charts.js';
import { h, f0, f1, f2, fmtDate, parseDate, statusIcon, FEEDER, modal, field, select, toast, idxToLabel, monthDayToIdx } from '../ui.js';
import { rerender } from '../app.js';

const OZ_PER_LB_ACRE = (area) => area / 43560 * 16;

export async function renderSoil(bedArg) {
  const [beds, settings] = await Promise.all([cached('/beds'), cached('/settings')]);
  if (!beds.beds.length) {
    return h('div', { class: 'empty' }, 'No beds yet. ', h('a', { href: '#/setup' }, 'Add your beds'), ' to see soil and nitrogen.');
  }
  const bed = beds.beds.find((b) => b.id === Number(bedArg)) || beds.beds[0];
  const [n, plants, amend, products] = await Promise.all([
    cached(`/nitrogen/${bed.id}`), cached('/plants'), cached('/amendments'), cached('/products')]);
  const feederOf = Object.fromEntries(plants.plants.map((p) => [p.id, p.feeder]));
  const sp = bed.soil_profile;
  const ozPer = OZ_PER_LB_ACRE(bed.area_sqft);

  const picker = h('div', { class: 'chips' }, beds.beds.map((b) =>
    h('a', { class: `chip${b.id === bed.id ? ' on' : ''}`, href: `#/soil/${b.id}` }, b.name)));

  const fact = (k, v) => h('div', { class: 'fact' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v));
  const soilCard = h('div', { class: 'card stack' },
    h('h2', {}, `Soil in ${bed.name}`),
    h('div', { class: 'facts' },
      fact('Texture', `${sp.texture} (${f0(sp.sand)}% sand, ${f0(sp.silt)}% silt, ${f0(sp.clay)}% clay)`),
      fact('Organic matter', `${f1(sp.om_pct)}%`),
      fact('pH', f1(sp.ph)),
      fact('Water holding', `${f2(sp.awc)} in per inch of soil`),
      sp.drainage ? fact('Drainage', sp.drainage) : null,
      sp.cec ? fact('CEC', `${f1(sp.cec)} meq/100g`) : null,
      fact('Starting nitrate', `${f0(bed.initial_no3_ppm)} ppm`)),
    h('p', { class: 'tiny' }, `Source: ${sp.name ? `${sp.name} — ` : ''}${sp.source}. `,
      h('a', { href: '#/setup' }, 'Edit bed soil'), ' with lab results when you have them.'));

  // ------------------------------------------------------------ N chart
  const x = n.series.map((p) => p.date);
  const lanes = laneCrops(n.crops);
  const t0 = parseDate(x[0]), t1 = parseDate(x[x.length - 1]);
  const pct = (iso) => Math.max(0, Math.min(1, (parseDate(iso) - t0) / (t1 - t0))) * 100;
  const strip = h('div', { style: { position: 'relative', marginLeft: '40px', marginRight: '16px', height: `${lanes.length * 22 + 4}px` } });
  lanes.forEach((lane, li) => lane.forEach((c) => {
    const left = pct(c.start), width = Math.max(pct(c.end) - left, 0.5);
    strip.append(h('div', {
      title: `${c.name} ${fmtDate(c.start)} – ${fmtDate(c.end, { month: 'short', day: 'numeric', year: 'numeric' })}`,
      style: { position: 'absolute', top: `${li * 22}px`, left: `${left}%`, width: `${width}%`, height: '18px',
        borderRadius: '4px', background: 'var(--surface-2)', borderLeft: `4px solid ${FEEDER[feederOf[c.plant_id]]?.color || 'var(--axis)'}`,
        fontSize: '.72rem', padding: '1px 4px', overflow: 'hidden', whiteSpace: 'nowrap', color: 'var(--ink-2)' } }, c.name));
  }));
  const nChart = lineChart({
    x, unit: ' ppm', height: 230, yMin: 0,
    series: [{ name: 'Plant-available N', color: 'var(--s1)', area: true, values: n.series.map((p) => p.ppm) }],
    refs: [{ y: 10, label: 'Low (<10 ppm)' }], title: 'Projected plant-available nitrogen',
  });
  const omChart = lineChart({
    x, unit: '%', height: 120, yFormat: (v) => f1(v),
    series: [{ name: 'Organic matter', color: 'var(--s3)', values: n.series.map((p) => p.om_pct) }],
    title: 'Projected soil organic matter',
  });

  const nCard = h('div', { class: 'card stack' },
    h('h2', {}, 'Nitrogen over your rotation'),
    h('p', { class: 'tiny' }, `Daily model over ${n.years.length} years (two passes through your ${settings.cycle_years}-year cycle): organic matter mineralises with soil temperature, crops take N up along their growth curve, legumes and residues give it back, wet months with no crop leach it. Nitrate in the top foot; 1 ppm ≈ ${f2(4 * ozPer)} oz N in this bed.`),
    h('h3', {}, 'Plant-available nitrogen (ppm NO₃-N)'), nChart,
    h('div', { class: 'legend' }, Object.values(FEEDER).map((f) => h('span', { class: 'item' }, h('span', { class: 'key', style: { background: f.color } }), f.label))),
    strip,
    h('h3', {}, 'Soil organic matter (%)'), omChart);

  // ---------------------------------------------------------- recommendations
  const recs = h('div', { class: 'card' }, h('h2', {}, 'What to do'));
  if (!n.recommendations.length) recs.append(h('div', { class: 'alert' }, statusIcon('good'), h('div', { class: 'title' }, 'Nitrogen looks balanced'), h('div', { class: 'text' }, 'No crop is projected to run short and losses are small.')));
  for (const r of n.recommendations) {
    recs.append(h('div', { class: 'alert' }, statusIcon(r.severity), h('div', { class: 'title' }, { deficit: 'Shortfall', leaching: 'Winter leaching', organic_matter: 'Organic matter' }[r.kind] || 'Note'), h('div', { class: 'text' }, r.text)));
  }

  // ---------------------------------------------------------- yearly table
  const yt = h('div', { class: 'card' }, h('h2', {}, 'Year-by-year budget (lb N per acre)'),
    h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Year', 'Cycle yr', 'Start', 'From soil OM', 'Residue', 'Amendments', 'Fixed', 'Crop uptake', 'Leached', 'Shortfall', 'End OM %']
        .map((c, i) => h('th', { class: i > 1 ? 'num' : '' }, c)))),
      h('tbody', {}, n.years.map((y) => h('tr', {},
        h('td', {}, y.year), h('td', {}, y.cycle_year),
        ...[y.start_mineral, y.mineralized, y.residue, y.amendments, y.fixed, y.uptake, y.leached, y.deficit].map((v) => h('td', { class: 'num' }, f0(v))),
        h('td', { class: 'num' }, f2(y.end_om_pct))))))),
    h('p', { class: 'tiny' }, `Multiply by ${f2(ozPer)} for ounces of N in this ${bed.area_sqft} sq ft bed.`));

  const ct = h('div', { class: 'card' }, h('h2', {}, 'Crops'),
    h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Crop', 'Planted', 'Needs', 'Got', 'Short', 'Short (oz N, bed)'].map((c, i) => h('th', { class: i > 1 ? 'num' : '' }, c)))),
      h('tbody', {}, n.crops.map((c) => h('tr', {},
        h('td', {}, h('span', { class: 'key', style: { background: FEEDER[feederOf[c.plant_id]]?.color, marginRight: '.4rem' } }), c.name),
        h('td', {}, fmtDate(c.start, { month: 'short', year: 'numeric' })),
        h('td', { class: 'num' }, c.fixer ? 'fixes' : f0(c.demand_lb_acre)), h('td', { class: 'num' }, f0(c.taken_lb_acre)),
        h('td', { class: 'num' }, c.fixer ? '—' : f0(c.deficit_lb_acre)), h('td', { class: 'num' }, c.fixer ? '—' : f2(c.deficit_n_oz_bed))))))));

  // ---------------------------------------------------------- amendments
  const mine = amend.amendments.filter((a) => a.bed_id === bed.id);
  const am = h('div', { class: 'card stack' }, h('h2', {}, 'Planned amendments'),
    h('p', { class: 'tiny' }, 'Amendments repeat every cycle on the same rotation year — they feed straight into the model above.'));
  if (mine.length) {
    am.append(h('table', {}, h('tbody', {}, mine.map((a) => h('tr', {},
      h('td', {}, `Year ${a.cycle_year}, ${idxToLabel(a.doy)}`),
      h('td', {}, `${a.amount_lb} lb ${products[a.product]?.name || a.product}`),
      h('td', {}, h('button', { class: 'small danger', onclick: async () => {
        await api(`/amendments/${a.id}`, { method: 'DELETE' }); invalidate(); rerender();
      } }, 'Remove')))))));
  }
  am.append(h('button', { onclick: () => amendDialog(bed, settings, products) }, '+ Add amendment'));

  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Soil & nitrogen'),
      h('p', {}, 'How each bed’s nitrogen rises and falls as crops, cover crops and compost cycle through.'))),
    picker,
    h('div', { class: 'grid grid-2' }, soilCard, recs),
    nCard, yt, h('div', { class: 'grid grid-2' }, ct, am));
}

function laneCrops(crops) {
  const lanes = [];
  const sorted = [...crops].sort((a, b) => a.start.localeCompare(b.start));
  for (const c of sorted) {
    let lane = lanes.find((l) => l[l.length - 1].end < c.start);
    if (!lane) { lane = []; lanes.push(lane); }
    lane.push(c);
  }
  return lanes;
}

function amendDialog(bed, settings, products) {
  const prod = select(Object.entries(products).map(([k, v]) => ({ value: k, label: `${v.name} — ${v.n_pct}% N` })), 'compost');
  const amt = h('input', { type: 'number', min: 0.1, step: 0.1, value: 10 });
  const date = h('input', { type: 'text', value: '04-01', placeholder: 'MM-DD', size: 6 });
  const yr = select(Array.from({ length: settings.cycle_years }, (_, i) => ({ value: i + 1, label: `Year ${i + 1}` })), settings.current_cycle_year);
  const hint = h('div', { class: 'tiny' });
  const upd = () => {
    const p = products[prod.value];
    const nLb = Number(amt.value || 0) * p.n_pct / 100;
    hint.textContent = `${f2(nLb * 16)} oz of N for ${bed.area_sqft} sq ft (${f0(nLb * 43560 / bed.area_sqft)} lb N/acre), ~${Math.round(p.available * 100)}% available this season.` +
      (prod.value === 'compost' ? ' 1 cu ft of compost weighs ~40–50 lb.' : '');
  };
  prod.onchange = upd; amt.oninput = upd; upd();
  modal(`Add amendment — ${bed.name}`, h('div', { class: 'stack' },
    h('div', { class: 'form-grid' }, field('Product', prod), field('Amount (lb)', amt), field('Date (MM-DD)', date), field('Rotation year', yr)), hint), [
    { label: 'Cancel' },
    { label: 'Add', class: 'primary', onClick: async () => {
      monthDayToIdx(date.value);
      await api('/amendments', { method: 'POST', body: { bed_id: bed.id, cycle_year: Number(yr.value), date: date.value, product: prod.value, amount_lb: Number(amt.value) } });
      invalidate(); toast('Amendment added'); rerender();
    } }]);
}
