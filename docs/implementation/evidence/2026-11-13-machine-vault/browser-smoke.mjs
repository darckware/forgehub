// Fixture-only browser proof. Start task Vite :5197 and Chrome CDP :9247.
// All /api calls are intercepted; no real credentials or machines are used.
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const output = fileURLToPath(new URL('./', import.meta.url));
const cdpPort = process.env.CDP_PORT || '9247';
const pages = await (await fetch(`http://127.0.0.1:${cdpPort}/json`)).json();
const ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
let serial = 0; const pending = new Map(), errors = [], mutations = [];
const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++serial; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params })); });
const base = { ssh_port: 22, ssh_key_path: null, public_key: null, private_key_stored: false, key_passphrase_stored: false, access_enabled: true, environment: 'semed', os_family: 'linux', kind: 'server', admin_user: 'aegis', group_ids: [], tailnet_node_id: null };
const machines = [
 { ...base, id: 'legacy', name: 'srv-app02', ip_address: '192.0.2.3', remote_user: 'aegis' },
 { ...base, id: 'own', name: 'srv-own', ip_address: '192.0.2.4', remote_user: 'darckware', ssh_key_in_vault: true, login_password_stored: true, login_password_in_vault: true, access_verified_at: '2026-11-13T18:00:00Z' },
 { ...base, id: 'staged', name: 'srv-pending', ip_address: '192.0.2.5', remote_user: 'aegis', preparation_pending: true },
];
let validations = 0;
ws.addEventListener('message', async event => {
 const message = JSON.parse(event.data);
 if (pending.has(message.id)) { const item = pending.get(message.id); pending.delete(message.id); message.error ? item.reject(message.error) : item.resolve(message.result); }
 if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
 if (message.method === 'Fetch.requestPaused') {
  const { requestId, request } = message.params; const path = new URL(request.url).pathname; let data = [], code = 200;
  if (request.method !== 'GET') mutations.push({ path, method: request.method, body: request.postData ? JSON.parse(request.postData) : null });
  if (path.endsWith('/servers')) data = machines;
  else if (path.endsWith('/servers/readiness')) data = { entries: machines.map(m => ({ server_id: m.id, readiness: 'ready', status: 'complete', ssh: 'active', access_path: 'subnet', detail: null, access_via_name: 'lab-router', access_via_node_id: 'router' })), checked_at: new Date().toISOString(), tailnet_available: true };
  else if (path.endsWith('/vpn/status')) data = { server: { posture: { accept_routes: true } }, peers: [], sources: [] };
  else if (path.endsWith('/preparation/pending')) data = { server_id: 'staged', script: '# fixture staged instructions', language: 'sh', public_key: 'fixture-public-only', execution_id: null };
  else if (path.endsWith('/preparation/validate')) {
   validations++; data = validations === 1 ? { ok: false, detail: 'Fixture: login validation failed' } : { ok: true };
   if (data.ok) { machines[2].remote_user = 'darckware'; machines[2].preparation_pending = false; machines[2].access_verified_at = '2026-11-13T19:00:00Z'; machines[2].ssh_key_in_vault = true; machines[2].login_password_in_vault = true; }
  }
  else if (path.endsWith('/notifications/unread-count')) data = { count: 0 };
  await send('Fetch.fulfillRequest', { requestId, responseCode: code, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(JSON.stringify(data)).toString('base64') });
 }
});
await send('Runtime.enable'); await send('Page.enable');
await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/*', requestStage: 'Request' }] });
const user = { id: 'fixture-human', username: 'fixture', is_admin: true, is_active: true, ui_language: 'pt-BR', full_name: 'Fixture operator', avatar_data_url: null };
await send('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('forgehub-auth', ${JSON.stringify(JSON.stringify({ state: { token: 'fixture-only', user, permissions: {}, actions: {} }, version: 0 }))});localStorage.setItem('i18nextLng','pt-BR');` });
const evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (result.exceptionDetails) throw Error(result.exceptionDetails.text); return result.result.value; };
async function until(expression) { for (let i = 0; i < 200; i++) { if (await evaluate(`Boolean(${expression})`)) return; await new Promise(resolve => setTimeout(resolve, 100)); } throw Error(`Timed out: ${expression}; errors=${JSON.stringify(errors)}`); }
const clickText = text => evaluate(`[...document.querySelectorAll('button')].find(button => button.textContent.trim() === ${JSON.stringify(text)})?.click()`);
const clickLabel = label => evaluate(`document.querySelector('button[aria-label="${label}"]')?.click()`);
const selectMachine = id => evaluate(`{const input=document.querySelector('#prep-machine'); Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(input,${JSON.stringify(id)}); input.dispatchEvent(new Event('change',{bubbles:true}));}`);
await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: 'http://127.0.0.1:5197/remote-access' });
await until(`document.querySelector('button[aria-label="Reconfigurar acesso a srv-app02"]')`);
assert(await evaluate(`document.body.textContent.includes('Reconfiguração necessária')`));
const desktopNameWidth = await evaluate(`[...document.querySelectorAll('td')].find(cell=>cell.querySelector('p')?.textContent==='srv-app02').getBoundingClientRect().width`);
assert(desktopNameWidth >= 180, `Machine name column too narrow: ${desktopNameWidth}`);
await send('Page.captureScreenshot').then(result => writeFileSync(output + 'desktop-machines.png', Buffer.from(result.data, 'base64')));
await clickLabel('Reconfigurar acesso a srv-app02');
await until(`document.querySelector('#prep-machine')?.value==='legacy'`);
assert(await evaluate(`document.querySelector('[role="dialog"]').textContent.includes('Conta cadastrada: aegis')`));
await selectMachine('own');
await until(`document.querySelector('[role="dialog"]').textContent.includes('Usar a senha darckware desta máquina')`);
assert(await evaluate(`[...document.querySelectorAll('label')].find(label=>label.textContent.includes('Bloquear a conta')).querySelector('input').disabled`));
await evaluate(`[...document.querySelectorAll('label')].find(label=>label.textContent.includes('Usar a senha darckware desta máquina')).querySelector('input').click()`);
await until(`!document.querySelector('#prep-password')`);
await send('Page.captureScreenshot').then(result => writeFileSync(output + 'desktop-own-account.png', Buffer.from(result.data, 'base64')));
// Exercise the full machine list and panel from a fresh layout at each viewport.
await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false });
await send('Page.navigate', { url: 'http://127.0.0.1:5197/remote-access' });
await until(`document.querySelector('button[aria-label="Reconfigurar acesso a srv-own"]')`);
assert.equal(await evaluate(`innerWidth`), 390);
await send('Page.captureScreenshot').then(result => writeFileSync(output + 'mobile-machines.png', Buffer.from(result.data, 'base64')));
assert(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth + 1`), await evaluate(`JSON.stringify({html:document.documentElement.scrollWidth,body:document.body.scrollWidth,unclipped:[...document.querySelectorAll('body *')].filter(e=>{let r=e.getBoundingClientRect();if(!r.width||r.right<=innerWidth+1)return false;for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){if(['hidden','auto','scroll','clip'].includes(getComputedStyle(p).overflowX))return false;}return true;}).map(e=>({tag:e.tagName,cls:e.className,r:e.getBoundingClientRect().right,w:e.getBoundingClientRect().width,position:getComputedStyle(e).position}))})`));
await clickLabel('Reconfigurar acesso a srv-own');
await until(`document.querySelector('#prep-machine')?.value==='own'`);
await evaluate(`[...document.querySelectorAll('label')].find(label=>label.textContent.includes('Usar a senha darckware desta máquina')).querySelector('input').click()`);
await until(`!document.querySelector('#prep-password')`);
await until(`document.documentElement.scrollWidth <= window.innerWidth + 1`);
const mobileMetrics = await evaluate(`({inner:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,scrollX,bodyWidth:document.body.scrollWidth,visual:visualViewport.width,scale:visualViewport.scale})`);
assert.equal(mobileMetrics.inner, 390);
assert.equal(mobileMetrics.client, 390);
assert.equal(mobileMetrics.visual, 390);
assert.equal(mobileMetrics.scale, 1);
await send('Page.captureScreenshot').then(result => writeFileSync(output + 'mobile-own-account.png', Buffer.from(result.data, 'base64')));
assert(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth + 1`), JSON.stringify({ mobileMetrics, offenders: await evaluate(`[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.left>=0&&r.right>innerWidth+1}).slice(0,15).map(e=>({tag:e.tagName,cls:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width,parents:[e.parentElement,e.parentElement?.parentElement,e.parentElement?.parentElement?.parentElement].filter(Boolean).map(p=>({tag:p.tagName,cls:p.className,overflow:getComputedStyle(p).overflowX,client:p.clientWidth,scroll:p.scrollWidth}))}))`) }));
await selectMachine('staged');
await until(`document.querySelector('[role="dialog"]').textContent.includes('Recuperar instruções pendentes')`);
await clickText('Recuperar instruções pendentes');
await until(`document.querySelector('pre')?.textContent.includes('fixture staged instructions')`);
await clickText('Validar acesso');
await until(`document.querySelector('[role="alert"]')?.textContent.includes('Fixture: login validation failed')`);
assert(await evaluate(`document.querySelector('[role="dialog"]').textContent.includes('Há uma configuração pendente')`));
await send('Page.captureScreenshot').then(result => writeFileSync(output + 'mobile-validation-failure.png', Buffer.from(result.data, 'base64')));
await clickText('Validar acesso');
await until(`document.querySelector('[role="dialog"]').textContent.includes('Acesso darckware validado')`);
assert(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth + 1`));
await send('Page.captureScreenshot').then(result => writeFileSync(output + 'mobile-validation-success.png', Buffer.from(result.data, 'base64')));
assert.equal(errors.length, 0, JSON.stringify(errors));
assert.deepEqual(mutations.map(item=>item.path), ['/api/v1/servers/staged/preparation/pending','/api/v1/servers/staged/preparation/validate','/api/v1/servers/staged/preparation/validate']);
writeFileSync(output + 'browser-result.json', JSON.stringify({ fixtureOnly: true, widths: [1440,390], mobileMetrics, desktopNameWidth, errors, mutations, success: true }, null, 2));
console.log('PASS: ready legacy reconfiguration; own Vault password; self-lock protection; pending recovery; validation failure/success; 1440px/390px without page overflow.');
await send('Fetch.disable'); ws.close();
