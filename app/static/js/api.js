export async function api(path, { method = 'GET', body } = {}) {
  const r = await fetch(`/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await r.json(); } catch { /* empty body */ }
  if (!r.ok) {
    let msg = data && data.detail ? data.detail : r.statusText;
    if (Array.isArray(msg)) msg = msg.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join('; ');
    const err = new Error(msg);
    err.status = r.status;
    err.code = data && data.code;
    throw err;
  }
  return data;
}

// Tiny cache so tab switches feel instant; mutations clear it.
const cache = new Map();
export async function cached(path) {
  if (!cache.has(path)) cache.set(path, api(path).catch((e) => { cache.delete(path); throw e; }));
  return cache.get(path);
}
export function invalidate() { cache.clear(); }
