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
  let sequence = 0;
  const mark = name => { if (performance.mark) performance.mark(name); };
  const finish = (record, fields) => {
    records.push({...record, ...fields});
    if (records.length > 4096) records.shift();
  };
  function inspect() {
    frame = null;
    const elements = [...document.querySelectorAll('#topology-visualization .sta-node')];
    const rendered = new Map(elements.map(element =>
      [identity(element.__data__?.sta?.staMAC), identity(element.__data__?.sta?.bssid)]));
    for (const [mac, record] of pending) {
      const matches = (rendered.get(mac) || null) === record.to;
      if (matches && record.matchedAt != null) {
        finish(record, {decodedResponseToSvgIdentityMs: performance.now() - record.receivedAt, passed: true});
        pending.delete(mac);
      } else if (performance.now() - record.receivedAt > 5000) {
        finish(record, {passed: false, timeout: true});
        pending.delete(mac);
      } else {
        record.matchedAt = matches ? performance.now() : null;
        if (matches) {
          const element = elements.find(item => identity(item.__data__?.sta?.staMAC) === mac);
          const bounds = element?.getBoundingClientRect?.();
          if (bounds) record.bounds = {left: bounds.left, top: bounds.top, right: bounds.right, bottom: bounds.bottom};
          mark('controller-latency-svg:' + record.id);
        }
      }
    }
    if (pending.size) frame = requestAnimationFrame(inspect);
  }
  const original = controller.apiCall;
  controller.apiCall = async function (...args) {
    const requestedAt = performance.now();
    const result = await original.apply(this, args);
    const receivedAt = performance.now();
    if (args[0] === '/topology' && result?.nodes?.length) {
      responses++;
      mark('controller-latency-decoded:' + responses);
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
        const record = {id: ++sequence, responseId: responses, mac, from, to, requestedAt,
          receivedAt, wallTime: new Date().toISOString()};
        const element = [...document.querySelectorAll('#topology-visualization .sta-node')]
          .find(item => identity(item.__data__?.sta?.staMAC) === mac);
        const bounds = element?.getBoundingClientRect?.();
        if (bounds) record.bounds = {left: bounds.left, top: bounds.top, right: bounds.right, bottom: bounds.bottom};
        pending.set(mac, record);
      }
      previous = current;
      if (pending.size && frame === null) frame = requestAnimationFrame(inspect);
    }
    return result;
  };
  window.__controllerRenderLatency = () => ({responses, records, pending: [...pending.values()]});
}

function paintObservations(records, trace) {
  const events = trace.traceEvents || [];
  const marks = new Map(events.filter(event => event.name?.startsWith('controller-latency-'))
    .map(event => [event.name, event]));
  const paints = events.filter(event => event.name === 'Paint' && event.ph === 'X' && event.args?.data?.clip)
    .sort((left, right) => left.ts - right.ts);
  return records.map(record => {
    const decoded = marks.get('controller-latency-decoded:' + (record.responseId ?? record.id));
    const matched = marks.get('controller-latency-svg:' + record.id);
    if (!record.passed || !decoded || !matched || !record.bounds ||
        !Object.values(record.bounds).every(Number.isFinite) ||
        record.bounds.right <= record.bounds.left || record.bounds.bottom <= record.bounds.top ||
        !Number.isFinite(decoded.ts) || !Number.isFinite(matched.ts) || matched.ts < decoded.ts ||
        decoded.pid !== matched.pid || decoded.tid !== matched.tid) return {...record, paintObserved: false};
    const paint = paints.find(event => {
      if (!Number.isFinite(event.ts) || !Number.isFinite(event.dur) || event.dur < 0 ||
          event.pid !== matched.pid || event.tid !== matched.tid || event.ts < matched.ts ||
          event.ts - matched.ts > 500000) return false;
      const clip = event.args.data.clip;
      if (!Array.isArray(clip) || clip.length !== 8 || !clip.every(Number.isFinite)) return false;
      const horizontal = clip.filter((value, index) => index % 2 === 0);
      const vertical = clip.filter((value, index) => index % 2 === 1);
      return Math.min(...horizontal) <= record.bounds.left && Math.max(...horizontal) >= record.bounds.right &&
        Math.min(...vertical) <= record.bounds.top && Math.max(...vertical) >= record.bounds.bottom;
    });
    if (!paint) return {...record, paintObserved: false};
    const decodedToPaintMs = (paint.ts + (paint.dur || 0) - decoded.ts) / 1000;
    return {...record, paintObserved: true, decodedToPaintMs,
      requestToPaintMs: record.receivedAt - record.requestedAt + decodedToPaintMs,
      paint: {timestampUs: paint.ts, durationUs: paint.dur || 0, clip: paint.args.data.clip,
        nodeId: paint.args.data.nodeId, frame: paint.args.data.frame}};
  });
}

async function stopTrace(session, timeoutMs = 10000) {
  let timeout;
  let finished;
  const completed = new Promise((resolve, reject) => {
    finished = resolve;
    session.once('Tracing.tracingComplete', finished);
    timeout = setTimeout(() => reject(new Error('Chrome trace completion timed out')), timeoutMs);
  });
  let completion;
  try {
    [, completion] = await Promise.all([session.send('Tracing.end'), completed]);
  } finally {
    clearTimeout(timeout);
    session.removeListener('Tracing.tracingComplete', finished);
  }
  const {stream, dataLossOccurred} = completion;
  if (!stream) throw new Error('Chrome trace stream missing');
  const chunks = [];
  try {
    while (true) {
      const result = await session.send('IO.read', {handle: stream});
      chunks.push(Buffer.from(result.data, result.base64Encoded ? 'base64' : 'utf8'));
      if (result.eof) break;
    }
  } finally { await session.send('IO.close', {handle: stream}); }
  return {trace: JSON.parse(Buffer.concat(chunks).toString('utf8')), dataLossOccurred: dataLossOccurred ?? null};
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
    const session = await browser.newBrowserCDPSession();
    await session.send('Tracing.start', {categories: 'devtools.timeline,blink.user_timing',
      transferMode: 'ReturnAsStream'});
    await page.evaluate(installObserver);
    const processes = await session.send('SystemInfo.getProcessInfo');
    for (const process of processes.processInfo) {
      execFileSync('renice', ['19', '-p', String(process.id)], {stdio: 'ignore'});
    }
    await page.waitForTimeout(seconds * 1000);
    const observations = await page.evaluate(() => window.__controllerRenderLatency());
    const captured = await stopTrace(session);
    fs.writeFileSync(path.join(args.output, 'trace.json'), JSON.stringify(captured.trace));
    observations.records = paintObservations(observations.records, captured.trace);
    const result = {url: args.url, seconds, errors, ...observations,
      traceDataLoss: captured.dataLossOccurred,
      scope: 'HTTP request to decoded association, SVG identity and subsequent main-thread Paint covering the client bounds; excludes native commit-to-poll wait, compositor presentation, physical display and layout-animation completion',
      latencyMs: distribution(observations.records.map(record => record.decodedResponseToSvgIdentityMs)),
      decodedToPaintMs: distribution(observations.records.filter(record => record.paintObserved).map(record => record.decodedToPaintMs)),
      requestToPaintMs: distribution(observations.records.filter(record => record.paintObserved).map(record => record.requestToPaintMs))};
    result.passed = !errors.length && observations.records.length > 0 &&
      observations.records.every(record => record.passed && record.paintObserved) &&
      !observations.pending.length && captured.dataLossOccurred === false;
    fs.writeFileSync(path.join(args.output, 'report.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result));
    process.exitCode = result.passed ? 0 : 1;
  } finally {
    await browser.close();
  }
}

module.exports = {installObserver, paintObservations, stopTrace};
if (require.main === module) main(process.argv.slice(2)).catch(error => { console.error(error); process.exitCode = 2; });
