import { api, cached, invalidate } from '../api.js';
import { lineChart, columnChart } from '../charts.js';
import { h, f0, f1, f2, modal, field, select, toast } from '../ui.js';
import { rerender } from '../app.js';
import { BED_DEFAULTS, bedKindSelect } from './food.js';

export async function renderSetup() {
  const settings = await api('/settings');
  let site = null, siteErr = null;
  if (settings.location) {
    try { site = await cached('/site'); } catch (e) { siteErr = e; }
  }
  const beds = await api('/beds');
  const plants = await cached('/plants');

  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Setup'),
      h('p', {}, 'Location, beds and preferences. Everything else is computed from free public data.'))),
    h('div', { class: 'grid grid-2' }, locationCard(settings, site, siteErr), prefsCard(settings)),
    bedsCard(beds, settings),
    site ? climateCard(site) : null,
    site ? siteSoilCard(site) : null,
    customCard(plants),
    sourcesCard(site));
}

// ---------------------------------------------------------------- location
function locationCard(settings, site, siteErr) {
  const q = h('input', { type: 'search', class: 'search', placeholder: 'ZIP code or town, e.g. 80202 or Boulder' });
  const results = h('div', { class: 'stack' });
  const go = async () => {
    results.replaceChildren(h('div', { class: 'tiny' }, 'Searching…'));
    try {
      const rs = await api(`/geocode?q=${encodeURIComponent(q.value)}`);
      results.replaceChildren(...(rs.length ? rs.map((r) => h('button', { type: 'button', onclick: () => saveLoc(r) },
        `${r.name} (${f2(r.lat)}, ${f2(r.lon)})`)) : [h('div', { class: 'tiny' }, 'No matches.')]));
    } catch (e) { results.replaceChildren(h('div', { class: 'error' }, e.message)); }
  };
  q.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  const lat = h('input', { type: 'number', step: 'any', placeholder: 'latitude' });
  const lon = h('input', { type: 'number', step: 'any', placeholder: 'longitude' });
  const zip = h('input', { type: 'text', placeholder: 'ZIP (for zone)', size: 6 });
  async function saveLoc(loc) {
    await api('/settings', { method: 'PUT', body: { location: loc } });
    invalidate(); toast('Location saved — fetching 30 years of climate data…'); rerender();
  }
  const cur = settings.location;
  return h('div', { class: 'card stack' }, h('h2', {}, 'Garden location'),
    cur ? h('div', {}, h('strong', {}, cur.name), h('div', { class: 'tiny' }, `${f2(cur.lat)}, ${f2(cur.lon)}${site?.zone ? ` · zone ${site.zone.zone}` : ''}`))
      : h('p', {}, 'Start here: enter your ZIP code. Frost dates, planting windows, weather and soil all key off this.'),
    siteErr ? h('div', { class: 'error' }, siteErr.message) : null,
    h('div', { class: 'row' }, q, h('button', { class: 'primary', onclick: go }, 'Search')), results,
    h('details', {}, h('summary', { class: 'tiny' }, 'Enter coordinates instead'),
      h('div', { class: 'row', style: { marginTop: '.5rem' } }, lat, lon, zip,
        h('button', { onclick: () => saveLoc({ name: `${f2(Number(lat.value))}, ${f2(Number(lon.value))}`, lat: Number(lat.value), lon: Number(lon.value), zip: zip.value || null }) }, 'Use'))));
}

// ------------------------------------------------------------- preferences
function prefsCard(s) {
  const risk = select([{ value: 0.1, label: 'Cautious — 10% chance of frost' }, { value: 0.3, label: 'Balanced — 30%' }, { value: 0.5, label: 'Aggressive — 50% (median dates)' }], s.frost_risk);
  const lsf = h('input', { type: 'text', placeholder: 'MM-DD', value: s.lsf_override || '', size: 6 });
  const fff = h('input', { type: 'text', placeholder: 'MM-DD', value: s.fff_override || '', size: 6 });
  const cyc = select(Array.from({ length: 8 }, (_, i) => ({ value: i + 1, label: `${i + 1} year${i ? 's' : ''}` })), s.cycle_years);
  const start = h('input', { type: 'number', value: s.start_year, min: 1990, max: 2200 });
  return h('div', { class: 'card stack' }, h('h2', {}, 'Preferences'),
    field('Frost risk for tender crops', risk, 'How much risk you accept when setting out tomatoes, peppers, squash… Cold-hardy crops are handled separately.'),
    h('div', { class: 'form-grid' },
      field('Your last spring frost', lsf, 'Optional local knowledge (MM-DD). Shifts the 30-year record to match.'),
      field('Your first fall frost', fff, 'Optional (MM-DD).')),
    h('div', { class: 'form-grid' }, field('Rotation cycle length', cyc, 'Years before the plan repeats (3–4 is typical).'), field('Cycle year 1 is', start)),
    h('div', {}, h('button', { class: 'primary', onclick: async () => {
      await api('/settings', { method: 'PUT', body: { frost_risk: Number(risk.value), lsf_override: lsf.value || null,
        fff_override: fff.value || null, cycle_years: Number(cyc.value), start_year: Number(start.value) } });
      invalidate(); toast('Saved'); rerender();
    } }, 'Save preferences')));
}

// -------------------------------------------------------------------- beds
function bedsCard(beds, settings) {
  const card = h('div', { class: 'card stack' }, h('div', { class: 'row between' }, h('h2', {}, 'Beds'),
    h('div', { class: 'row' },
      beds.beds.length ? h('button', { class: 'danger', onclick: () => delAllBeds(beds.beds.length) }, 'Remove all beds') : null,
      h('button', { class: 'primary', onclick: () => bedDialog(null, beds.presets) }, '+ Add bed'))));
  card.append(sizingForm(settings));
  if (!beds.beds.length) card.append(h('div', { class: 'empty' }, settings.auto_size === false
    ? 'No beds yet. Add each raised bed, row or plot you rotate crops through.'
    : 'No beds yet. Add the food you want on the My food page and I’ll add beds to fit, or add your own here.'));
  else {
    card.append(h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Bed', 'Size', 'Type', 'Soil', 'OM', 'pH', 'Water', ''].map((c) => h('th', {}, c)))),
      h('tbody', {}, beds.beds.map((b) => h('tr', {},
        h('td', {}, h('strong', {}, b.name), b.mulched ? h('div', { class: 'tiny' }, 'mulched') : null,
          b.auto ? h('div', { class: 'tiny', title: 'Added to fit your food. It goes away if it empties out; edit it to keep it.' }, 'added for your food') : null),
        h('td', {}, `${b.length_ft}×${b.width_ft} ft (${b.area_sqft} sq ft)`),
        h('td', {}, { raised: 'Raised bed', in_ground: 'In-ground', container: 'Container' }[b.kind]),
        h('td', {}, b.soil_profile.texture, h('div', { class: 'tiny' }, b.soil_profile.source)),
        h('td', {}, `${f1(b.soil_profile.om_pct)}%`), h('td', {}, f1(b.soil_profile.ph)),
        h('td', {}, `${f2(b.soil_profile.awc)} in/in`),
        h('td', {}, h('div', { class: 'row' }, h('button', { class: 'small', onclick: () => bedDialog(b, beds.presets) }, 'Edit'),
          h('button', { class: 'small danger', onclick: () => delBed(b) }, 'Delete')))))))));
  }
  return card;
}

function sizingForm(s) {
  const t = s.auto_bed || { kind: 'raised', length_ft: 8, width_ft: 4 };
  const on = h('input', { type: 'checkbox', checked: s.auto_size !== false });
  const kind = bedKindSelect(t.kind);
  const len = h('input', { type: 'number', min: 0.5, step: 0.5, value: t.length_ft, style: { width: '5rem' } });
  const wid = h('input', { type: 'number', min: 0.5, step: 0.5, value: t.width_ft, style: { width: '5rem' } });
  kind.addEventListener('change', () => { [len.value, wid.value] = BED_DEFAULTS[kind.value]; });
  const save = h('button', { class: 'small', onclick: async () => {
    await api('/settings', { method: 'PUT', body: { auto_size: on.checked,
      auto_bed: { kind: kind.value, length_ft: Number(len.value) || t.length_ft, width_ft: Number(wid.value) || t.width_ft } } });
    invalidate(); toast('Saved'); rerender();
  } }, 'Save');
  return h('div', { class: 'stack' },
    h('label', { class: 'check' }, on, 'Size my garden for my food: add beds when a food doesn’t fit'),
    h('div', { class: 'row' }, 'New beds are', kind, 'of', len, '×', wid, 'feet', save),
    h('p', { class: 'tiny' }, 'Beds added this way are removed again if they empty out. Edit one to keep it. Turning this off keeps every bed you have.'));
}

function delBed(b) {
  modal(`Delete ${b.name}?`, h('p', {}, 'This also removes its plantings, amendments and watering log.'), [
    { label: 'Cancel' },
    { label: 'Delete', class: 'danger', onClick: async () => {
      await api(`/beds/${b.id}`, { method: 'DELETE' }); invalidate(); rerender();
    } }]);
}

function delAllBeds(n) {
  modal(`Remove all ${n} bed${n === 1 ? '' : 's'}?`, h('p', {}, 'This also removes every planting, amendment and watering log. Your location, preferences and custom plants are kept.'), [
    { label: 'Cancel' },
    { label: 'Remove all', class: 'danger', onClick: async () => {
      await api('/beds', { method: 'DELETE' }); invalidate(); toast('All beds removed'); rerender();
    } }]);
}

function bedDialog(b, presets) {
  const soil = b?.soil || {};
  const name = h('input', { type: 'text', value: b?.name || '', placeholder: 'e.g. North bed 1' });
  const len = h('input', { type: 'number', min: 0.5, step: 0.5, value: b?.length_ft ?? 8 });
  const wid = h('input', { type: 'number', min: 0.5, step: 0.5, value: b?.width_ft ?? 4 });
  const kind = select([{ value: 'raised', label: 'Raised bed' }, { value: 'in_ground', label: 'In-ground plot' }, { value: 'container', label: 'Container' }], b?.kind || 'raised');
  const preset = select(Object.entries(presets).map(([k, v]) => ({ value: k, label: v })), soil.preset || (b ? 'native' : 'raised_mix'));
  kind.onchange = () => { if (!b) preset.value = { raised: 'raised_mix', in_ground: 'native', container: 'container_mix' }[kind.value]; };
  const num = (v, ph) => h('input', { type: 'number', step: 'any', value: v ?? '', placeholder: ph });
  const om = num(soil.om_pct, 'auto'), ph = num(soil.ph, 'auto');
  const sand = num(soil.sand, 'auto'), silt = num(soil.silt, 'auto'), clay = num(soil.clay, 'auto');
  const no3 = num(b?.initial_no3_ppm ?? 10, '10');
  const mulch = h('input', { type: 'checkbox', checked: !!b?.mulched });
  const body = h('div', { class: 'stack' },
    h('div', { class: 'form-grid' }, field('Name', name), field('Length (ft)', len), field('Width (ft)', wid), field('Type', kind)),
    field('Soil', preset, 'Native soil comes from the USDA soil survey for your location; raised-bed mix assumes topsoil + compost.'),
    h('details', { open: !!(soil.om_pct || soil.ph || soil.sand) }, h('summary', {}, 'Soil test results (optional)'),
      h('div', { class: 'form-grid', style: { marginTop: '.5rem' } },
        field('Organic matter %', om), field('pH', ph), field('Sand %', sand), field('Silt %', silt), field('Clay %', clay),
        field('Nitrate-N (ppm)', no3, 'Starting point for the nitrogen model')),
      h('p', { class: 'tiny' }, 'Your state extension service runs inexpensive soil tests (~$15–30).')),
    h('label', { class: 'check' }, mulch, 'Mulched (straw, leaves, wood chips) — reduces evaporation'));
  modal(b ? `Edit ${b.name}` : 'Add bed', body, [
    { label: 'Cancel' },
    { label: 'Save', class: 'primary', onClick: async () => {
      const s = { preset: preset.value };
      const put = (k, el) => { if (el.value !== '') s[k] = Number(el.value); };
      put('om_pct', om); put('ph', ph); put('sand', sand); put('silt', silt); put('clay', clay);
      const payload = { name: name.value || 'Bed', length_ft: Number(len.value), width_ft: Number(wid.value),
        kind: kind.value, soil: s, mulched: mulch.checked, initial_no3_ppm: Number(no3.value || 10) };
      await api(b ? `/beds/${b.id}` : '/beds', { method: b ? 'PUT' : 'POST', body: payload });
      invalidate(); toast('Bed saved'); rerender();
    } }]);
}

// ----------------------------------------------------------------- climate
function climateCard(site) {
  const c = site.climate;
  const months = c.monthly.map((m) => m.month);
  const temps = lineChart({
    x: c.monthly.map((m, i) => `2001-${String(i + 1).padStart(2, '0')}-15`), unit: '°F', height: 200,
    series: [{ name: 'Average high', color: 'var(--s2)', values: c.monthly.map((m) => m.high_f) },
      { name: 'Average low', color: 'var(--s1)', values: c.monthly.map((m) => m.low_f) }],
    refs: [{ y: 32, label: '32°F' }], title: 'Monthly normal temperatures',
    xFormat: (d) => months[Number(d.slice(5, 7)) - 1],
  });
  const water = columnChart({
    labels: months, unit: '"', height: 170, yFormat: (v) => f1(v),
    series: [{ name: 'Precipitation', color: 'var(--s1)', values: c.monthly.map((m) => m.precip_in) },
      { name: 'Evapotranspiration (ET₀)', color: 'var(--s2)', values: c.monthly.map((m) => m.et0_in) }],
    title: 'Monthly rain vs. evaporative demand',
  });
  const risks = ['0.1', '0.3', '0.5', '0.9'];
  const table = h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Chance of a later/earlier frost'),
    ...risks.map((r) => h('th', {}, `${Math.round(Number(r) * 100)}%`)))),
  h('tbody', {},
    h('tr', {}, h('td', {}, 'Last spring frost (32°F)'), ...risks.map((r) => h('td', {}, c.last_spring_frost[r] || 'none'))),
    h('tr', {}, h('td', {}, 'Last hard freeze (28°F)'), ...risks.map((r) => h('td', {}, c.last_hard_freeze[r] || 'none'))),
    h('tr', {}, h('td', {}, 'First fall frost (32°F)'), ...risks.map((r) => h('td', {}, c.first_fall_frost[r] || 'none'))),
    h('tr', {}, h('td', {}, 'First hard freeze (28°F)'), ...risks.map((r) => h('td', {}, c.first_hard_freeze[r] || 'none')))));
  return h('div', { class: 'card stack' }, h('h2', {}, `Your climate (${c.years})`),
    h('div', { class: 'stats' },
      h('div', { class: 'stat' }, h('div', { class: 'label' }, 'Annual precipitation'), h('div', { class: 'value' }, `${f1(c.annual_precip_in)}"`)),
      h('div', { class: 'stat' }, h('div', { class: 'label' }, 'Annual ET₀'), h('div', { class: 'value' }, `${f1(c.annual_et0_in)}"`)),
      h('div', { class: 'stat' }, h('div', { class: 'label' }, 'Avg. coldest night'), h('div', { class: 'value' }, `${f0(c.avg_annual_min_f)}°F`), h('div', { class: 'sub' }, `zone ${c.zone_estimate} by reanalysis`)),
      h('div', { class: 'stat' }, h('div', { class: 'label' }, 'Frost-free season'), h('div', { class: 'value' }, `${c.season_days} d`))),
    c.overrides && (c.overrides.last_spring_frost || c.overrides.first_fall_frost)
      ? h('p', { class: 'tiny' }, `Adjusted to your frost dates (spring shift ${c.overrides.spring_shift_days} d, fall ${c.overrides.fall_shift_days} d).`) : null,
    h('div', { class: 'grid grid-2' }, h('div', {}, h('h3', {}, 'Monthly normals (°F)'), temps), h('div', {}, h('h3', {}, 'Rain vs. evaporative demand (inches)'), water)),
    h('div', { class: 'table-wrap' }, table),
    h('p', { class: 'tiny' }, 'Computed from ERA5 reanalysis (≈10–25 km grid). Hollows and hilltops can differ by a week or more — enter your own frost dates under Preferences if you know them.'));
}

function siteSoilCard(site) {
  const sp = site.soil;
  return h('div', { class: 'card' }, h('h2', {}, 'Native soil at your location'),
    h('p', {}, `${sp.name || 'Soil'}: ${sp.texture}, ${f1(sp.om_pct)}% organic matter, pH ${f1(sp.ph)}, holds ${f2(sp.awc)}" of water per inch${sp.drainage ? `, ${sp.drainage.toLowerCase()}` : ''}.`),
    h('p', { class: 'tiny' }, `Source: ${sp.source}. Used for in-ground beds; raised beds default to a compost-rich mix.`));
}

function customCard(plants) {
  const custom = plants.plants.filter((p) => p.custom);
  return h('div', { class: 'card' }, h('h2', {}, 'Custom plants & varieties'),
    custom.length ? h('div', { class: 'chips' }, custom.map((p) => h('a', { class: 'chip', href: `#/plants/${p.id}` }, p.name)))
      : h('p', { class: 'muted' }, 'Open any plant and choose “Make a custom variety” to add your own seed varieties (days to maturity, spacing, hardiness).'));
}

function sourcesCard(site) {
  const sources = site?.sources || [];
  return h('div', { class: 'card stack' }, h('h2', {}, 'Data sources (all free, no accounts)'),
    h('ul', {}, sources.map((s) => h('li', {}, h('a', { href: s.url, target: '_blank', rel: 'noopener' }, s.name), ` — ${s.use}`))),
    h('div', { class: 'row' },
      h('button', { onclick: async () => { await api('/refresh?what=all', { method: 'POST' }); invalidate(); toast('All data will be re-downloaded'); rerender(); } }, 'Re-download all data')),
    h('p', { class: 'tiny' }, 'Responses are cached in the local database, so the app keeps working if a service is briefly unavailable.'));
}
