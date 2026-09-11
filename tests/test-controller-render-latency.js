'use strict';
const assert = require('node:assert/strict');
const vm = require('node:vm');
const {installObserver} = require('./controller-render-latency.js');

async function main() {
  let now = 0;
  let bssid = 'first';
  let rendered = 'first';
  const frames = [];
  const controller = {apiCall: async () => ({nodes: [{STAList: bssid ? [{staMAC: 'client', bssid}] : []}]})};
  const environment = {window: {EasyMeshController: controller},
    performance: {now: () => now}, requestAnimationFrame: callback => frames.push(callback),
    document: {querySelectorAll: () => rendered ? [{__data__: {sta: {staMAC: 'client', bssid: rendered}}}] : []}};
  vm.runInNewContext('(' + installObserver.toString() + ')()', environment);
  const sample = () => environment.window.__controllerRenderLatency();
  const frame = () => { now += 16; frames.splice(0).forEach(callback => callback()); };
  await controller.apiCall('/topology');
  assert.equal(sample().records.length, 0);
  bssid = 'second';
  await controller.apiCall('/topology');
  frame();
  assert.equal(sample().records.length, 0);
  rendered = 'second';
  frame();
  assert.equal(sample().records.length, 0);
  frame();
  assert.equal(sample().records[0].decodedResponseToSvgIdentityMs, 48);
  assert.equal(sample().records[0].passed, true);
  bssid = null;
  await controller.apiCall('/topology');
  rendered = null;
  frame(); frame();
  assert.equal(sample().records[1].to, null);
  assert.equal(sample().records[1].passed, true);
  bssid = 'third';
  await controller.apiCall('/topology');
  bssid = 'fourth';
  await controller.apiCall('/topology');
  assert.equal(sample().records[2].superseded, true);
  now += 5001;
  frame();
  assert.equal(sample().records[3].timeout, true);
  assert.equal(sample().pending.length, 0);
  assert.equal(sample().responses, 5);
  console.log('PASS: render timing waits for two matching frames, tracks removals, supersession and timeouts');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
