import { api, cached, invalidate } from '../api.js';
import { lineChart } from '../charts.js';
import { h, f0, f1, f2, fmtDate, parseDate, statusIcon, FEEDER, modal, field, select, toast, idxToLabel, monthDayToIdx, getScope, scopeToggle, npkTag } from '../ui.js';
import { rerender } from '../app.js';

const OZ_PER_LB_ACRE = (area) => area / 43560 * 16;

export async function renderSoil(bedArg) {
  const [beds, settings] = await Promise.all([cached('/beds'), cached('/settings')]);
  if (!beds.beds.length) {
    return h('div', { class: 'empty' }, 'No beds yet. ', h('a', { href: '#/setup' }, 'Add your beds'), ' to see what to feed them.');
  }
  const scope = getScope();
  const today = settings.today;
  const thisYear = Number(today.slice(0, 4));
  const cyc = settings.cycle_years;
  // "this year" also loads next year, shown once this year's feedings are all done
  const planYears = scope === 'year' ? [thisYear, thisYear + 1]
    : Array.from({ length: cyc }, (_, i) => settings.start_year + i);
  const bed = beds.beds.find((b) => b.id === Number(bedArg)) || beds.beds[0];
  const [n, nu, plants, amend, products, plantings, ...loaded] = await Promise.all([
    cached(`/nitrogen/${bed.id}`), cached(`/nutrients/${bed.id}?year=${thisYear}`), cached('/plants'), cached('/amendments'), cached('/products'), cached('/plantings'),
    ...planYears.map((y) => cached(`/feeding-plan?year=${y}`))]);
  const feederOf = Object.fromEntries(plants.plants.map((p) => [p.id, p.feeder]));
  const inYear = (iso) => scope === 'all' || iso.startsWith(String(thisYear));

  // ------------------------------------------------------- garden feeding plan
  let plans = loaded, done = null;
  if (scope === 'year') {
    const [now, next] = loaded;
    const left = now.steps.some((st) => st.date >= today);
    plans = [left || !next.steps.length ? now : next];
    if (!left && next.steps.length && now.steps.length) done = now;
  }
  const planYear = plans[0].year;
  const plan = h('div', { class: 'card stack' }, h('h2', {}, scope === 'year' ? `Feeding plan for ${planYear}` : 'Feeding plan, year by year'));
  if (done) {
    plan.append(h('p', { class: 'muted' }, `All of ${done.year}’s feedings are done, so here’s what’s coming next season.`));
  }
  const allSteps = plans.flatMap((pl) => pl.steps);
  if (!allSteps.length) {
    plan.append(h('div', { class: 'alert' }, statusIcon('good'), h('div', { class: 'title' }, 'Nothing to add'),
      h('div', { class: 'text' }, settings.auto_feed === false
        ? 'Automatic feeding is off (Setup → Preferences). Each bed below says whether it runs short.'
        : 'Your soil, compost and cover crops already give every crop the nitrogen it needs.')));
  } else {
    const used = [...new Map(plans.flatMap((pl) => pl.products).map((p) => [p.id, p])).values()];
    const nBeds = new Set(allSteps.map((x) => x.bed_id)).size;
    plan.append(h('div', { class: 'explain' },
      `${allSteps.length} feeding${allSteps.length === 1 ? '' : 's'} across ${nBeds} bed${nBeds === 1 ? '' : 's'}, each timed to when the crop needs it. `,
      used.length ? ['You’ll need: ', used.map((p, i) => [i ? ', ' : '', p.name.toLowerCase(), p.npk ? [' (', npkTag(p.npk), ')'] : null]), '.'] : null,
      h('div', { class: 'tiny', style: { marginTop: '.3rem' } }, plans[0].npk_help)));
    for (const pl of plans) {
      if (scope === 'all') plan.append(h('h3', {}, `${pl.year} (rotation year ${pl.cycle_year})`));
      if (!pl.steps.length) { plan.append(h('p', { class: 'muted' }, 'No feedings this year.')); continue; }
      plan.append(h('ol', { class: 'feed-list' }, pl.steps.map((st) => feedStep(st, today))));
    }
  }
  if (done) {
    plan.append(h('details', {}, h('summary', { class: 'tiny' }, `Done in ${done.year} (${done.steps.length})`),
      h('ol', { class: 'feed-list' }, done.steps.map((st) => feedStep(st, today)))));
  }
  plan.append(h('p', { class: 'tiny' }, 'These also show on your Calendar, and on the Today page when they come due. ',
    settings.auto_feed !== false ? 'Change the fertilizer in Setup → Preferences.' : ''));

  // ---------------------------------------------------------------- bed view
  const picker = h('div', { class: 'chips' }, beds.beds.map((b) =>
    h('a', { class: `chip${b.id === bed.id ? ' on' : ''}`, href: `#/soil/${b.id}` }, b.name)));
  const sp = bed.soil_profile;
  const ozPer = OZ_PER_LB_ACRE(bed.area_sqft);
  const fact = (k, v) => h('div', { class: 'fact' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v));
  const soilCard = h('div', { class: 'card stack' },
    h('h2', {}, `Soil in ${bed.name}`),
    h('p', {}, soilSummary(sp)),
    nutrientBlock(nu),
    h('details', {}, h('summary', { class: 'tiny' }, 'Soil details'),
      h('div', { class: 'facts', style: { marginTop: '.5rem' } },
        fact('Texture', `${sp.texture} (${f0(sp.sand)}% sand, ${f0(sp.silt)}% silt, ${f0(sp.clay)}% clay)`),
        fact('Organic matter', `${f1(sp.om_pct)}%`),
        fact('pH', f1(sp.ph)),
        fact('Water holding', `${f2(sp.awc)} in per inch of soil`),
        sp.drainage ? fact('Drainage', sp.drainage) : null,
        sp.cec ? fact('CEC', `${f1(sp.cec)} meq/100g`) : null,
        fact('Starting nitrate', `${f0(bed.initial_no3_ppm)} ppm`))),
    h('p', { class: 'tiny' }, `Source: ${sp.name ? `${sp.name} — ` : ''}${sp.source}. `,
      h('a', { href: '#/setup' }, 'Edit bed soil'), ' with soil-test results when you have them.'));

  // what this bed needs, in plain words
  const crops = n.crops.filter((c) => inYear(c.start) || inYear(c.end));
  const cropNames = [...new Set(crops.map((c) => c.name))];
  const bedSteps = (scope === 'year' ? loaded[0].steps : allSteps).filter((st) => st.bed_id === bed.id);
  const short = n.recommendations.filter((r) => r.kind === 'deficit' && (scope === 'all' || r.year === thisYear));
  const needs = h('div', { class: 'card stack' }, h('h2', {}, scope === 'year' ? `${bed.name} in ${thisYear}` : bed.name));
  needs.append(h('p', {}, cropNames.length ? `Growing: ${cropNames.join(', ')}.` : 'Nothing planned here this year.'));
  if (short.length) {
    for (const r of short) {
      needs.append(h('div', { class: 'alert' }, statusIcon(r.severity), h('div', { class: 'title' }, r.headline || 'Runs short'),
        r.options?.length ? h('ul', { class: 'text' }, r.options.map((o) => h('li', {}, o))) : h('div', { class: 'text' }, r.text)));
    }
  } else if (bedSteps.length) {
    needs.append(h('div', { class: 'alert' }, statusIcon('good'), h('div', { class: 'title' }, 'Covered by the feeding plan'),
      h('div', { class: 'text' }, `${bedSteps.length === 1 ? 'One feeding gives' : `${bedSteps.length} feedings give`} these crops what the soil can’t (see the feeding plan).`)));
  } else if (cropNames.length) {
    needs.append(h('div', { class: 'alert' }, statusIcon('good'), h('div', { class: 'title' }, 'No feeding needed'),
      h('div', { class: 'text' }, 'The soil here releases enough nitrogen for what’s planted.')));
  }

  // ------------------------------------------------- how we worked this out
  const series = n.series.filter((p) => inYear(p.date));
  const ser = series.length > 1 ? series : n.series;
  const x = ser.map((p) => p.date);
  const lanes = laneCrops(crops.length ? crops : n.crops);
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
    series: [{ name: 'Plant-available N', color: 'var(--s1)', area: true, values: ser.map((p) => p.ppm) }],
    refs: [{ y: 10, label: '10 ppm' }], title: 'Projected plant-available nitrogen',
  });
  const omChart = lineChart({
    x, unit: '%', height: 120, yFormat: (v) => f1(v),
    series: [{ name: 'Organic matter', color: 'var(--s3)', values: ser.map((p) => p.om_pct) }],
    title: 'Projected soil organic matter',
  });
  const notes = n.recommendations.filter((r) => r.kind !== 'deficit');
  const NOTE_TITLE = { budget: 'Where this bed’s nitrogen comes from', leaching: 'Lost over winter', organic_matter: 'Organic matter' };
  const nCard = h('div', { class: 'stack' },
    notes.length ? h('div', {}, notes.map((r) => h('div', { class: 'alert' }, statusIcon(r.severity),
      h('div', { class: 'title' }, NOTE_TITLE[r.kind] || 'Note'),
      h('div', { class: 'text' }, r.text),
      r.options?.length ? h('ul', { class: 'text' }, r.options.map((o) => h('li', {}, o))) : null))) : null,
    h('p', { class: 'tiny' }, `A day-by-day model over ${n.years.length} years (two passes through your ${cyc}-year cycle): organic matter releases nitrogen as the soil warms, crops take it up as they grow, legumes and leftover roots give some back, and rain on a bare bed washes it away. 1 ppm ≈ ${f2(4 * ozPer)} oz N in this bed.`),
    h('h3', {}, 'Nitrogen plants can use (ppm)'), nChart,
    h('p', { class: 'tiny' }, 'The line dips while a crop grows because the crop is using it, so dipping below 10 ppm is not a problem by itself. The Short column below shows whether a crop got enough: near zero means it was fed.'),
    h('div', { class: 'legend' }, Object.values(FEEDER).map((f) => h('span', { class: 'item' }, h('span', { class: 'key', style: { background: f.color } }), f.label))),
    strip,
    h('h3', {}, 'Soil organic matter (%)'), omChart);

  const years = n.years.filter((y) => scope === 'all' || y.year === thisYear);
  const yt = h('div', { class: 'stack' }, h('h3', {}, 'Nitrogen budget (lb N per acre)'),
    h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Year', 'Cycle yr', 'Start', 'From soil OM', 'Residue', 'Amendments', 'Fixed', 'Crop uptake', 'Leached', 'Shortfall', 'End OM %']
        .map((c, i) => h('th', { class: i > 1 ? 'num' : '' }, c)))),
      h('tbody', {}, years.map((y) => h('tr', {},
        h('td', {}, y.year), h('td', {}, y.cycle_year),
        ...[y.start_mineral, y.mineralized, y.residue, y.amendments, y.fixed, y.uptake, y.leached, y.deficit].map((v) => h('td', { class: 'num' }, f0(v))),
        h('td', { class: 'num' }, f2(y.end_om_pct))))))),
    h('p', { class: 'tiny' }, `Multiply by ${f2(ozPer)} for ounces of N in this ${bed.area_sqft} sq ft bed.`));

  const ct = h('div', { class: 'stack' }, h('h3', {}, 'Crops'),
    h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Crop', 'Planted', 'Needs', 'Got', 'Short', 'Short (oz N, bed)'].map((c, i) => h('th', { class: i > 1 ? 'num' : '' }, c)))),
      h('tbody', {}, crops.map((c) => h('tr', {},
        h('td', {}, h('span', { class: 'key', style: { background: FEEDER[feederOf[c.plant_id]]?.color, marginRight: '.4rem' } }), c.name),
        h('td', {}, fmtDate(c.start, { month: 'short', year: 'numeric' })),
        h('td', { class: 'num' }, c.fixer ? 'fixes' : f0(c.demand_lb_acre)), h('td', { class: 'num' }, f0(c.taken_lb_acre)),
        h('td', { class: 'num' }, c.fixer ? '—' : f0(c.deficit_lb_acre)), h('td', { class: 'num' }, c.fixer ? '—' : f2(c.deficit_n_oz_bed))))))));

  // ---------------------------------------------------------- amendments
  const mine = amend.amendments.filter((a) => a.bed_id === bed.id && (scope === 'all' || a.cycle_year === settings.current_cycle_year));
  const plantName = Object.fromEntries(plants.plants.map((p) => [p.id, p.name]));
  const cropOf = Object.fromEntries(plantings.plantings.map((p) => [p.id, plantName[p.plant_id] || p.plant_id]));
  const am = h('div', { class: 'stack' }, h('h3', {}, 'Everything added to this bed'),
    h('p', { class: 'tiny' }, 'Planned feedings are worked out for you and change when your plan does; anything you add yourself counts first. Each one repeats when the rotation comes back round to that year.'));
  if (mine.length) {
    am.append(h('table', {}, h('tbody', {}, mine.map((a) => h('tr', {},
      h('td', {}, `${idxToLabel(a.doy)}${scope === 'all' ? `, ${settings.start_year + a.cycle_year - 1}` : ''}`),
      h('td', {}, `${amountText(a.amount_lb)} ${(products[a.product]?.name || a.product).split(' (')[0].toLowerCase()} `,
        npkTag(products[a.product]?.npk),
        a.auto ? h('div', { class: 'tiny' }, `planned for ${cropOf[a.planting_id] || 'a crop'}`) : null),
      h('td', {}, a.auto ? null : h('button', { class: 'small danger', onclick: async () => {
        await api(`/amendments/${a.id}`, { method: 'DELETE' }); invalidate(); rerender();
      } }, 'Remove')))))));
  }
  am.append(h('button', { onclick: () => amendDialog(bed, settings, products) }, '+ Add compost or fertilizer'));

  const more = h('details', { class: 'more', open: scope === 'all' },
    h('summary', {}, 'How we worked this out'), h('div', { class: 'stack' }, nCard, yt, ct, pkTable(nu), am));

  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Feeding & soil'),
      h('p', {}, scope === 'year' ? 'What to add to your beds this year, when, and how much.'
        : 'Feedings and soil for every year of your rotation.')),
    scopeToggle(cyc, rerender)),
    plan,
    h('h2', { class: 'section-title' }, 'Bed by bed'),
    picker,
    h('div', { class: 'grid grid-2' }, needs, soilCard),
    h('div', { class: 'card' }, more));
}

function feedStep(st, today) {
  const stage = { planting: 'at planting', side_dress: 'side-dress', soil_prep: 'soil prep' }[st.stage];
  return h('li', { class: `feed-step${st.date < today ? ' past' : ''}` },
    h('div', { class: 'when' }, fmtDate(st.date), h('small', {}, fmtDate(st.date, { weekday: 'short' }))),
    h('div', { class: 'stack', style: { gap: '.2rem' } },
      h('div', { class: 'what' }, st.crop ? `${st.crop}, ${st.bed}` : st.bed,
        stage ? h('span', { class: 'badge', style: { marginLeft: '.4rem' } }, stage) : null),
      h('div', { class: 'amount' }, st.measure ? [h('strong', {}, st.measure.replace(/^about /, 'About ')), ' of '] : null,
        `${st.product_name.toLowerCase()} `, npkTag(st.npk), h('span', { class: 'tiny' }, ` (${st.amount})`)),
      h('div', { class: 'how' }, st.how),
      h('details', {}, h('summary', {}, 'Why?'), h('div', {}, st.why))));
}

// Phosphorus, potassium and pH in plain words, with what to do about them
function nutrientBlock(nu) {
  const LEVEL_SEV = { very_low: 'warn', low: 'warn', optimum: 'good', high: 'info', very_high: 'info' };
  const from = { tested: 'from your soil test', assumed: 'typical for this soil mix', unknown: '' }[nu.source];
  const line = (key, name) => {
    const x = nu[key];
    const val = x.ppm == null ? 'Not tested yet' : `${x.label} (${f0(x.ppm)} ppm${from ? `, ${from}` : ''})`;
    const plan = x.planned.length
      ? `Planned for ${nu.year}: ${x.planned.map((p) => `${p.measure || p.amount} of ${p.product.replace('_', ' ')}`).join(', ')} before planting.`
      : x.level === 'high' || x.level === 'very_high' ? 'Nothing to add: the soil has plenty in reserve.'
        : x.need === 0 && x.removed > 0 ? 'Your compost and feedings already cover it.' : null;
    return h('div', { class: 'alert' }, statusIcon(x.ppm == null ? 'info' : LEVEL_SEV[x.level]),
      h('div', { class: 'title' }, `${name}: ${val}`), h('div', { class: 'text' }, x.role),
      plan ? h('div', { class: 'text' }, plan) : null);
  };
  const box = h('div', {}, line('p', 'Phosphorus'), line('k', 'Potassium'));
  if (nu.source !== 'tested') {
    box.append(h('div', { class: 'explain' },
      nu.source === 'assumed'
        ? 'These are typical levels for a compost-rich mix, not a measurement. '
        : 'Without a soil test the plan only puts back what your crops take out. ',
      'A soil test (about $15–30 through your county extension office) shows what this bed really has, so you don’t buy what it doesn’t need. ',
      h('a', { href: '#/setup' }, 'Enter results'), ' under Setup → edit bed.'));
  }
  if (nu.ph_advice) {
    box.append(h('div', { class: 'alert' }, statusIcon('warn'), h('div', { class: 'title' }, 'Adjust the pH'),
      h('div', { class: 'text' }, nu.ph_advice.text)));
  }
  if (nu.high_p_warning) {
    box.append(h('div', { class: 'alert' }, statusIcon('info'), h('div', { class: 'title' }, 'Plenty of phosphorus already'),
      h('div', { class: 'text' }, 'Your fertilizer adds phosphorus this bed doesn’t need, and the extra washes into streams. A nitrogen-only feed such as blood meal (12-0-0) is a better fit; change it in Setup → Preferences.')));
  }
  return box;
}

function pkTable(nu) {
  const oz = (lb) => `${f1(lb * nu.oz_per_lb_acre)} oz`;
  const row = (key, name) => {
    const x = nu[key];
    return h('tr', {}, h('td', {}, name),
      ...[x.removed, x.supplied, x.build, x.need].map((v) => h('td', { class: 'num' }, `${f0(v)}`, h('div', { class: 'tiny' }, oz(v)))));
  };
  return h('div', { class: 'stack' }, h('h3', {}, `Phosphorus & potassium in ${nu.year} (lb per acre)`),
    h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, ['', 'Crops take out', 'Compost & feedings add', 'Build-up', 'Soil prep adds']
        .map((c, i) => h('th', { class: i ? 'num' : '' }, c)))),
      h('tbody', {}, row('p', 'Phosphorus (P₂O₅)'), row('k', 'Potassium (K₂O)')))),
    h('p', { class: 'tiny' }, 'Phosphorus and potassium hardly wash out, so they’re worked out once a year instead of day by day: what the harvest carries off, plus a build-up when a soil test says low, minus what compost and feedings already bring. When a test says high, nothing is added. Ounces are for this bed.'));
}

function soilSummary(sp) {
  const om = sp.om_pct;
  const omText = om < 2 ? 'low in organic matter, so it holds little nitrogen or water (compost every year helps a lot)'
    : om < 5 ? 'with a fair amount of organic matter' : 'rich in organic matter, which slowly feeds your crops';
  const ph = sp.ph;
  const phText = ph < 5.5 ? `quite acidic (pH ${f1(ph)}), so garden lime would help most vegetables`
    : ph < 6 ? `a little acidic (pH ${f1(ph)}); most vegetables like it slightly higher`
      : ph <= 7 ? `at a good pH (${f1(ph)}) for most vegetables`
        : ph <= 7.5 ? `slightly alkaline (pH ${f1(ph)}), fine for most crops`
          : `alkaline (pH ${f1(ph)}), which locks up some nutrients; sulfur brings it down`;
  return `${sp.texture[0].toUpperCase()}${sp.texture.slice(1)} soil, ${omText}, and ${phText}.`;
}

function amountText(lb) { return lb < 1 ? `${f1(lb * 16)} oz` : `${f1(lb)} lb`; }

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
  const prod = select(Object.entries(products).map(([k, v]) => ({ value: k, label: v.npk && !v.name.includes(v.npk) ? `${v.name} (${v.npk})` : v.name })), 'compost');
  const amt = h('input', { type: 'number', min: 0.1, step: 0.1, value: 10 });
  const date = h('input', { type: 'text', value: '04-01', placeholder: 'MM-DD', size: 6 });
  const yr = select(Array.from({ length: settings.cycle_years }, (_, i) => ({ value: i + 1, label: `${settings.start_year + i} (rotation year ${i + 1})` })), settings.current_cycle_year);
  const hint = h('div', { class: 'tiny' });
  const upd = () => {
    const p = products[prod.value];
    const nLb = Number(amt.value || 0) * p.n_pct / 100;
    hint.textContent = `${f2(nLb * 16)} oz of N for ${bed.area_sqft} sq ft (${f0(nLb * 43560 / bed.area_sqft)} lb N/acre), ~${Math.round(p.available * 100)}% available this season.` +
      (prod.value === 'compost' ? ' 1 cu ft of compost weighs ~40–50 lb.' : '');
  };
  prod.onchange = upd; amt.oninput = upd; upd();
  modal(`Add compost or fertilizer — ${bed.name}`, h('div', { class: 'stack' },
    h('div', { class: 'form-grid' }, field('Product', prod), field('Amount (lb)', amt), field('Date (MM-DD)', date), field('Year', yr)), hint), [
    { label: 'Cancel' },
    { label: 'Add', class: 'primary', onClick: async () => {
      monthDayToIdx(date.value);
      await api('/amendments', { method: 'POST', body: { bed_id: bed.id, cycle_year: Number(yr.value), date: date.value, product: prod.value, amount_lb: Number(amt.value) } });
      invalidate(); toast('Amendment added'); rerender();
    } }]);
}
