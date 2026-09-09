'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {distribution, eventPerformance, viewAgreement} = require('./room-feature-acceptance.js');

function readJsonLines(filename) {
  return fs.readFileSync(filename, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line));
}

function summarize(directory, worlds = path.join(directory, '..', 'goldens')) {
  const report = JSON.parse(fs.readFileSync(path.join(directory, 'report.json')));
  const events = readJsonLines(path.join(directory, 'events.jsonl'));
  const gates = ['roster', 'viewMatchesRoom', 'viewMatchesModel', 'healthy', 'epochMatches', 'complete',
    'sameBandBest', 'metricsFresh', 'meshConnected', 'meshViewMatches', 'policyConverged'];
  const rooms = report.rooms.map(room => {
    const samples = readJsonLines(path.join(directory, room.id + '-samples.jsonl'));
    const golden = JSON.parse(fs.readFileSync(path.join(worlds, room.id + '.world.json')));
    const snapshotPath = path.join(directory, room.id + '-loaded.json');
    const snapshot = fs.existsSync(snapshotPath) ? JSON.parse(fs.readFileSync(snapshotPath)) : null;
    const devices = Object.fromEntries((snapshot?.current.network.mesh.nodes || []).map(node => [node.role, String(node.device_id)]));
    const owners = samples.map(sample => {
      const associations = new Map((sample.roomAssociations || []).map(client => [client.mac.toLowerCase(), client]));
      return {time: sample.wallTime, phase: sample.phase, errors: sample.associations.filter(client => {
        const native = associations.get(client.mac.toLowerCase());
        return native && native.bssid === client.bssid && devices[native.ap] !== client.owner;
      }).map(client => client.mac)};
    }).filter(sample => sample.errors.length);
    const phases = Object.fromEntries([...new Set(samples.map(sample => sample.phase))].map(phase => {
      const selected = samples.filter(sample => sample.phase === phase);
      return [phase, {samples: selected.length,
        failedGates: Object.fromEntries(gates.map(gate => [gate, selected.filter(sample => !sample[gate]).length])),
        scriptErrors: selected.filter(sample => sample.scriptErrors.length).length,
        sceneErrors: selected.filter(sample => sample.sceneErrors.length).length,
        metricFaults: [...new Set(selected.map(sample => sample.unavailable).filter(Boolean))],
        firstConverged: selected.find(sample => sample.converged)?.playback.time_ms ?? null,
      }];
    }));
    const outages = Object.entries(golden.roles).filter(([, kind]) => kind === 'fronthaul_ap').flatMap(([role]) => {
      const start = golden.generations.find(frame => !frame.present[role])?.time_ms;
      if (start === undefined) return [];
      const end = golden.generations.find(frame => frame.time_ms > start && frame.present[role])?.time_ms ?? golden.duration_ms + 1;
      const checked = samples.filter(sample => sample.phase === 'playing' && sample.playback.time_ms >= start + 5000 && sample.playback.time_ms < end);
      return [{role, startMs: start, endMs: end, samples: checked.length,
        remainingAssociations: checked.filter(sample => (sample.roomAssociations || []).some(client => client.ap === role)).map(sample => sample.playback.time_ms),
        meshConnected: checked.every(sample => sample.meshConnected && sample.meshViewMatches)}];
    });
    let directional = null;
    const auditPath = path.join(directory, '..', 'asymmetric-rf-audit.json');
    if (room.id === 'home-a-asymmetric-link' && fs.existsSync(auditPath)) {
      const audit = JSON.parse(fs.readFileSync(auditPath));
      const frame = golden.generations.findLast(item => item.time_ms <= audit.playback.time_ms) || golden.generations[0];
      const mismatches = audit.links.filter(row => {
        const down = frame.links.find(link => link.source_role === row.ap && link.destination_role === 'sta_mobile_01').snr_db_by_band[row.band];
        const up = frame.links.find(link => link.destination_role === row.ap && link.source_role === 'sta_mobile_01').snr_db_by_band[row.band];
        return row.uplink_minus_downlink_db !== up - down;
      });
      const generationStable = new Set(audit.links.flatMap(row => [row.up[0], row.down[0]])).size === 1;
      directional = {passed: audit.world === golden.name && audit.epoch_stable && generationStable && mismatches.length === 0,
        timeMs: audit.playback.time_ms, generationStable, checked: audit.links.length, mismatches};
    }
    const directionalRequired = room.id === 'home-a-asymmetric-link';
    const playing = samples.filter(sample => sample.phase === 'playing');
    const agreement = viewAgreement(playing);
    const viewCorrect = agreement.passed && playing.every(sample => !sample.duplicates && sample.meshCount === 6 && sample.associations.every(client => client.visible && client.label));
    const basePassed = room.load?.passed && room.initial?.passed && room.final?.passed && room.playback?.completed &&
      room.checkpoints.every(checkpoint => checkpoint.passed) && room.scriptCorrect && room.sceneCorrect && viewCorrect &&
      room.presencePhases.every(entry => entry.topologyVerified) && room.kernel?.passed && !room.errors.length &&
      !report.errors.some(error => error.room === room.id);
    return {id: room.id, passed: Boolean(basePassed) && owners.length === 0 && (!directionalRequired || directional?.passed === true) &&
      outages.every(outage => outage.samples > 0 && !outage.remainingAssociations.length && outage.meshConnected),
      directionalRequired, directional, fronthaulOutages: outages,
      loadAckMs: room.load?.acknowledgementMs, initial: room.initial, final: room.final,
      playback: room.playback, checkpoints: room.checkpoints, phases, ownerErrors: owners,
      scriptCorrect: room.scriptCorrect, sceneCorrect: room.sceneCorrect, viewCorrect,
      presencePhases: room.presencePhases, kernel: room.kernel, errors: room.errors,
      performance: {...room.performance, viewAgreement: agreement, viewMismatchSeconds: agreement.observedBadSpanSeconds,
        ...eventPerformance(events.filter(record => record.room === room.id))}};
  });
  const monitorPath = path.join(directory, '..', 'host-monitor.jsonl');
  const monitor = fs.existsSync(monitorPath) ? readJsonLines(monitorPath) : [];
  const counters = monitor.filter(row => row.package_throttle_count != null).map(row => Number(row.package_throttle_count)).filter(Number.isFinite);
  return {flavor: report.flavor, started: report.started, finished: report.finished,
    failure: report.failure, errors: report.errors, eventGaps: report.eventGaps,
    catalogCount: report.catalog?.length, tested: rooms.length, passed: rooms.filter(room => room.passed).length,
    nativeIdentitiesUnchanged: report.nativeIdentitiesUnchanged, restoration: report.restoration,
    performance: eventPerformance(events.filter(record => rooms.some(room => room.id === record.room))), rooms,
    host: {samples: monitor.length, cpuBusyPercent: distribution(monitor.map(row => row.cpu_busy_percent)),
      maximumSensorCelsius: distribution(monitor.map(row => Math.max(...Object.values(row.temperatures_celsius)))),
      minimumAvailableMemoryGiB: monitor.length ? Math.min(...monitor.map(row => row.available_memory_kib)) / 1048576 : null,
      packageThrottleDelta: counters.length ? counters.at(-1) - counters[0] : null}};
}

module.exports = {summarize};
if (require.main === module) {
  const report = summarize(process.argv[2], process.argv[3]);
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
}
