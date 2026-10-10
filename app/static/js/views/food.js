// Food-first home: "What do you want to eat?" -> the app works out whether and
// how to grow it, and puts it into the rotation.
import { api, invalidate } from '../api.js';
import { h, fmtDate, f0, f1, statusBadge, toast, modal, field, select, errorBox } from '../ui.js';
import { plantingDialog } from './planting-modal.js';
import { rerender } from '../app.js';

const VERDICT = {
  good: ['good', 'Grows well'],
  fixable: ['good', 'Grows with soil prep'],
  marginal: ['warn', 'Possible with help'],
  partial: ['warn', 'Room some years'],
  no_space: ['warn', 'No room yet'],
  needs_beds: ['info', 'Add a bed'],
  unsuitable: ['high', 'Not suitable'],
};

export async function renderFood() {
  const settings = await api('/settings');
  if (!settings.location) return onboardingLocation();
  const beds = await api('/beds');
  if (!beds.beds.length && settings.auto_size === null) return onboardingGarden();
  const [mine, bundles] = await Promise.all([api('/foods/mine'), api('/foods/bundles')]);

  const box = h('div', { class: 'stack' });
  const sizing = settings.auto_size !== false;
  const hero = searchCard(sizing, async (food, amount) => {
    const res = await api('/foods/mine', { method: 'POST', body: { food_id: food.id, amount_lb: amount } });
    invalidate();
    const extra = res.beds_added ? ` (added ${res.beds_added} bed${res.beds_added > 1 ? 's' : ''})` : '';
    toast(res.planting_ids.length ? `${res.assessment.food.name} added to your rotation${extra}` : res.assessment.headline);
    rerender();
  });

  const chips = h('div', { class: 'chips' }, bundles.map((b) => h('button', {
    class: 'chip', type: 'button', title: b.foods.length + ' foods',
    onclick: async (e) => {
      e.target.disabled = true;
      e.target.textContent = `Planning ${b.name}…`;
      try {
        const r = await api(`/foods/bundle/${b.id}`, { method: 'POST' });
        const added = r.foods.reduce((n, f) => n + (f.beds_added || 0), 0);
        invalidate(); toast(`${b.name}: planned ${r.foods.length} foods${added ? `, added ${added} beds` : ''}`); rerender();
      } catch (err) { toast(err.message); e.target.disabled = false; }
    },
  }, b.name)));

  box.append(hero, h('div', { class: 'row' }, h('span', { class: 'muted' }, 'Or start from a dish:'), chips));

  if (!mine.foods.length) {
    box.append(h('div', { class: 'empty' },
      'Tell me what you like to eat — pinto beans, salsa, french fries, strawberries… ',
      'I’ll check your climate and soil, pick varieties and dates, and fit it into your beds year after year.'));
  } else {
    const ok = mine.foods.filter((f) => f.planting_ids.length);
    const not = mine.foods.filter((f) => !f.planting_ids.length);
    const yieldTotal = ok.reduce((a, f) => a + (f.assessment.expected_yield || 0), 0);
    box.append(h('div', { class: 'stats' },
      stat('Foods planned', ok.length, `${not.length} need attention`),
      stat('Expected harvest', `${f0(yieldTotal)} lb/yr`, 'rough garden averages'),
      gardenStat(beds.beds, sizing),
      stat('Rotation', `${settings.cycle_years}-year cycle`, `this is year ${settings.current_cycle_year}`)));
    box.append(h('div', { class: 'row between' }, h('h2', { class: 'section-title' }, 'Your food'),
      h('button', { onclick: coverCrops }, 'Add winter cover crops')));
    for (const f of mine.foods) box.append(foodCard(f));
  }
  return box;
}

function gardenStat(beds, sizing) {
  const sqft = beds.reduce((a, b) => a + b.area_sqft, 0);
  const auto = beds.filter((b) => b.auto).length;
  const sub = !sizing ? 'your beds; sizing is off' : auto === beds.length ? 'sized for your food'
    : auto ? `${auto} added for your food` : 'your beds';
  return h('a', { class: 'stat', href: '#/setup' }, h('div', { class: 'label' }, 'Garden'),
    h('div', { class: 'value' }, `${beds.length} bed${beds.length === 1 ? '' : 's'} · ${f0(sqft)} sq ft`),
    h('div', { class: 'sub' }, sub));
}

function stat(label, value, sub) {
  return h('div', { class: 'stat' }, h('div', { class: 'label' }, label),
    h('div', { class: 'value' }, value), sub ? h('div', { class: 'sub' }, sub) : null);
}

// -------------------------------------------------------------- search
function searchCard(sizing, onGrow) {
  const input = h('input', { type: 'search', class: 'search big', autocomplete: 'off',
    placeholder: 'What do you want to eat? e.g. pinto beans, salsa, french fries',
    'aria-label': 'Food to grow' });
  const sugg = h('div', { class: 'suggest-list', role: 'listbox', hidden: true });
  const amount = h('input', { type: 'number', min: 0, step: 0.5, placeholder: 'lb / year (optional)', style: { width: '11rem' } });
  const go = h('button', { class: 'primary', type: 'button', disabled: true }, 'Grow it');
  const picked = h('div', { class: 'tiny' });
  let chosen = null, timer = null, results = [];

  function choose(f) {
    chosen = f;
    input.value = f.name;
    sugg.hidden = true;
    go.disabled = false;
    picked.textContent = f.note ? 'Not a garden crop — I’ll explain why.' :
      f.plant_name ? `Grown as: ${f.plant_name}${f.has_yield ? ' · enter how much you eat a year to size the planting' : ''}` : '';
    amount.disabled = !f.has_yield;
  }
  input.addEventListener('input', () => {
    chosen = null; go.disabled = true; picked.textContent = '';
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { sugg.hidden = true; return; }
    timer = setTimeout(async () => {
      results = await api(`/foods/search?q=${encodeURIComponent(q)}`);
      sugg.replaceChildren(...(results.length ? results.map((f) => h('button', {
        type: 'button', role: 'option', class: 'suggest-item', onclick: () => choose(f),
      }, h('strong', {}, f.name), f.plant_name && f.plant_name !== f.name ? h('span', { class: 'tiny' }, ` · ${f.plant_name}`) : null,
      f.note ? h('span', { class: 'tiny' }, ' · not a garden crop') : null))
        : [h('div', { class: 'suggest-item tiny' }, 'No match. Try another name, or add it as a custom plant on the Plants page.')]));
      sugg.hidden = false;
    }, 150);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      if (!chosen && results.length) choose(results[0]);
      else if (chosen) go.click();
    }
    if (e.key === 'Escape') sugg.hidden = true;
  });
  go.addEventListener('click', async () => {
    if (!chosen) return;
    go.disabled = true; go.textContent = 'Working it out…';
    try { await onGrow(chosen, amount.value ? Number(amount.value) : null); } catch (err) { toast(err.message); }
    go.disabled = false; go.textContent = 'Grow it';
  });
  return h('div', { class: 'card stack hero' },
    h('h1', {}, 'What do you want to eat?'),
    h('p', { class: 'muted' }, sizing
      ? 'Name a food, and how much you eat if you know. I’ll check it against your climate and soil, pick the variety and dates, and size the garden to fit it, every year of the rotation.'
      : 'Name a food. I’ll check it against your climate and soil, pick the variety and dates, and fit it into your beds every year.'),
    h('div', { class: 'search-wrap' }, input, sugg),
    h('div', { class: 'row' }, amount, go), picked);
}

// ---------------------------------------------------------------- card
function foodCard(item) {
  const a = item.assessment;
  const [sev, label] = VERDICT[a.verdict] || ['info', a.verdict];
  const card = h('div', { class: 'card stack food-card' });
  card.append(h('div', { class: 'row between' },
    h('div', {}, h('h2', {}, a.food.name), h('div', { class: 'muted' }, a.headline)),
    statusBadge(sev, label)));

  if (a.reasons && a.reasons.length) {
    card.append(h('ul', { class: 'reasons' }, a.reasons.map((r) => h('li', {}, r))));
  }
  if (a.workaround) card.append(h('p', {}, h('strong', {}, 'What would work: '), a.workaround));

  if (a.placements && a.placements.length) {
    const facts = h('div', { class: 'row', style: { gap: '1.2rem' } },
      a.expected_yield ? h('span', {}, h('strong', {}, `~${f1(a.expected_yield)} ${a.unit}`), ' a year') : null,
      h('span', {}, h('strong', {}, `${f0(a.area_per_year)} sq ft`), ' a year'),
      item.amount_lb ? h('span', { class: 'muted' }, `sized for ${item.amount_lb} ${a.unit}/yr`) : h('span', { class: 'muted' }, 'starter-size planting'),
      item.removed_plantings ? h('span', { class: 'muted' }, `${item.removed_plantings} planting(s) removed in Rotation`) : null);
    card.append(facts);
    const rows = a.placements.map((p) => h('tr', {},
      h('td', {}, `${p.calendar_year}`), h('td', {}, p.bed), h('td', { class: 'num' }, `${f1(p.area_sqft)} sq ft`),
      h('td', {}, `${p.verb || (p.method === 'transplant' ? 'Transplant' : 'Sow')} ${fmtDate(p.establish)}`),
      h('td', {}, `${fmtDate(p.maturity)} – ${fmtDate(p.harvest_end)}`),
      h('td', { class: 'tiny' }, p.successions > 1 ? `${p.successions} sowings` : '')));
    card.append(h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, ['Year', 'Bed', 'Area', 'Plant', 'Harvest', ''].map((c) => h('th', {}, c)))),
      h('tbody', {}, rows))));
  }

  if (a.steps && a.steps.length) {
    const det = h('details', { open: !!item.justAdded },
      h('summary', {}, h('strong', {}, `How to grow ${a.food.name.toLowerCase()} here`)),
      h('ol', { class: 'steps' }, a.steps.map((s) => h('li', {}, h('strong', {}, `${s.title}. `), s.text))));
    card.append(det);
  }

  const actions = h('div', { class: 'row' });
  if (a.plant && a.verdict !== 'needs_beds') {
    actions.append(h('a', { class: 'btn', href: `#/plants/${a.plant.id}` }, 'Plant details'));
  }
  if (a.food.plant_id && a.verdict !== 'unsuitable') {
    actions.append(h('button', { onclick: () => changeAmount(item) }, 'Change amount'));
    actions.append(h('button', { onclick: async () => {
      await api(`/foods/mine/${item.id}/replan`, { method: 'POST' }); invalidate(); toast('Re-planned'); rerender();
    } }, 'Re-plan'));
  }
  if (a.verdict === 'unsuitable' && a.plant) {
    actions.append(h('button', { onclick: () => plantingDialog({ plantId: a.plant.id, onSaved: rerender }) }, 'Plan it manually anyway'));
  }
  actions.append(h('button', { class: 'danger', onclick: () => removeFood(item) }, 'Remove'));
  card.append(actions);
  return card;
}

function changeAmount(item) {
  const a = item.assessment;
  const amt = h('input', { type: 'number', min: 0.5, step: 0.5, value: item.amount_lb || '' });
  modal(`How much ${a.food.name.toLowerCase()}?`, h('div', { class: 'stack' },
    field(`Pounds a year`, amt, 'I’ll size the planting from typical garden yields and spread it over your beds.')), [
    { label: 'Cancel' },
    { label: 'Re-plan', class: 'primary', onClick: async () => {
      await api(`/foods/mine/${item.id}/replan`, { method: 'POST', body: { food_id: item.food_id, amount_lb: Number(amt.value) || null } });
      invalidate(); toast('Re-planned'); rerender();
    } }]);
}

function removeFood(item) {
  const keep = h('input', { type: 'checkbox' });
  modal(`Remove ${item.assessment.food.name}?`, h('div', { class: 'stack' },
    h('p', {}, item.planting_ids.length ? 'This also removes its plantings from your rotation.' : 'It isn’t in your rotation.'),
    item.planting_ids.length ? h('label', { class: 'check' }, keep, 'Keep the plantings in my rotation') : null), [
    { label: 'Cancel' },
    { label: 'Remove', class: 'danger', onClick: async () => {
      await api(`/foods/mine/${item.id}?keep_plantings=${keep.checked}`, { method: 'DELETE' });
      invalidate(); rerender();
    } }]);
}

export async function coverCrops() {
  const r = await api('/rotation/cover-crops', { method: 'POST' });
  invalidate();
  if (!r.added.length) toast('No bare winter beds found where a cover crop fits.');
  else toast(`Added ${r.added.length} cover crop${r.added.length > 1 ? 's' : ''}: ${[...new Set(r.added.map((x) => x.plant))].join(', ')}`);
  rerender();
}

// ---------------------------------------------------------- onboarding
function onboardingLocation() {
  const q = h('input', { type: 'search', class: 'search big', placeholder: 'Your ZIP code (or town)' });
  const out = h('div', { class: 'stack' });
  const go = async () => {
    try {
      const rs = await api(`/geocode?q=${encodeURIComponent(q.value)}`);
      out.replaceChildren(...(rs.length ? rs.map((r) => h('button', { type: 'button', onclick: async () => {
        await api('/settings', { method: 'PUT', body: { location: r } });
        invalidate(); toast('Got it — loading 30 years of your weather…'); rerender();
      } }, r.name)) : [h('div', { class: 'tiny' }, 'No match — try a ZIP code.')]));
    } catch (e) { out.replaceChildren(errorBox(e)); }
  };
  q.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
  return h('div', { class: 'card stack hero' }, h('h1', {}, 'Grow the food you love to eat'),
    h('p', {}, 'Step 1 of 2: where is your garden? Your climate, frost dates and soil all come from free public data for this spot.'),
    h('div', { class: 'row' }, q, h('button', { class: 'primary', onclick: go }, 'Find')), out);
}

export const BED_DEFAULTS = { raised: [8, 4], in_ground: [10, 4], container: [2, 2] };

export function bedKindSelect(value) {
  return select([{ value: 'raised', label: 'raised beds' }, { value: 'in_ground', label: 'in-ground plots' }, { value: 'container', label: 'large containers' }], value);
}

function onboardingGarden() {
  // Path 1: the app works out how many beds the food needs.
  const kind = bedKindSelect('raised');
  const len = h('input', { type: 'number', min: 1, step: 0.5, value: 8, style: { width: '5rem' } });
  const wid = h('input', { type: 'number', min: 1, step: 0.5, value: 4, style: { width: '5rem' } });
  kind.addEventListener('change', () => { [len.value, wid.value] = BED_DEFAULTS[kind.value]; });
  const sizeIt = h('button', { class: 'primary' }, 'Size it for me');
  sizeIt.onclick = async () => {
    sizeIt.disabled = true;
    await api('/settings', { method: 'PUT', body: { auto_size: true,
      auto_bed: { kind: kind.value, length_ft: Number(len.value) || 8, width_ft: Number(wid.value) || 4 } } });
    invalidate(); rerender();
  };

  // Path 2: the user already has beds.
  const count = h('input', { type: 'number', min: 1, max: 30, value: 3, style: { width: '5rem' } });
  const mlen = h('input', { type: 'number', min: 1, step: 0.5, value: 8, style: { width: '5rem' } });
  const mwid = h('input', { type: 'number', min: 1, step: 0.5, value: 4, style: { width: '5rem' } });
  const mkind = bedKindSelect('raised');
  mkind.addEventListener('change', () => { [mlen.value, mwid.value] = BED_DEFAULTS[mkind.value]; });
  const more = h('input', { type: 'checkbox', checked: true });
  const go = h('button', {}, 'Create my beds');
  go.onclick = async () => {
    go.disabled = true;
    const n = Number(count.value) || 1;
    const size = { kind: mkind.value, length_ft: Number(mlen.value), width_ft: Number(mwid.value) };
    for (let i = 1; i <= n; i++) await api('/beds', { method: 'POST', body: { name: `Bed ${i}`, ...size } });
    await api('/settings', { method: 'PUT', body: { auto_size: more.checked, auto_bed: size } });
    invalidate(); toast(`${n} beds created`); rerender();
  };

  return h('div', { class: 'card stack hero' }, h('h1', {}, 'Your garden'),
    h('p', {}, 'Step 2 of 2: do you already have beds, or should I work out what your food needs?'),
    h('div', { class: 'grid grid-2' },
      h('div', { class: 'stack' }, h('h2', {}, 'Size it for me'),
        h('p', { class: 'muted' }, 'Tell me what you want to eat, and I’ll work out how many beds that takes, including room to rotate crops.'),
        h('div', { class: 'row' }, 'Use', kind, 'of', len, '×', wid, 'feet'), h('div', {}, sizeIt)),
      h('div', { class: 'stack' }, h('h2', {}, 'I already have beds'),
        h('p', { class: 'muted' }, 'I’ll fit your food into them. You can rename them, resize them or add soil tests later in Setup.'),
        h('div', { class: 'row' }, 'I have', count, mkind, 'of', mlen, '×', mwid, 'feet'),
        h('label', { class: 'check' }, more, 'Add more like these if my food doesn’t fit'),
        h('div', {}, go))));
}
