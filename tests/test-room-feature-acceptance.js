'use strict';
const assert = require('node:assert/strict');
const {expectedFrame, evaluate, distribution, eventPerformance, viewAgreement} = require('./room-feature-acceptance.js');
const now = Date.now();
const timestamp = new Date(now).toISOString();
const world = {roles: {client: 'station'}, generations: [
  {time_ms: 0, positions: {client: [0, 0]}, present: {client: true}},
  {time_ms: 10000, positions: {client: [10, 0]}, present: {client: true}},
  {time_ms: 20000, positions: {client: [20, 0]}, present: {client: false}},
]};
assert.deepEqual(expectedFrame(world, 5000).client.position, [5, 0]);
assert.deepEqual(expectedFrame(world, 15000).client.position, [10, 0]);
assert.equal(expectedFrame(world, 20000).client.present, false);
const bindings = {client: {sta_mac: 'aa'}};
const parents = ['ext1', 'ext2', 'ext3', 'ext4'];
const current = {environment_epoch: 1, health: {healthy: true, expected_online_clients: 1},
  network: {clients: [{sta_mac: 'aa', connected_bssid: 'bb', ssid: 'private', rcpi: 100, metric_observed_at: timestamp}],
    mesh: {nodes: ['gateway', ...parents].map(role => ({role, device_id: role})),
      backhaul_edges: parents.map(role => ({child_role: role, parent_role: 'gateway'}))}},
  optimizer: {environment_epoch: 1, evaluated_at: timestamp,
    fleet: {converged: true, measurement_complete: true, clients_checked: 1, clients_evaluated: 1, clients_with_stronger_ap: 0},
    client_decisions: [{sta_mac: 'aa', source_bssid: 'bb', current_rcpi: 100, current_band: '5', scores: [{band: '5', gain_rcpi: -2}]}]}};
const interactions = {environment_epoch: 1, playback: {time_ms: 0}, roles: {client: {position: [0, 0], present: true}}};
const station = {mac: 'aa', bssid: 'bb', ssid: 'private'};
const view = {meshCount: 6, stations: [station], modelStations: [station], edges: parents.map(role => ({to: role, from: 'gateway'}))};
const check = (snapshot = current, state = interactions, rendered = view) => evaluate(snapshot, state, rendered, world, bindings, now);
assert.equal(check().converged, true);
assert.equal(check(current, interactions, {...view, stations: [station, station]}).converged, false);
assert.equal(check(current, interactions, {...view, stations: [{...station, bssid: 'wrong'}]}).viewMatchesRoom, false);
assert.equal(check(current, {...interactions, environment_epoch: 2}).converged, false);
assert.equal(check({...current, optimizer: {...current.optimizer, evaluated_at: new Date(now - 31000).toISOString()}}).converged, false);
assert.equal(check({...current, optimizer: {...current.optimizer, fleet: {...current.optimizer.fleet, measurement_complete: false}}}).converged, false);
assert.equal(check({...current, network: {...current.network, clients: [{...current.network.clients[0], rcpi: 0}]}}).converged, false);
assert.equal(check({...current, network: {...current.network, mesh: {...current.network.mesh,
  backhaul_edges: current.network.mesh.backhaul_edges.map(edge => ({...edge, parent_role: edge.child_role}))}}}).meshConnected, false);
assert.equal(check(current, {...interactions, roles: {client: {position: [5, 0], present: true}}}).converged, false);
assert.equal(check(current, interactions, {...view, edges: []}).meshViewMatches, false);
assert.deepEqual(distribution([1, 2, 4, 3]), {count: 4, p50: 2, p95: 4, max: 4});
assert.deepEqual(distribution([]), {count: 0, p50: null, p95: null, max: null});
const measured = eventPerformance([
  {event: {kind: 'optimizer.action', payload: {phase: 'requested'}}},
  {event: {kind: 'optimizer.action', payload: {phase: 'submitted'}}},
  {event: {kind: 'optimizer.collection', payload: {phase: 'completed', transactions: [{operation: 'register'}]}}},
  {event: {kind: 'optimizer.collection', payload: {phase: 'published', publication_wait_ms: 12}}},
]);
assert.equal(measured.submittedActions, 1);
assert.equal(measured.candidateTransactionMs.count, 0);
assert.equal(measured.candidatePublicationWaitMs.p50, 12);
const actionTimings = eventPerformance([
  {event: {kind: 'optimizer.action', recorded_at: '2026-09-09T00:00:00Z', payload: {phase: 'requested', decision: {sta_mac: 'aa', target_bssid: 'bb'}}}},
  {event: {kind: 'optimizer.action', recorded_at: '2026-09-09T00:00:02Z', payload: {phase: 'submitted', decision: {sta_mac: 'aa', target_bssid: 'bb'}}}},
  {event: {kind: 'optimizer.verification', recorded_at: '2026-09-09T00:00:03Z', payload: {success: true, subject_mac: 'aa', target_bssid: 'bb'}}},
]);
assert.equal(actionTimings.submissionSeconds.p50, 2);
assert.equal(actionTimings.requestToVerificationSeconds.p50, 3);
const overlapping = eventPerformance([
  {event: {kind: 'optimizer.action', recorded_at: '2026-09-09T00:00:00Z', payload: {phase: 'requested', action_id: 'first'}}},
  {event: {kind: 'optimizer.action', recorded_at: '2026-09-09T00:00:01Z', payload: {phase: 'requested', action_id: 'second'}}},
  {event: {kind: 'optimizer.verification', recorded_at: '2026-09-09T00:00:02Z', payload: {success: true, action_id: 'first'}}},
  {event: {kind: 'optimizer.collection', payload: {phase: 'completed', transactions: [
    {operation: 'timestamp_resolution_wait', elapsed_ms: 750},
    {error: 'HTTP 503 Error_Prev_Cmd_In_Progress', native_admission_busy: true, elapsed_ms: 100},
    {error: 'HTTP 504', elapsed_ms: 8000},
  ]}}},
]);
assert.equal(overlapping.requestToVerificationSeconds.p50, 2);
assert.equal(overlapping.collectionOperationMs.timestamp_resolution_wait.p50, 750);
assert.equal(overlapping.nativeBusyRejections, 1);
assert.equal(overlapping.nativeBusyReadmissions, 1);
assert.equal(overlapping.nativeResponseTimeouts, 1);
const matching = {viewMatchesRoom: true, viewMatchesModel: true, duplicates: false};
assert.equal(viewAgreement([{...matching, monoMs: 0, viewMatchesRoom: false}, {...matching, monoMs: 6000}]).passed, true);
assert.equal(viewAgreement(Array.from({length: 7}, (_, index) => ({...matching, monoMs: index * 1000, viewMatchesRoom: false}))).passed, false);
console.log('PASS: golden interpolation, absence, duplicates, ownership, epochs, freshness, coverage, mesh, script and percentile checks');
