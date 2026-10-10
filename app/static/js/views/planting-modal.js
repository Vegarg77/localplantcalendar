// "Add to rotation" / edit-planting dialog shared by the Plants and Rotation pages.
import { api, invalidate } from '../api.js';
import { h, modal, field, select, toast, idxToLabel, idxToMonthDay, monthDayToIdx } from '../ui.js';

export async function plantingDialog({ plantId, bedId, cycleYear, planting, onSaved } = {}) {
  const [beds, settings, plantsResp] = await Promise.all([
    api('/beds'), api('/settings'), api('/plants')]);
  if (!beds.beds.length) {
    modal('Add a bed first', h('p', {}, 'Your rotation is organised by bed. Create at least one bed on the Setup page.'),
      [{ label: 'Go to Setup', class: 'primary', onClick: () => { location.hash = '#/setup'; } }]);
    return;
  }
  const editing = !!planting;
  const state = {
    plant_id: planting?.plant_id || plantId || plantsResp.plants[0].id,
    bed_id: planting?.bed_id || bedId || beds.beds[0].id,
    cycle_year: planting?.cycle_year || cycleYear || settings.current_cycle_year,
    method: planting?.method || null,
    doy: planting?.doy ?? null,
    area_sqft: planting?.area_sqft || 0,
    successions: planting?.successions || 1,
    dtm_override: planting?.dtm_override || null,
    residue: planting?.residue || null,
    notes: planting?.notes || '',
  };

  const plantSel = select(plantsResp.plants.map((p) => ({ value: p.id, label: p.name })), state.plant_id);
  const bedSel = select(beds.beds.map((b) => ({ value: b.id, label: `${b.name} (${b.area_sqft} sq ft)` })), state.bed_id);
  const years = Array.from({ length: settings.cycle_years }, (_, i) => ({
    value: i + 1, label: `Year ${i + 1} (${settings.start_year + i}, ${settings.start_year + i + settings.cycle_years}…)` }));
  const yearSel = select(years, state.cycle_year);
  const methodBox = h('div', {});
  const windowBox = h('div', { class: 'stack' });
  const areaIn = h('input', { type: 'number', min: 0, step: 1, value: state.area_sqft || '', placeholder: 'whole bed' });
  const succIn = h('input', { type: 'number', min: 1, max: 12, value: state.successions });
  const dtmIn = h('input', { type: 'number', min: 10, max: 400, value: state.dtm_override || '', placeholder: 'packet value (optional)' });
  const residueSel = select([{ value: '', label: 'Default' }, { value: 'remove', label: 'Remove / compost elsewhere' },
    { value: 'incorporate', label: 'Chop & drop / turn in' }], state.residue || '');
  const notesIn = h('input', { type: 'text', value: state.notes, placeholder: 'variety, notes…' });
  const dateIn = h('input', { type: 'text', placeholder: 'MM-DD', size: 6,
    value: state.doy !== null ? idxToMonthDay(state.doy) : '' });

  let detail = null;
  async function loadPlant() {
    detail = await api(`/plants/${state.plant_id}${state.dtm_override ? `?dtm=${state.dtm_override}` : ''}`);
    const methods = Object.keys(detail.methods);
    if (!state.method || !methods.includes(state.method)) state.method = methods[0];
    methodBox.replaceChildren();
    if (methods.length > 1) {
      const sel = select(methods.map((m) => ({ value: m, label: m === 'direct' ? 'Direct sow' : 'Transplant (start indoors)' })), state.method);
      sel.onchange = () => { state.method = sel.value; state.doy = null; drawWindows(); };
      methodBox.append(field('Method', sel));
    }
    succIn.disabled = !detail.plant.succession;
    drawWindows();
  }
  function drawWindows() {
    windowBox.replaceChildren();
    if (!detail.located) {
      windowBox.append(h('p', { class: 'muted' }, 'Set your location to see planting windows.'));
      return;
    }
    const w = detail.methods[state.method];
    if (!w.windows.length) {
      windowBox.append(h('p', { class: 'error' }, `No reliable window at your location: ${w.reasons.join('; ')}. You can still enter a date (season extension, greenhouse…).`));
    }
    if (state.doy === null && w.windows.length) state.doy = w.windows[0].establish;
    for (const win of w.windows) {
      const r = h('input', { type: 'radio', name: 'win', value: win.establish });
      if (state.doy === win.establish) r.checked = true;
      r.onchange = () => { state.doy = win.establish; dateIn.value = idxToMonthDay(win.establish); };
      windowBox.append(h('label', { class: 'check window' }, r,
        h('div', {}, h('strong', {}, `${win.season}: ${win.labels.establish}`),
          h('div', { class: 'tiny' }, `Window ${win.start_label} – ${win.end_label} · harvest ${win.labels.maturity} – ${idxToLabel(win.harvest_end)}`
            + (win.labels.indoor_start ? ` · start indoors ${win.labels.indoor_start}` : '')))));
    }
    if (state.doy !== null) dateIn.value = idxToMonthDay(state.doy);
    windowBox.append(field('Or a specific date', dateIn, 'Any date works — the plan will warn if it is outside the window.'));
  }
  plantSel.onchange = () => { state.plant_id = plantSel.value; state.method = null; state.doy = null; loadPlant(); };
  dtmIn.onchange = () => { state.dtm_override = dtmIn.value ? Number(dtmIn.value) : null; loadPlant(); };
  await loadPlant();

  const body = h('div', { class: 'stack' },
    h('div', { class: 'form-grid' }, field('Plant', plantSel), field('Bed', bedSel), field('Rotation year', yearSel)),
    methodBox, windowBox,
    h('div', { class: 'form-grid' },
      field('Area (sq ft)', areaIn, 'Blank = whole bed'),
      field('Successions', succIn, detail.plant.succession ? `Sow again every ${detail.plant.succession} days` : 'Single sowing'),
      field('Days to maturity', dtmIn, 'From your seed packet'),
      field('Residue', residueSel, 'Turned-in residue returns N'),
      field('Notes', notesIn)));

  const actions = [];
  if (editing) {
    actions.push({ label: 'Delete', class: 'danger', onClick: async () => {
      await api(`/plantings/${planting.id}`, { method: 'DELETE' });
      invalidate(); toast('Removed'); onSaved && onSaved();
    } });
  }
  actions.push({ label: 'Cancel' });
  actions.push({ label: editing ? 'Save' : 'Add to rotation', class: 'primary', onClick: async () => {
    let doy = state.doy;
    if (dateIn.value && /^\d{1,2}-\d{1,2}$/.test(dateIn.value.trim())) {
      const [m, d] = dateIn.value.trim().split('-').map(Number);
      doy = monthDayToIdx(`${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`);
    }
    const payload = {
      plant_id: plantSel.value, bed_id: Number(bedSel.value), cycle_year: Number(yearSel.value),
      method: state.method, doy, area_sqft: Number(areaIn.value) || 0,
      successions: Number(succIn.value) || 1, dtm_override: dtmIn.value ? Number(dtmIn.value) : null,
      residue: residueSel.value || null, notes: notesIn.value,
    };
    if (editing) await api(`/plantings/${planting.id}`, { method: 'PUT', body: payload });
    else await api('/plantings', { method: 'POST', body: payload });
    invalidate();
    toast(editing ? 'Saved' : 'Added to your rotation');
    onSaved && onSaved();
  } });
  modal(editing ? 'Edit planting' : 'Add to rotation', body, actions);
}
