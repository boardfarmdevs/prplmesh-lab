'use strict';
const assert = require('node:assert/strict');
const {offsetBounds, remoteTimeBounds, nativeObservations} = require('./native-controller-latency.js');
assert.deepEqual(offsetBounds([{before: 9, remote: 5, after: 11}], 10, 0), {lower: 4, upper: 6});
assert.throws(() => offsetBounds([], 10), /missing/);
assert.throws(() => offsetBounds([{before: 10, remote: 1, after: 12}, {before: 20, remote: 1, after: 22}], 10, 0), /Inconsistent/);
const clocks = {reference: 0, guest: [{before: 0, remote: 0, after: 0}], browser: [{before: 0, remote: 0, after: 0}]};
const event = (timestamp, bssid) => ({kind: 'commit', monotonic_ns: timestamp * 1e6, sta: 'client', bssid, associated: true});
const record = (receivedAt, from, to) => ({mac: 'client', from, to, requestedAt: receivedAt - 5,
  receivedAt, paintObserved: true, decodedToPaintMs: 10});
const result = nativeObservations([record(20, 'old', 'first'), record(40, 'first', 'second'), record(60, 'second', 'first')],
  [event(10, 'first'), event(30, 'second'), event(50, 'first')], clocks);
assert.ok(result.every(row => row.nativeObserved));
assert.equal(result[2].nativeCommit.monotonic_ns, 50000000);
assert.ok(result[2].nativeToPaintMs.lower < 20 && result[2].nativeToPaintMs.upper > 20);
const drift = remoteTimeBounds([{before: 0, remote: 0, after: 0}, {before: 1000, remote: 1000, after: 1000}], 500);
assert.ok(drift.upper - drift.lower > .09);
assert.ok(drift.lower < 500 && drift.upper > 500);
assert.deepEqual(remoteTimeBounds([{before: 0, remote: 0, after: 0}], 50, 0), {lower: 50, upper: 50});
const recurrence = nativeObservations([record(20, null, 'first'), record(40, 'first', 'second'), record(60, 'second', 'first')],
  [event(10, 'first'), event(30, 'second'), event(50, 'first')], clocks);
assert.equal(recurrence[2].nativeObserved, true);
assert.equal(recurrence[2].nativeCommit.monotonic_ns, 50000000);
assert.equal(nativeObservations([record(20, 'old', 'missing')], [], clocks)[0].nativeObserved, false);
assert.equal(nativeObservations([record(20, null, 'first')], [event(10, 'first')], clocks)[0].nativeScope, 'addition-or-removal-not-qualified');
assert.equal(nativeObservations([record(60, 'old', 'first')], [event(10, 'first'), event(30, 'second'), event(50, 'first')], clocks)[0].nativeMatches, 2);
console.log('PASS: bounded clock mapping, missing/ambiguous commits, native owner recurrence and scope');
