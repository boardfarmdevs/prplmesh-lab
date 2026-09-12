'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const now = () => Number(process.hrtime.bigint()) / 1e6;
const quote = value => "'" + value.replaceAll("'", "'\\''") + "'";

function offsetBounds(samples, localTime, driftPpm = 100) {
  if (!samples.length) throw new Error('Clock calibration missing');
  const lower = Math.max(...samples.map(sample => sample.before - sample.remote -
    Math.abs(localTime - (sample.before + sample.after) / 2) * driftPpm / 1e6));
  const upper = Math.min(...samples.map(sample => sample.after - sample.remote +
    Math.abs(localTime - (sample.before + sample.after) / 2) * driftPpm / 1e6));
  if (![lower, upper].every(Number.isFinite) || lower > upper) throw new Error('Inconsistent monotonic clocks');
  return {lower, upper};
}

async function calibrate(readClock, count = 5) {
  const samples = [];
  for (let index = 0; index < count; index++) {
    const before = now();
    const remote = Number(await readClock());
    const after = now();
    if (!Number.isFinite(remote)) throw new Error('Invalid clock sample');
    samples.push({before, remote, after});
  }
  return samples;
}

function remoteTimeBounds(samples, remoteTime, driftPpm = 100) {
  if (!samples.length) throw new Error('Clock calibration missing');
  const fraction = driftPpm / 1e6;
  if (!Number.isFinite(remoteTime) || !Number.isFinite(fraction) || fraction < 0 || fraction >= 1) {
    throw new Error('Invalid clock mapping');
  }
  const intervals = samples.map(sample => {
    const delta = remoteTime - sample.remote;
    const endpoints = [delta / (1 - fraction), delta / (1 + fraction)];
    return {lower: sample.before + Math.min(...endpoints), upper: sample.after + Math.max(...endpoints)};
  });
  const lower = Math.max(...intervals.map(interval => interval.lower));
  const upper = Math.min(...intervals.map(interval => interval.upper));
  if (![lower, upper].every(Number.isFinite) || lower > upper) throw new Error('Inconsistent monotonic clocks');
  return {lower, upper};
}

function nativeObservations(records, events, clocks) {
  const transitions = [];
  const owners = new Map();
  for (const event of events.filter(event => event.kind === 'commit')
    .sort((left, right) => left.monotonic_ns - right.monotonic_ns)) {
    if (!event.associated) continue;
    const previous = owners.get(event.sta);
    if (!previous || previous.bssid !== event.bssid) transitions.push(event);
    owners.set(event.sta, event);
  }
  const used = new Set();
  const matchedThrough = new Map();
  return records.map(record => {
    if (!record.from || !record.to) return {...record, nativeScope: 'addition-or-removal-not-qualified'};
    const decoded = remoteTimeBounds(clocks.browser, record.receivedAt);
    const matches = transitions.filter(event => {
      const committed = event.monotonic_ns / 1e6;
      const guest = remoteTimeBounds(clocks.guest, committed);
      return event.sta === record.mac && event.bssid === record.to && !used.has(event) &&
        event.monotonic_ns > (matchedThrough.get(record.mac) ?? -Infinity) &&
        guest.lower <= decoded.upper &&
        decoded.lower - guest.upper <= 30000;
    });
    if (matches.length !== 1) return {...record, nativeObserved: false, nativeMatches: matches.length};
    const commit = matches[0];
    used.add(commit);
    matchedThrough.set(record.mac, commit.monotonic_ns);
    const committed = commit.monotonic_ns / 1e6;
    const guest = remoteTimeBounds(clocks.guest, committed);
    const delay = browserTime => {
      const browser = remoteTimeBounds(clocks.browser, browserTime);
      return {lower: browser.lower - guest.upper, upper: browser.upper - guest.lower};
    };
    const decodedDelay = delay(record.receivedAt);
    const paintDelay = record.paintObserved ? delay(record.receivedAt + record.decodedToPaintMs) : null;
    return {...record, nativeObserved: decodedDelay.upper >= 0 && Boolean(paintDelay),
      nativeCommit: commit, nativeToRequestMs: delay(record.requestedAt),
      nativeToDecodedMs: decodedDelay, nativeToPaintMs: paintDelay,
      clockUncertaintyMs: paintDelay ? paintDelay.upper - paintDelay.lower : null};
  });
}

async function startNativeTrace(args, directory, page) {
  if (!['rdk', 'prpl'].includes(args['native-stack']) || !args.host || !args.vm) {
    throw new Error('Native tracing requires --native-stack rdk|prpl --host HOST --vm VM');
  }
  if (![args.host, args.vm].every(value => /^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/.test(value))) {
    throw new Error('Invalid native trace host or VM');
  }
  const seconds = Number(args.seconds || 60);
  if (seconds > 150) throw new Error('Native/browser capture is bounded to 150 seconds');
  const prefix = 'lxc exec ' + quote(args.vm) + ' -- python3 -u -c ';
  const clocks = {guest: [], browser: []};
  const source = fs.readFileSync(path.join(__dirname, 'native-controller-trace.py'), 'utf8');
  const child = spawn('ssh', ['--', args.host, prefix + quote(source) + ' --stack ' + args['native-stack'] +
    ' --seconds ' + Math.ceil(seconds + 25) + ' --watch-stdin']);
  const events = [];
  const clockRequests = new Map();
  let clockSequence = 0;
  const readGuestClock = () => new Promise((resolve, reject) => {
    const request = 'clock:' + ++clockSequence;
    const timeout = setTimeout(() => { clockRequests.delete(request); reject(new Error('Native clock reply timed out')); }, 2000);
    clockRequests.set(request, value => { clearTimeout(timeout); resolve(value); });
    child.stdin.write(request + '\n');
  });
  let stderr = '';
  let failure = null;
  const filename = path.join(directory, 'native-events.jsonl');
  const descriptor = fs.openSync(filename, 'wx');
  const lines = createInterface({input: child.stdout});
  let readyResolve;
  let readyReject;
  const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject; });
  const exited = new Promise(resolve => child.once('close', code => {
    fs.closeSync(descriptor);
    if (code !== 0) failure ||= new Error('Native trace exited ' + code);
    if (!events.some(event => event.kind === 'ready')) readyReject(failure || new Error('Native trace never became ready'));
    resolve();
  }));
  lines.on('line', line => {
    try {
      const event = JSON.parse(line);
      fs.writeSync(descriptor, line + '\n');
      events.push(event);
      if (event.kind === 'clock') {
        clockRequests.get(event.request)?.(event.monotonic_ms);
        clockRequests.delete(event.request);
      }
      if (events.length > 100010) throw new Error('Native trace exceeded event budget');
      if (event.kind === 'ready') readyResolve();
    } catch (error) { failure = error; readyReject(error); child.stdin.end(); }
  });
  child.on('error', error => { failure = error; readyReject(error); });
  child.stdin.on('error', error => { failure ||= error; });
  child.stderr.on('data', chunk => { stderr += chunk; });
  const timer = setTimeout(() => readyReject(new Error('Native trace startup timed out')), 15000);
  let calibrationTimer;
  let calibrationInFlight = Promise.resolve();
  let stopping = false;
  const collectClocks = async () => {
    clocks.guest.push(...await calibrate(readGuestClock));
    clocks.browser.push(...await calibrate(() => page.evaluate(() => performance.now())));
  };
  const scheduleCalibration = () => {
    calibrationTimer = setTimeout(() => {
      calibrationInFlight = collectClocks().catch(error => { failure ||= error; }).finally(() => {
        if (!stopping) scheduleCalibration();
      });
    }, 10000);
  };
  const stop = async () => {
    stopping = true;
    clearTimeout(calibrationTimer);
    await calibrationInFlight;
    try {
      await collectClocks();
    } catch (error) { failure ||= error; }
    child.stdin.end();
    const timeout = setTimeout(() => { failure ||= new Error('Native trace shutdown timed out'); child.kill(); }, 10000);
    try { await exited; } finally { clearTimeout(timeout); }
    clocks.reference = now();
    fs.writeFileSync(path.join(directory, 'native-clocks.json'), JSON.stringify(clocks, null, 2) + '\n');
    fs.writeFileSync(path.join(directory, 'native-stderr.txt'), stderr);
    const end = events.find(event => event.kind === 'end');
    if (failure) throw failure;
    if (stderr.trim() || !end || end.lost !== 0 || end.records !== end.emitted ||
        end.records !== events.filter(event => event.kind === 'commit').length) {
      throw new Error('Native trace incomplete or reported diagnostics');
    }
    return {events, clocks, identity: events.find(event => event.kind === 'identity')};
  };
  try {
    await ready;
    await collectClocks();
    scheduleCalibration();
  }
  catch (error) { await stop().catch(() => {}); throw error; }
  finally { clearTimeout(timer); }
  return {stop};
}

module.exports = {offsetBounds, remoteTimeBounds, calibrate, nativeObservations, startNativeTrace};
