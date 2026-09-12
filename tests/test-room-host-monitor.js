'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {HostMonitor} = require('./room-host-monitor.js');
const {hostSummary} = require('./room-feature-report.js');

async function test() {
  const sample = {cpu_busy_percent: 10, available_memory_kib: 1048576, temperatures_celsius: {cpu: 60}};
  const summary = hostSummary([
    {...sample, time: '2026-09-12T00:00:00Z', cpu_busy_percent: 99, package_throttle_count: 10},
    {...sample, time: '2026-09-12T00:00:31Z', package_throttle_count: 20},
    {...sample, time: '2026-09-12T00:00:33Z', package_throttle_count: 22},
  ], '2026-09-12T00:00:30Z', '2026-09-12T00:00:34Z');
  assert.equal(summary.samples, 2);
  assert.equal(summary.samplingComplete, true);
  assert.equal(summary.cpuBusyPercent.max, 10);
  assert.equal(summary.packageThrottleDelta, 2);
  const broken = hostSummary([
    {...sample, time: '2026-09-12T00:00:31Z'},
    {...sample, time: '2026-09-12T00:00:33Z'},
  ], '2026-09-12T00:00:30Z', '2026-09-12T00:00:34Z', 'sampler exited unexpectedly');
  assert.equal(broken.samplingComplete, false);
  assert.equal(broken.packageThrottleDelta, null);
  assert.equal(broken.monitorError, 'sampler exited unexpectedly');
  const missing = hostSummary([], '2026-09-12T00:00:00Z', '2026-09-12T00:01:00Z');
  assert.equal(missing.samplingComplete, false);
  assert.equal(missing.packageThrottleDelta, null);
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'room-host-monitor-'));
  try {
    const filename = path.join(directory, 'samples.jsonl');
    const child = spawn('python3', ['-u', path.join(__dirname, 'room-feature-host-monitor.py'),
      '--interval', '.1', '--duration', '30', '--watch-stdin']);
    const monitor = new HostMonitor(child, filename);
    await monitor.ready;
    assert.ok(monitor.samples >= 2);
    assert.deepEqual(await monitor.stop(), {samples: monitor.samples, error: null, stopped: true});
    const samples = fs.readFileSync(filename, 'utf8').trim().split('\n').map(line => JSON.parse(line));
    assert.equal(samples.length, monitor.samples);
    const failed = new HostMonitor(spawn('python3', ['-c', 'raise SystemExit(3)']), path.join(directory, 'failed.jsonl'));
    await assert.rejects(failed.ready, /sampler/);
    assert.match((await failed.stop()).error, /unexpectedly/);
    console.log('PASS: host sampler readiness, retained samples, owned shutdown and early failure');
  } finally { fs.rmSync(directory, {recursive: true, force: true}); }
}
test().catch(error => { console.error(error); process.exitCode = 1; });
