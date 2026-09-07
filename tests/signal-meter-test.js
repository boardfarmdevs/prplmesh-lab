'use strict';

const assert = require('assert').strict;
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const viewerRoot = path.resolve(__dirname, '../wmediumd/configurator/worlds/viewer');
const signalMeter = require(path.join(viewerRoot, 'signal-meter.js'));

assert.equal(signalMeter.segmentCount, 10);
for (const [rssi, expected] of [
  [-110, 1], [-90, 1], [-86, 1], [-85, 2], [-80, 3], [-76, 3], [-75, 4],
  [-70, 5], [-67, 5], [-65, 6], [-60, 7], [-56, 7], [-55, 8], [-50, 9], [-45, 10], [0, 10],
]) {
  assert.equal(signalMeter.rssiLevel(rssi), expected, `${rssi} dBm`);
  assert.equal(signalMeter.snrLevel(rssi - signalMeter.noiseFloorDbm), expected);
  assert.equal(signalMeter.rssiColor(rssi), signalMeter.snrColor(rssi - signalMeter.noiseFloorDbm));
}
for (const value of [null, undefined, '', '0', false, NaN, Infinity, -111, 1]) {
  assert.equal(signalMeter.rssiLevel(value), 0, `invalid RSSI ${String(value)}`);
  assert.equal(signalMeter.rssiColor(value), signalMeter.colors.grey);
}
assert.equal(signalMeter.snrLevel(-20), 0);
assert.equal(signalMeter.snrLevel(null), 0);
assert.equal(signalMeter.snrLevel(0), 1);
for (let level = 0; level <= 10; level++) {
  const segments = Array.from({length: 10}, (_value, index) => signalMeter.segmentColor(index, level));
  assert.equal(segments.filter(color => color !== signalMeter.colors.grey).length, level);
  assert.ok(segments.slice(level).every(color => color === signalMeter.colors.grey));
}
assert.deepEqual(Array.from({length: 10}, (_value, index) => signalMeter.segmentColor(index, 10)), [
  ...Array(3).fill(signalMeter.colors.red), ...Array(4).fill(signalMeter.colors.yellow),
  ...Array(3).fill(signalMeter.colors.green),
]);
assert.equal(signalMeter.textColor(signalMeter.colors.yellow), '#111827');

const html = fs.readFileSync(path.join(viewerRoot, 'index.html'), 'utf8');
const levelSource = html.match(/  function signalLevel\(observed, predicted\) \{[\s\S]*?\n  \}(?=\n  function updateSignalGauge)/)[0];
const now = Date.now();
const context = {
  signalMeter, liveMode: true, replayMode: false,
  networkState: {observed_at: new Date(now).toISOString()},
};
vm.createContext(context);
vm.runInContext(levelSource, context);
const observed = {rssi_dbm: -67, metric_observed_at: new Date(now - 1000).toISOString()};
assert.equal(context.signalLevel(observed, {snr: 60}), 5);
assert.equal(context.signalLevel({...observed, rssi_dbm: null}, {snr: 60}), 0);
assert.equal(context.signalLevel(null, {snr: 60}), 0);
assert.equal(context.signalLevel({...observed, metric_observed_at: null}, {snr: 60}), 0);
assert.equal(context.signalLevel({...observed, metric_observed_at: new Date(now - 21000).toISOString()}, {snr: 60}), 0);
assert.equal(context.signalLevel({...observed, metric_observed_at: new Date(now + 10000).toISOString()}, {snr: 60}), 0);
context.liveMode = false;
assert.equal(context.signalLevel(null, {snr: 24}), 5);
context.replayMode = true;
context.networkState.observed_at = '2026-01-01T00:00:10Z';
assert.equal(context.signalLevel({rssi_dbm: -67, metric_observed_at: '2026-01-01T00:00:09Z'}, null), 5);
assert.doesNotMatch(html, /Private-Laptop/);
assert.match(html, /Traffic probe/);
assert.match(html, /signalMeter\.segmentColor\(index, level\)/);
console.log('PASS: shared red/yellow/green/grey meter, RSSI/SNR scale, missing/stale/replay readings and ordinary client identity');
