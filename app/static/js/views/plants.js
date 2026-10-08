import { api, cached, invalidate } from '../api.js';
import { yearStrip } from '../charts.js';
import { h, MONTHS, doyOf, idxToLabel, CATEGORY_LABEL, FROST_LABEL, FEEDER, modal, field, select, toast } from '../ui.js';
import { plantingDialog } from './planting-modal.js';

const state = { q: '', cat: 'all', season: 'all', now: false };

export async function renderPlants() {
  const data = await cached('/plants');
  const todayIdx = doyOf(new Date());
  const listBox = h('div', { class: 'list' });
  const count = h('span', { class: 'muted' });

  const search = h('input', { class: 'search', type: 'search', placeholder: 'Search 140+ plants (name, family, Latin)…', value: state.q });
  search.oninput = () => { state.q = search.value; draw(); };
  const chipRow = (key, opts) => h('div', { class: 'chips' }, opts.map(([v, label]) => {
    const c = h('button', { class: `chip${state[key] === v ? ' on' : ''}`, type: 'button' }, label);
    c.onclick = () => { state[key] = v; c.parentElement.querySelectorAll('.chip').forEach((x) => x.classList.remove('on')); c.classList.add('on'); draw(); };
    return c;
  }));
  const nowBox = h('input', { type: 'checkbox', checked: state.now });
  nowBox.onchange = () => { state.now = nowBox.checked; draw(); };

  function plantable(p) {
    return p.windows.some((w) => [todayIdx, todayIdx + 365].some((t) => w.start <= t + 7 && t <= w.end));
  }
  function draw() {
    const q = state.q.trim().toLowerCase();
    const rows = data.plants.filter((p) =>
      (state.cat === 'all' || p.category === state.cat) &&
      (state.season === 'all' || p.season === state.season) &&
      (!state.now || plantable(p)) &&
      (!q || `${p.name} ${p.latin} ${p.family} ${data.families[p.family] || ''}`.toLowerCase().includes(q)));
    count.textContent = `${rows.length} plants`;
    listBox.replaceChildren(
      h('div', { class: 'list-row', style: { cursor: 'default', borderTop: 0 } },
        h('div', { class: 'tiny' }, 'Plant'),
        h('div', {}, h('div', { class: 'months' }, MONTHS.map((m) => h('span', {}, m[0])))),
        h('div', { class: 'tiny' }, 'Planting window')),
      ...rows.map((p) => h('a', { class: 'list-row', href: `#/plants/${p.id}` },
        h('div', {}, h('div', { class: 'name' }, p.name, p.custom ? h('span', { class: 'badge', style: { marginLeft: '.4rem' } }, 'custom') : null),
          h('div', { class: 'latin' }, p.latin),
          h('div', { class: 'row', style: { gap: '.3rem', marginTop: '.2rem' } },
            h('span', { class: 'badge' }, h('span', { class: 'key', style: { background: FEEDER[p.feeder].color } }), FEEDER[p.feeder].label),
            h('span', { class: 'badge' }, p.season === 'warm' ? 'Warm season' : 'Cool season'))),
        data.located ? yearStrip(p.windows, todayIdx) : h('div', { class: 'tiny' }, 'Set location to see windows'),
        h('div', { class: 'tiny', style: { maxWidth: '220px' } },
          p.windows.length ? p.windows.map((w) => `${w.season}: ${w.label}`).join(' · ')
            : (data.located ? `No window — ${p.reasons[0] || 'not suited'}` : '')))));
    if (!rows.length) listBox.append(h('div', { class: 'empty' }, 'No plants match. Try another search, or add a custom plant from any plant’s page.'));
  }
  draw();

  return h('div', { class: 'stack' },
    h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Plant library'),
      h('p', {}, 'Green bars show when each crop can go in the ground (sowing or transplanting) at your location, from 30 years of local weather.'))),
    h('div', { class: 'card stack' },
      h('div', { class: 'row' }, search, count),
      chipRow('cat', [['all', 'All'], ...Object.entries(CATEGORY_LABEL)]),
      h('div', { class: 'row' }, chipRow('season', [['all', 'Any season'], ['cool', 'Cool season'], ['warm', 'Warm season']]),
        h('label', { class: 'check' }, nowBox, 'Plantable this week'))),
    h('div', { class: 'card' }, listBox));
}

export async function renderPlant(pid) {
  const d = await api(`/plants/${pid}`);
  const p = d.plant;
  const fact = (k, v) => h('div', { class: 'fact' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v));
  const kcText = `${p.kc[0]} → ${p.kc[1]} → ${p.kc[2]}`;
  const facts = h('div', { class: 'facts' },
    fact('Family', `${d.family_common} (${p.family})`),
    fact('Season', `${p.season === 'warm' ? 'Warm' : 'Cool'}-season ${p.lifecycle}`),
    fact('Frost tolerance', FROST_LABEL[p.frost]),
    fact('Days to harvest', p.special ? (p.special.first_harvest_year > 1 ? `Year ${p.special.first_harvest_year}` : 'See windows') : `${p.dtm[0]}–${p.dtm[1]} from ${p.dtm_from === 'sow' ? 'sowing' : 'transplant'}`),
    fact('Germination', `${p.germ_min}°F${p.germ_max ? `–${p.germ_max}°F` : '+'} soil · ${p.germ_days[0]}–${p.germ_days[1]} days`),
    p.indoor_weeks ? fact('Start indoors', `${p.indoor_weeks[0]}–${p.indoor_weeks[1]} weeks before transplant`) : null,
    fact('Spacing', `${p.spacing}" in row, ${p.row}" rows · ~${d.per_sqft} per sq ft`),
    fact('Sowing depth', p.depth ? `${p.depth}"` : 'surface (needs light)'),
    fact('Sun', p.sun === 'full' ? 'Full sun (6–8 h+)' : 'Part shade OK'),
    fact('Water (FAO-56 Kc)', `${kcText} · roots ~${p.root_in}"`),
    fact('Nitrogen', p.feeder === 'fixer' ? `Fixes N — leaves ~${p.n_fix} lb/acre` : `${FEEDER[p.feeder].label} — ~${p.n_demand} lb N/acre`),
    fact('Soil pH', `${p.ph[0]}–${p.ph[1]}`),
    p.heat_max ? fact('Heat limit', `Quality drops when highs average > ${p.heat_max}°F`) : null,
    p.heat_stress ? fact('Heat stress', `Alerts at ${p.heat_stress}°F+`) : null,
    d.family_return_years ? fact('Rotation', `Keep ${d.family_return_years}+ years between ${d.family_common.toLowerCase()} in a bed`) : null,
  );

  const windows = h('div', { class: 'stack' });
  if (!d.located) windows.append(h('p', { class: 'muted' }, 'Set your location on the Setup page to see dates.'));
  for (const [method, w] of Object.entries(d.methods)) {
    const box = h('div', { class: 'stack' }, h('h3', {}, method === 'direct' ? (p.special ? 'Planting' : 'Direct sowing') : 'Starting indoors & transplanting'));
    if (!w.windows.length) {
      box.append(h('div', { class: 'error' }, `No reliable window at your location: ${w.reasons.join('; ')}. A greenhouse, low tunnel or a faster variety may make it possible.`));
    }
    box.append(yearStrip(w.windows.map((x) => ({ start: x.start, end: x.end, label: x.season })), doyOf(new Date())),
      h('div', { class: 'months' }, MONTHS.map((m) => h('span', {}, m))));
    for (const win of w.windows) {
      const steps = [];
      if (win.labels.indoor_start) steps.push(`Start seeds indoors ${win.labels.indoor_start}`);
      if (win.labels.harden_off) steps.push(`Harden off from ${win.labels.harden_off}`);
      steps.push(`${method === 'transplant' ? 'Transplant' : (p.special ? 'Plant' : 'Sow')} around ${win.labels.establish} (window ${win.start_label} – ${win.end_label})`);
      if (win.successions && win.successions.length > 1) steps.push(`Succession sowings: ${win.successions.map(idxToLabel).join(', ')}`);
      steps.push(p.category === 'cover' ? `Terminate around ${win.labels.maturity}` :
        `Harvest from ${win.labels.maturity} to ${idxToLabel(win.harvest_end)}${win.first_harvest_year > 1 ? ` (from year ${win.first_harvest_year})` : ''}`);
      box.append(h('div', { class: 'window' },
        h('div', { class: 'row between' }, h('strong', {}, `${win.season} planting`),
          win.frost_risk !== null && win.frost_risk !== undefined ? h('span', { class: 'tiny' }, `frost risk ${Math.round(win.frost_risk * 100)}% · ${win.days_to_harvest} days to harvest here`) : null),
        h('ol', {}, steps.map((st) => h('li', {}, st))),
        win.notes.length ? h('div', { class: 'tiny' }, win.notes.join(' ')) : null));
    }
    if (!p.special) box.append(h('div', { class: 'tiny' }, 'Harvest dates use growing degree days from your local temperatures, so they run longer than the seed packet in cool spells and a little shorter in hot summers.'));
    windows.append(box);
  }

  const comp = h('div', { class: 'stack' },
    d.companions.length ? h('div', {}, h('strong', {}, 'Good companions: '), ...joinLinks(d.companions)) : null,
    d.avoid.length ? h('div', {}, h('strong', {}, 'Keep apart from: '), ...joinLinks(d.avoid)) : null);

  return h('div', { class: 'stack' },
    h('a', { href: '#/plants' }, '← All plants'),
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', {}, p.name), h('p', {}, h('i', {}, p.latin))),
      h('div', { class: 'row' },
        h('button', { onclick: () => customDialog(p) }, 'Make a custom variety'),
        p.custom ? h('button', { class: 'danger', onclick: async () => {
          await api(`/plants/custom/${p.id}`, { method: 'DELETE' }); invalidate(); location.hash = '#/plants';
        } }, 'Delete custom plant') : null,
        h('button', { class: 'primary', onclick: () => plantingDialog({ plantId: p.id, onSaved: () => { location.hash = '#/rotation'; } }) }, 'Add to my rotation'))),
    p.tips ? h('div', { class: 'card' }, h('p', { style: { margin: 0 } }, p.tips)) : null,
    h('div', { class: 'grid grid-2' },
      h('div', { class: 'card stack' }, h('h2', {}, 'When to plant at your location'), windows),
      h('div', { class: 'card stack' }, h('h2', {}, 'Growing facts'), facts, comp)));
}

function joinLinks(items) {
  const out = [];
  items.forEach((c, i) => { if (i) out.push(', '); out.push(h('a', { href: `#/plants/${c.id}` }, c.name)); });
  return out;
}

function customDialog(p) {
  const name = h('input', { type: 'text', value: `${p.name} — my variety` });
  const dtm0 = h('input', { type: 'number', value: p.dtm[0] });
  const dtm1 = h('input', { type: 'number', value: p.dtm[1] });
  const spacing = h('input', { type: 'number', value: p.spacing });
  const frost = select(Object.entries(FROST_LABEL).map(([v, l]) => ({ value: v, label: l })), p.frost);
  const heat = h('input', { type: 'number', value: p.heat_max || '', placeholder: 'none' });
  const ndem = h('input', { type: 'number', value: p.n_demand });
  const tips = h('input', { type: 'text', value: '' , placeholder: 'notes for this variety' });
  modal('Custom variety', h('div', { class: 'stack' },
    h('p', { class: 'tiny' }, `Starts as a copy of ${p.name} — change what your seed packet says differs.`),
    field('Name', name),
    h('div', { class: 'form-grid' }, field('Days to maturity (min)', dtm0), field('Days to maturity (max)', dtm1),
      field('Spacing (in)', spacing), field('Frost tolerance', frost), field('Heat limit (°F avg high)', heat),
      field('N demand (lb/acre)', ndem)), field('Notes', tips)), [
    { label: 'Cancel' },
    { label: 'Create', class: 'primary', onClick: async () => {
      const overrides = { dtm: [Number(dtm0.value), Number(dtm1.value)], spacing: Number(spacing.value),
        frost: frost.value, n_demand: Number(ndem.value) };
      if (heat.value) overrides.heat_max = Number(heat.value);
      if (tips.value) overrides.tips = tips.value;
      const r = await api('/plants/custom', { method: 'POST', body: { name: name.value, base_id: p.custom ? p.base_id || null : p.id, profile: p.profile, overrides } });
      invalidate(); toast('Custom plant created'); location.hash = `#/plants/${r.id}`;
    } }]);
}

