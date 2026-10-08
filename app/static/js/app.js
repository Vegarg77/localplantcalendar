import { h, errorBox, loading } from './ui.js';
import { renderToday } from './views/today.js';
import { renderFood } from './views/food.js';
import { renderPlants, renderPlant } from './views/plants.js';
import { renderRotation } from './views/rotation.js';
import { renderCalendar } from './views/calendar.js';
import { renderSoil } from './views/soil.js';
import { renderSetup } from './views/setup.js';

const routes = [
  [/^#?\/?$/, 'food', renderFood],
  [/^#\/today$/, 'today', renderToday],
  [/^#\/plants\/([\w-]+)$/, 'plants', renderPlant],
  [/^#\/plants$/, 'plants', renderPlants],
  [/^#\/rotation$/, 'rotation', renderRotation],
  [/^#\/calendar(?:\/(\d{4}))?$/, 'calendar', renderCalendar],
  [/^#\/soil(?:\/(\d+))?$/, 'soil', renderSoil],
  [/^#\/setup$/, 'setup', renderSetup],
];

let seq = 0;
export async function route() {
  const hash = location.hash || '#/';
  const view = document.getElementById('view');
  const my = ++seq;
  for (const [re, tab, fn] of routes) {
    const m = hash.match(re);
    if (!m) continue;
    document.querySelectorAll('.tabs a').forEach((a) => a.classList.toggle('active', a.dataset.tab === tab));
    view.replaceChildren(loading());
    try {
      const node = await fn(...m.slice(1));
      if (my === seq) view.replaceChildren(node);
    } catch (err) {
      console.error(err);
      if (my === seq) view.replaceChildren(errorBox(err));
    }
    return;
  }
  view.replaceChildren(h('div', { class: 'empty' }, 'Page not found. ', h('a', { href: '#/' }, 'Go home')));
}

export function rerender() { route(); }

window.addEventListener('hashchange', () => { route(); window.scrollTo(0, 0); });

// theme toggle: OS default, persisted override
const root = document.documentElement;
try {
  const saved = localStorage.getItem('theme');
  if (saved) root.dataset.theme = saved;
} catch { /* storage unavailable */ }
document.getElementById('theme-toggle').addEventListener('click', () => {
  const dark = root.dataset.theme
    ? root.dataset.theme === 'dark'
    : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('theme', root.dataset.theme); } catch { /* ignore */ }
});

route();
