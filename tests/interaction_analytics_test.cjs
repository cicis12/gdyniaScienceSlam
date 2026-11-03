// Run with: node tests/interaction_analytics_test.cjs
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { webcrypto } = require('node:crypto');
const vm = require('node:vm');
const source = readFileSync('static/js/interaction-analytics.js', 'utf8');
const uuid = '10000000-0000-4000-8000-000000000001';

async function browser({ dnt = false, optedOut = false, preview = false } = {}) {
  let clock = 0;
  let interval;
  let stopped = false;
  const requests = [];
  const events = new Map();
  const documentEvents = new Map();
  const anchors = [
    { href: 'https://example.test/about?x=1#benefits' },
    { href: 'https://example.test/admin/content' },
    { href: 'https://external.test/about' },
    { href: 'https://example.test/static/document.pdf' },
  ];
  const section = { dataset: { analyticsSection: 'section-visible' }, id: '', getAttribute: () => null,
    closest: () => null, getBoundingClientRect: () => ({ top: 100, bottom: 600, height: 500, width: 800, left: 0, right: 800 }) };
  const hidden = { ...section, dataset: { analyticsSection: 'section-below-fold' },
    getBoundingClientRect: () => ({ top: 1500, bottom: 2000, height: 500, width: 800, left: 0, right: 800 }) };
  const optOut = { hidden: true, setAttribute(name) { if (name === 'hidden') this.hidden = true; },
    addEventListener(name, callback) { this[name] = callback; } };
  const add = map => (name, fn) => map.set(name, [...(map.get(name) || []), fn]);
  const config = { paths: ['/', '/about', '/become-a-partner'], path: '/become-a-partner', consented: true };
  const document = {
    visibilityState: 'visible', focused: true, hasFocus() { return this.focused; },
    getElementById(id) { return id === 'interaction-analytics-config' ? { textContent: JSON.stringify(config) } : optOut; },
    querySelector(selector) { return selector === '.site-nav' ? { getBoundingClientRect: () => ({ height: 100 }) } : null; },
    querySelectorAll(selector) { return selector === 'a[href]' ? anchors : [section, hidden]; },
    addEventListener: add(documentEvents),
  };
  const context = {
    document, navigator: { doNotTrack: dnt ? '1' : '0', sendBeacon: () => true },
    location: { href: `https://example.test/become-a-partner?ref=${uuid}${optedOut ? '&analytics=off' : ''}`, origin: 'https://example.test' },
    performance: { now: () => clock }, crypto: webcrypto, URL, Uint8Array, Blob,
    innerHeight: 1000, innerWidth: 1000, HTMLDetailsElement: class {},
    addEventListener: add(events),
    setInterval(fn) { interval = fn; return 1; }, clearInterval() { stopped = true; },
    history: { state: null, replaceState(_a, _b, url) { context.location.href = url.toString(); } },
    async fetch(_url, options) { requests.push(JSON.parse(options.body)); return { status: 204, ok: true }; },
  };
  context.window = context; context.self = context; context.top = preview ? {} : context;
  vm.runInNewContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  async function advance(milliseconds) {
    for (let elapsed = 0; elapsed < milliseconds; elapsed += 500) {
      clock += 500;
      if (interval && !stopped) interval();
      await Promise.resolve();
    }
    await new Promise(resolve => setImmediate(resolve));
  }
  function emit(map, name, event = {}) { (map.get(name) || []).forEach(fn => fn(event)); }
  return { context, document, section, optOut, requests, anchors, advance,
    input: () => emit(events, 'pointerdown'), visibility: () => emit(documentEvents, 'visibilitychange'),
    click: () => emit(documentEvents, 'click', { target: { closest(selector) { return selector === 'a[href]' ? null : selector === 'a, button, summary' ? {} : section; } } }) };
}

(async () => {
  for (const option of [{dnt:true}, {optedOut:true}, {preview:true}]) {
    const b = await browser(option); assert.equal(b.requests.length, 0, 'Privacy exclusions must send nothing');
  }
  const b = await browser();
  assert.equal(b.requests.length, 1);
  assert.equal(b.optOut.hidden, false);
  assert.equal(new URL(b.anchors[0].href).searchParams.get('ref'), uuid);
  assert.equal(new URL(b.anchors[0].href).searchParams.get('x'), '1');
  assert.equal(new URL(b.anchors[0].href).hash, '#benefits');
  b.anchors.slice(1).forEach(a => assert.equal(new URL(a.href).searchParams.has('ref'), false));
  await b.advance(10000);
  let latest = b.requests.at(-1);
  assert.equal(latest.samples.find(s => s.section_id === 'page').visible_ms, 10000);
  assert.equal(latest.samples.find(s => s.section_id === 'section-visible').visible_ms, 10000);
  assert.equal(latest.samples.some(s => s.section_id === 'section-below-fold'), false);
  b.document.visibilityState = 'hidden'; b.visibility();
  await b.advance(10000);
  assert.equal(b.requests.at(-1).samples.find(s => s.section_id === 'page').visible_ms, 10000);
  b.document.visibilityState = 'visible'; b.visibility(); b.input();
  b.document.focused = false;
  await b.advance(10000);
  assert.equal(b.requests.at(-1).samples.find(s => s.section_id === 'page').visible_ms, 10000);
  b.document.focused = true; b.input(); b.click();
  await b.advance(70000);
  const beforeIdle = b.requests.at(-1).samples.find(s => s.section_id === 'page').visible_ms;
  await b.advance(10000);
  assert.equal(b.requests.at(-1).samples.find(s => s.section_id === 'page').visible_ms, beforeIdle, 'Idle time must not accumulate');
  assert.equal(b.requests.at(-1).samples.find(s => s.section_id === 'section-visible').clicks, 1);
  assert.equal(Object.hasOwn(b.requests.at(-1), 'email'), false);
  await b.optOut.click({ currentTarget: b.optOut });
  const count = b.requests.length;
  await b.advance(10000);
  assert.equal(b.requests.length, count, 'Opt-out must stop collection immediately');
  assert.equal(new URL(b.context.location.href).searchParams.has('ref'), false);
  assert.equal(new URL(b.anchors[0].href).searchParams.has('ref'), false);
  console.log('Analytics browser-state checks passed: visibility, focus, idle, navigation, exclusions, opt-out.');
})().catch(error => { console.error(error); process.exitCode = 1; });
