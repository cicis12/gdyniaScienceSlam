(() => {
  const settings = document.getElementById('interaction-analytics-config');
  if (!settings || window.self !== window.top || navigator.doNotTrack === '1' || navigator.globalPrivacyControl) return;
  const config = JSON.parse(settings.textContent);
  if (!config.consented) return;
  const current = new URL(location.href);
  const linkId = (config.link_id || current.searchParams.get('ref'))?.toLowerCase();
  if (current.searchParams.get('analytics') === 'off' || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(linkId || '')) return;
  if (!window.crypto?.getRandomValues) return;
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(value => value.toString(16).padStart(2, '0')).join('');
  const visitId = [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
  const publicPath = path => config.paths.includes(path) || /^\/forms\/[a-zA-Z0-9_-]{1,160}$/.test(path);
  const records = new Map();
  const elements = new Map();
  let stopped = false;
  let ready = false;
  let sending = false;
  let lastInput = performance.now();
  let lastTick = performance.now();
  let timer;
  const sample = key => {
    if (!records.has(key)) records.set(key, { section_id: key, visible_ms: 0, clicks: 0, faq_opens: 0 });
    return records.get(key);
  };
  sample('page');
  const candidates = [...document.querySelectorAll('[data-analytics-section], main section, body > section, main > header, main > dialog')];
  candidates.slice(0, 99).forEach((element, index) => {
    const raw = element.dataset.analyticsSection || element.id || element.getAttribute('aria-labelledby') || `block-${index + 1}`;
    const key = raw.replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 100);
    if (!key || key === 'page') return;
    elements.set(element, key);
    // No DOM text, input values, link destinations, or form contents are read.
  });
  const active = () => ready && !stopped && document.visibilityState === 'visible' && document.hasFocus() && performance.now() - lastInput < 60000;
  function visible(element) {
    if (element.closest('dialog:not([open])') || element.closest('[hidden]')) return false;
    const rect = element.getBoundingClientRect();
    const height = innerHeight - (document.querySelector('.site-nav')?.getBoundingClientRect().height || 0);
    const top = innerHeight - height;
    const shown = Math.min(rect.bottom, innerHeight) - Math.max(rect.top, top);
    return rect.width > 0 && rect.right > 0 && rect.left < innerWidth && rect.height > 0 && shown >= Math.min(rect.height, height) * .5;
  }
  function tick() {
    const now = performance.now();
    const elapsed = Math.min(Math.max(0, now - lastTick), 1500);
    lastTick = now;
    if (!active()) return;
    sample('page').visible_ms += elapsed;
    const modal = document.querySelector('dialog[open]');
    for (const [element, key] of elements) {
      if (modal && element !== modal && !modal.contains(element)) continue;
      if (visible(element)) sample(key).visible_ms += elapsed;
    }
  }
  function batch() {
    tick();
    return JSON.stringify({ link_id: linkId, visit_id: visitId, path: config.path,
      samples: [...records.values()].map(record => ({ ...record, visible_ms: Math.min(86400000, Math.floor(record.visible_ms)),
        clicks: Math.min(100000, record.clicks), faq_opens: Math.min(100000, record.faq_opens) })) });
  }
  async function flush() {
    if (stopped || sending) return;
    sending = true;
    try {
      const response = await fetch('/api/interactions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: batch(), keepalive: true });
      if ([403, 404, 409].includes(response.status)) stop(false);
      return response.ok;
    } catch { return false; }
    finally { sending = false; }
  }
  function beacon() {
    if (!ready || stopped) return;
    const body = batch();
    if (!navigator.sendBeacon?.('/api/interactions', new Blob([body], { type: 'application/json' }))) {
      fetch('/api/interactions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
    }
  }
  function decorate(link) {
    if (stopped || !link.href) return;
    const url = new URL(link.href, location.href);
    if (url.origin === location.origin && publicPath(url.pathname) && !url.searchParams.has('ref') && url.searchParams.get('analytics') !== 'off') {
      url.searchParams.set('ref', linkId); link.href = url.href;
    }
  }
  function stop(removeIdentifier) {
    stopped = true; clearInterval(timer);
    document.getElementById('stop-link-analytics')?.setAttribute('hidden', '');
    if (!removeIdentifier) return;
    const clean = new URL(location.href); clean.searchParams.delete('ref');
    history.replaceState(history.state, '', clean);
    document.querySelectorAll('a[href]').forEach(link => {
      const url = new URL(link.href, location.href);
      if (url.origin === location.origin && url.searchParams.get('ref') === linkId) { url.searchParams.delete('ref'); link.href = url.href; }
    });
  }
  ['pointerdown', 'pointermove', 'keydown', 'scroll', 'touchstart'].forEach(name => {
    window.addEventListener(name, () => { tick(); lastInput = performance.now(); }, { passive: true });
  });
  window.addEventListener('blur', () => { tick(); beacon(); lastTick = performance.now(); });
  window.addEventListener('focus', () => { lastInput = performance.now(); lastTick = lastInput; });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') beacon();
    lastTick = performance.now();
  });
  window.addEventListener('pagehide', beacon);
  window.addEventListener('pageshow', () => { lastTick = performance.now(); });
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (ready && link) decorate(link);
    if (!active() || !event.target.closest('a, button, summary')) return;
    const element = event.target.closest('[data-analytics-section], main section, body > section, main > header, main > dialog');
    sample(elements.get(element) || 'page').clicks += 1;
  });
  document.addEventListener('toggle', event => {
    if (!(event.target instanceof HTMLDetailsElement) || !event.target.open || !active() || !event.target.closest('.partnership-faq')) return;
    const element = event.target.closest('[data-analytics-section], main section');
    sample(elements.get(element) || 'page').faq_opens += 1;
  }, true);
  document.getElementById('stop-link-analytics')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    stop(true);
    try {
      const response = await fetch('/api/referrals/decision', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accepted: false }) });
      if (!response.ok) throw new Error();
      document.getElementById('interaction-analytics-config')?.remove();
      document.getElementById('referral-session-config')?.remove();
    } catch {
      button.hidden = false;
      button.textContent = 'Nie zapisano odmowy. Kliknij, aby spróbować ponownie.';
    }
  });
  flush().then(ok => {
    if (!ok || stopped) return;
    ready = true; lastTick = performance.now();
    document.querySelectorAll('a[href]').forEach(decorate);
    const optOut = document.getElementById('stop-link-analytics');
    if (optOut) optOut.hidden = false;
    let count = 0;
    timer = setInterval(() => { tick(); if (++count % 20 === 0) flush(); }, 500);
  });
})();
