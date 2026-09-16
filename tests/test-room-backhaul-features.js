'use strict';

const assert = require('assert').strict;
const {interfaceState, summarizeNative, stackProfile, ready} = require('./room-backhaul-features.js');
assert.equal(stackProfile('rdk').gateway, '10.0.0.1');
assert.equal(stackProfile('prpl').gateway, '192.168.77.1');
assert.equal(stackProfile('prpl').healthNodes, 5);
assert.equal(stackProfile('prpl').containers.extender_3, 'prpl-agent-03');
assert.throws(() => stackProfile('unknown'));
const healthy = {native: {
  nodes: Object.fromEntries(['gateway', 'extender_1', 'extender_2', 'extender_3', 'extender_4']
    .map(role => [role, {pingOk: true, fronthaulAps: 6, apOperating: true}])),
  parents: {extender_1: 'gateway', extender_2: 'gateway', extender_3: 'extender_1', extender_4: 'extender_2'}},
  health: {healthy: true, topology_nodes: 5, api_active: 10},
  optimizer: {fleet: {converged: true}},
  topology: {nodes: Array(6).fill({}), stations: Array.from({length: 10}, (_, index) => ({mac: String(index)}))}};
assert.equal(ready(healthy, 5), true);
assert.equal(ready(healthy, 6), false);
assert.equal(ready({...healthy, native: {...healthy.native, nodes: {}}}, 5), false);
assert.equal(ready({...healthy, native: {...healthy.native, parents: {...healthy.native.parents, extender_4: null}}}, 5), false);
assert.equal(ready({...healthy, optimizer: {fleet: {converged: false}}}, 5), false);
const inactive = 'Interface wifi1.1\n addr 02:00:00:00:01:01\n type AP\n' +
  'Connected to 02:00:00:00:02:02 (on wifi1.3)\n SSID: mesh_backhaul\n freq: 5180\nPROBE_EXIT=0\n';
assert.equal(interfaceState(inactive).apOperating, false, 'STA SSID does not prove its backhaul AP is running');
assert.equal(interfaceState(inactive + '\nFRONTHAUL_APS=6\n').fronthaulAps, 6);
assert.ok(Number.isNaN(interfaceState(inactive).fronthaulAps), 'Missing AP observation must not imply readiness');
assert.equal(interfaceState(inactive).parentBssid, '02:00:00:00:02:02');
assert.equal(interfaceState(inactive).pingOk, true);
const active = inactive.replace(' type AP', ' ssid mesh_backhaul\n channel 36 (5180 MHz), width: 20 MHz\n type AP');
assert.equal(interfaceState(active).apOperating, true);
assert.equal(interfaceState('Not connected.\nPROBE_EXIT=1\n').parentBssid, null);
assert.equal(interfaceState('Not connected.\nPROBE_EXIT=1\n').pingOk, false);
const observed = [{native: {parents: {extender_3: 'extender_1', extender_4: 'extender_2'}, nodes: {extender_4: {pingOk: true}}}}];
assert.equal(summarizeNative(observed, 'backhaul-branch-formation').branchObserved, true);
assert.equal(summarizeNative(observed, 'backhaul-parent-handover').lowerRelayObserved, false);
assert.equal(summarizeNative([{native: {parents: {}, nodes: {extender_4: {pingOk: null}}}}],
  'backhaul-isolation-recovery').upstreamOutageObserved, false, 'Missing observations are not successful isolation');
assert.equal(summarizeNative([{native: {parents: {extender_4: null}, nodes: {extender_4: {pingOk: false}}}}],
  'backhaul-isolation-recovery').upstreamOutageObserved, true);
assert.equal(summarizeNative([{native: {parents: {extender_4: 'gateway'}, nodes: {extender_4: {pingOk: false}}}}],
  'backhaul-isolation-recovery').upstreamOutageObserved, false, 'One lost ping is not proof of backhaul isolation');
console.log('PASS: backhaul AP readiness, native parents, traffic and missing-observation classification');
