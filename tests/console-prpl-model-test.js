'use strict';
const assert = require('node:assert/strict');

async function main() {
  const {MediumModel, nativeLoadValue} = await import('../wmediumd/observer/web/ng/model.mjs');
  const now = Date.now(), timestamp = new Date(now).toISOString();
  const mac = ordinal => `42:00:00:00:${ordinal.toString(16).padStart(2, '0')}:00`;
  const radios = [], roles = [];
  for (let node = 0; node < 5; node++) {
    const container = node === 0 ? 'prpl-controller' : `prpl-agent-0${node}`;
    const bandRadios = {};
    for (const [offset, band] of ['2.4', '5', '6'].entries()) {
      const identity = mac(node * 3 + offset);
      radios.push({mac: identity, owner: container, role: node === 0 ? 'controller-agent' : 'extender'});
      bandRadios[band] = {tx_mac: identity};
    }
    roles.push({container, band_radios: bandRadios, present: true, position: [node, 1]});
  }
  for (let client = 0; client < 100; client++) {
    const identity = mac(15 + client), container = `prpl-client-${String(client + 1).padStart(2, '0')}`;
    radios.push({mac: identity, owner: container, role: client % 2 ? 'iot-client' : 'wlan-client'});
    roles.push({radio: identity, container, present: client < 20, position: [client, 2]});
  }
  for (let spare = 115; spare < 120; spare++) radios.push({mac: mac(spare), role: 'spare'});
  const model = new MediumModel();
  model.update({daemon: {instance_id: 'prpl'}, captured_at: timestamp, radios,
    room: {available: true, observed_at: timestamp, data: {instance_id: 'prpl', live: true, roles}}});
  const result = model.explore({}, now);
  assert.deepEqual(result.pool, {bound: 100, present: 20, excluded: 80, unknown: 0});
  for (const offset of [0, 1, 2]) assert.deepEqual(result.radios.find(radio => radio.mac === mac(3 + offset)).position, [1, 1]);
  assert.equal(result.radios.find(radio => radio.mac === mac(119)).presence, 'unknown');
  const record = {source: 'native_ap_metrics', transport: 'prpl-local-broker',
    observed_at: timestamp, utilization: 0, station_count: 0};
  assert.deepEqual(nativeLoadValue(record, {enabled: true, maximum_age_seconds: 5}, true, now),
    {valid: true, utilization: 0, station_count: 0});
  console.log('PASS: prpl tri-band identity, 120 radios, 100 clients, 20 online, 80 excluded, spare and native broker provenance');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
