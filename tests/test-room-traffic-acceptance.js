'use strict';
const assert = require('node:assert/strict');
const {trafficExperimentSummary, recordedEventKind} = require('./room-feature-acceptance.js');
const phase = {role: 'client', packets_per_second: 10, payload_bytes: 1200};
const world = {golden_sha256: 'world', traffic_experiment: {phases: [phase]}};
const result = {world_sha256: 'world', key: ['world', 1, 0], role: 'client',
  source: 'bound_client_wlan0_icmp_echo', state: 'completed', requested_packets: 50,
  transmitted_packets: 49, received_echo_replies: 48};
const event = payload => ({event: {kind: 'traffic.experiment', payload: {world_sha256: 'world', ...payload}}});
const records = [event({...result, state: 'running', requested_packets_per_second: 10, payload_bytes: 1200}),
  event({state: 'completed', history: [result]}), event({state: 'off', history: [result]})];
assert.equal(recordedEventKind('traffic.experiment'), true);
assert.equal(trafficExperimentSummary(world, records).passed, true);
assert.equal(trafficExperimentSummary(world, []).passed, false);
assert.equal(trafficExperimentSummary(world, records.slice(0, 2)).passed, false);
for (const change of [{received_echo_replies: 0}, {transmitted_packets: null},
  {requested_packets: 40}, {state: 'failed'}, {role: 'other'}, {world_sha256: 'old'}]) {
  assert.equal(trafficExperimentSummary(world, [records[0], event({state: 'off', history: [{...result, ...change}]})]).passed, false);
}
console.log('PASS: actual traffic phases, identities, counts and off-state required');
