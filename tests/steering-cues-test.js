'use strict';
const assert = require('assert/strict');
const path = require('path');
const cues = require(path.resolve(process.argv[2]));
const obstacle = {x: 140, y: -45, width: 120, height: 90};
const start = {x: 0, y: 0}, end = {x: 400, y: 0};
assert.equal(cues.segmentHitsBox(start, end, obstacle), true);
assert.equal(cues.segmentHitsBox({x: 0, y: -60}, {x: 400, y: -60}, obstacle), false);
assert.equal(cues.segmentHitsBox({x: 0, y: -100}, {x: 400, y: 100}, obstacle), true);
assert.equal(cues.segmentHitsBox({x: 0, y: 0}, {x: 0, y: 100}, obstacle), false);
const routed = cues.route(start, end, [obstacle]);
assert.ok(routed.length > 2);
assert.deepEqual(routed[0], start);
assert.deepEqual(routed.at(-1), end);
for (let index = 1; index < routed.length; index++) {
  assert.equal(cues.segmentHitsBox(routed[index - 1], routed[index], obstacle), false);
}
const occupied = [obstacle, {x: -30, y: -30, width: 60, height: 60}];
for (let ordinal = 0; ordinal < 100; ordinal++) {
  const label = cues.labelPosition(start, {width: 240, height: 54}, occupied, ordinal);
  assert.ok(occupied.every(box => !cues.intersects(label, box, 4)), 'label overlaps an entity or another label');
  occupied.push(label);
}
const paths = [];
for (let ordinal = 0; ordinal < 12; ordinal++) {
  const points = cues.route({x: 0, y: ordinal * 6}, {x: 400, y: 70 - ordinal * 6}, [obstacle], paths, ordinal);
  paths.push(points);
  for (let index = 1; index < points.length; index++) {
    assert.equal(cues.segmentHitsBox(points[index - 1], points[index], obstacle), false);
  }
}
assert.equal(new Set(paths.map(points => JSON.stringify(points))).size, 12);
assert.ok(cues.route(start, start, []).length >= 4, 'same-position band steer needs a visible loop');
assert.deepEqual(cues.route({x: NaN, y: 0}, end, []), []);
const effect = {staMAC: 'aa:bb', fromBSSID: 'old', toBSSID: 'new', changedAt: Date.now()};
const action = {sta_mac: 'aa:bb', source_bssid: 'old', target_bssid: 'new', method: 'btm-request', requested_at: new Date(effect.changedAt).toISOString()};
assert.equal(cues.style(effect, [action]).color, '#7c3aed');
assert.equal(cues.style(effect, [action]).label, 'BTM request');
assert.equal(cues.style(effect, []).method, 'unknown');
console.log('PASS: obstacle-free routes, separated simultaneous paths, 100 collision-free labels, band loops and purple BTM cues');
