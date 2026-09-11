'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {distribution} = require('./room-feature-acceptance.js');

function installObserver() {
  const controller = window.EasyMeshController;
  const identity = value => String(value || '').toLowerCase();
  const associations = topology => new Map((topology?.nodes || []).flatMap(node =>
    (node.STAList || []).map(station => [identity(station.staMAC), identity(station.bssid)])));
  let previous = null;
  const pending = new Map();
  const records = [];
  let frame = null;
  let responses = 0;
  const finish = (record, fields) => {
    records.push({...record, ...fields});
    if (records.length > 4096) records.shift();
  };
  function inspect() {
    frame = null;
    const rendered = new Map([...document.querySelectorAll('#topology-visualization .sta-node')].map(element =>
      [identity(element.__data__?.sta?.staMAC), identity(element.__data__?.sta?.bssid)]));
    for (const [mac, record] of pending) {
      const matches = (rendered.get(mac) || null) === record.to;
      if (matches && record.matchedAt != null) {
        finish(record, {decodedResponseToSvgIdentityMs: performance.now() - record.receivedAt, passed: true});
        pending.delete(mac);
      } else if (performance.now() - record.receivedAt > 5000) {
        finish(record, {passed: false, timeout: true});
        pending.delete(mac);
      } else record.matchedAt = matches ? performance.now() : null;
    }
    if (pending.size) frame = requestAnimationFrame(inspect);
  }
  const original = controller.apiCall;
  controller.apiCall = async function (...args) {
    const result = await original.apply(this, args);
    if (args[0] === '/topology' && result?.nodes?.length) {
      responses++;
      const current = associations(result);
      if (previous === null) {
        previous = current;
        return result;
      }
      for (const mac of new Set([...previous.keys(), ...current.keys()])) {
        const from = previous.get(mac) || null;
        const to = current.get(mac) || null;
        if (from === to) continue;
        if (pending.has(mac)) finish(pending.get(mac), {passed: false, superseded: true});
        pending.set(mac, {mac, from, to, receivedAt: performance.now(), wallTime: new Date().toISOString()});
      }
      previous = current;
      if (pending.size && frame === null) frame = requestAnimationFrame(inspect);
    }
    return result;
  };
  window.__controllerRenderLatency = () => ({responses, records, pending: [...pending.values()]});
}

async function main(argv) {
  const args = Object.fromEntries(Array.from({length: argv.length / 2}, (_, index) =>
    [argv[index * 2].replace(/^--/, ''), argv[index * 2 + 1]]));
  if (!args.url || !args.output) throw new Error('Required: --url URL --output NEW_DIRECTORY [--seconds 60]');
  const seconds = Number(args.seconds || 60);
  if (!Number.isFinite(seconds) || seconds < 5 || seconds > 180) throw new Error('Duration must be 5–180 seconds');
  fs.mkdirSync(args.output);
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const environment = {...process.env};
  delete environment.DISPLAY;
  const browser = await chromium.launch({headless: true, env: environment,
    executablePath: process.env.CHROMIUM_PATH,
    args: ['--no-sandbox', '--ozone-platform=headless', '--disable-background-timer-throttling']});
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.goto(args.url);
    await page.locator('[data-tab="topology"]').click();
    await page.waitForSelector('.sta-node');
    await page.evaluate(installObserver);
    const session = await browser.newBrowserCDPSession();
    const processes = await session.send('SystemInfo.getProcessInfo');
    for (const process of processes.processInfo) {
      execFileSync('renice', ['19', '-p', String(process.id)], {stdio: 'ignore'});
    }
    await page.waitForTimeout(seconds * 1000);
    const observations = await page.evaluate(() => window.__controllerRenderLatency());
    const result = {url: args.url, seconds, errors, ...observations,
      scope: 'Decoded controller topology response to SVG-bound association identity across two animation frames; excludes native reporting, HTTP polling wait, paint timing and animation completion',
      latencyMs: distribution(observations.records.map(record => record.decodedResponseToSvgIdentityMs))};
    result.passed = !errors.length && observations.records.length > 0 &&
      observations.records.every(record => record.passed) && !observations.pending.length;
    fs.writeFileSync(path.join(args.output, 'report.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result));
    process.exitCode = result.passed ? 0 : 1;
  } finally {
    await browser.close();
  }
}

module.exports = {installObserver};
if (require.main === module) main(process.argv.slice(2)).catch(error => { console.error(error); process.exitCode = 2; });
