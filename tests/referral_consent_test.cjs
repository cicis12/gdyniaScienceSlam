// Run with: node tests/referral_consent_test.cjs
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('static/js/referral-consent.js', 'utf8');
const uuid = '10000000-0000-4000-8000-000000000001';

function browser({fail = false, dnt = false} = {}) {
  const requests = [], appended = [], registry = new Map();
  const buttons = ['no', 'yes'].map(choice => ({dataset:{referralChoice:choice}, addEventListener(type, fn) { this[type] = fn; }}));
  const dialog = {open:false, querySelectorAll: () => buttons, showModal() {this.open=true;}, close() {this.open=false;}, addEventListener(name, fn) {this[name]=fn;}};
  const status = {textContent:''};
  const config = {tracking:{paths:['/', '/become-a-partner'], path:'/', link_id:uuid, consented:false}, analytics_enabled:true, analytics_url:'/static/js/interaction-analytics.js?v=test', needs_popup:true, revision:'a'.repeat(64)};
  const settings = {textContent:JSON.stringify(config), removed:false, remove() { this.removed=true; registry.delete('referral-session-config'); }};
  registry.set('referral-session-config',settings); registry.set('referral-consent',dialog); registry.set('referral-consent-status',status);
  const links = [{href:`https://site.test/become-a-partner?ref=${uuid}`}, {href:`https://other.test/?ref=${uuid}`}];
  const context = {
    document:{getElementById:key=>registry.get(key), querySelectorAll:()=>links, createElement:()=>({}),
      body:{append(...elements) {for(const e of elements) {appended.push(e);registry.set(e.id,e);}}}},
    location:{href:`https://site.test/?ref=${uuid}`, origin:'https://site.test'},
    history:{state:null,replaceState(_state,_unused,url) {context.location.href=String(url);}},
    navigator:{doNotTrack:dnt?'1':'0'}, URL,
    async fetch(path, options) {const data=JSON.parse(options.body); requests.push({path,data}); return {ok:!fail,json:async()=>fail?{detail:'Cannot save choice'}:{consented:data.accepted,tracking:data.accepted}};},
  };
  context.window=context; context.self=context; context.top=context;
  vm.runInNewContext(source,context);
  return {context, settings, dialog, buttons, status, requests, appended, registry, links};
}
const settle = () => new Promise(resolve=>setImmediate(resolve));
(async()=>{
  const no = browser();
  assert.equal(no.dialog.open,true); assert.equal(no.requests.length,0); assert.equal(no.appended.length,0);
  no.buttons[0].click(); await settle();
  assert.equal(no.requests.length,1); assert.equal(no.requests[0].data.accepted,false);
  assert.equal(no.dialog.open,false); assert.equal(no.appended.length,0); assert.equal(no.settings.removed,true);
  assert.equal(new URL(no.context.location.href).searchParams.has('ref'),false);
  assert.equal(new URL(no.links[0].href).searchParams.has('ref'),false);
  assert.equal(new URL(no.links[1].href).searchParams.get('ref'),uuid);
  const yes = browser(); yes.buttons[1].click(); await settle();
  assert.equal(yes.requests[0].data.accepted,true); assert.equal(yes.requests[0].data.revision,'a'.repeat(64));
  assert.equal(yes.dialog.open,false); assert.equal(yes.appended.length,2);
  assert.equal(JSON.parse(yes.registry.get('interaction-analytics-config').textContent).consented,true);
  assert.equal(yes.registry.get('interaction-analytics-script').src,'/static/js/interaction-analytics.js?v=test');
  const failed = browser({fail:true}); failed.buttons[0].click(); await settle();
  assert.equal(failed.dialog.open,true); assert.equal(failed.appended.length,0); assert.equal(failed.buttons[0].disabled,false);
  assert.equal(failed.status.textContent,'Cannot save choice');
  const cancelled = browser(); cancelled.dialog.cancel({preventDefault(){}}); await settle();
  assert.equal(cancelled.requests[0].data.accepted,false); assert.equal(cancelled.dialog.open,false);
  const privateBrowser = browser({dnt:true}); privateBrowser.buttons[1].click(); await settle();
  assert.equal(privateBrowser.requests[0].data.accepted,false); assert.equal(privateBrowser.appended.length,0);
  console.log('Referral consent checks passed: no pre-consent requests, Yes, No, Escape, failure, privacy signal, UUID removal.');
})().catch(error=>{console.error(error);process.exitCode=1;});
