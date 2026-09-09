#!/usr/bin/env node

'use strict';

const assert = require('assert').strict;
const path = require('path');

global.document = { addEventListener() {}, getElementById() { return null; } };
global.window = { addEventListener() {} };

const Controller = require(path.resolve(__dirname, '../web/static/script.js'));
const controller = new Controller();
const nodes = [
  { id: 'controller', name: 'Controller', haulTypes: [], STAList: [] },
  { id: 'agent-1', name: 'Agent-1', haulTypes: [], STAList: [] },
  ...[1, 2, 3, 4].map(index => ({
    id: `extender-${index}`, name: `Extender-${index}`, haulTypes: [], STAList: []
  }))
];

const colocatedStar = [
  { from: 'controller', to: 'agent-1' },
  ...[1, 2, 3, 4].map(index => ({ from: 'agent-1', to: `extender-${index}` }))
];
const positions = controller.topologyLandscapeLayout(nodes, colocatedStar, 1600, 900);
const controllerPosition = positions.get('controller');
assert.ok(controllerPosition, 'Controller is missing from the hierarchy');
const gatewayPosition = positions.get('agent-1');
const satellites = nodes.slice(2).map(node => positions.get(node.id));
assert.ok(satellites.some(position => position.x < gatewayPosition.x));
assert.ok(satellites.some(position => position.x > gatewayPosition.x));
assert.ok(satellites.some(position => position.y < gatewayPosition.y));
assert.ok(satellites.some(position => position.y > gatewayPosition.y));
assert.equal(new Set(nodes.slice(1).map(node => {
  const position = positions.get(node.id);
  return `${position.x.toFixed(3)},${position.y.toFixed(3)}`;
})).size, nodes.length - 1);

const branch = [
  { from: 'controller', to: 'agent-1' },
  { from: 'agent-1', to: 'extender-1' },
  { from: 'agent-1', to: 'extender-2' },
  { from: 'extender-2', to: 'extender-3' },
  { from: 'extender-2', to: 'extender-4' }
];
const branchPositions = controller.topologyLandscapeLayout(nodes, branch, 1600, 900);
assert.notDeepEqual(branchPositions.get('controller'), { x: 0, y: 0 },
  'a multihop branch was incorrectly classified as a star');

assert.equal(controller.topologySignalLevel({ available: true, rssi: -41 }), 10);
assert.equal(controller.topologySignalLevel({ available: true, rssi: -50 }), 9);
assert.equal(controller.topologySignalLevel({ available: true, rssi: -56 }), 7);
assert.equal(controller.topologySignalLevel({ available: true, rssi: -63 }), 6);
assert.equal(controller.topologySignalLevel({ available: true, rssi: -72 }), 4);
assert.equal(controller.topologySignalLevel({ available: true, rssi: -82 }), 2);
assert.equal(controller.topologySignalLevel({ available: true, rssi: -90 }), 1);
assert.equal(controller.topologySignalLevel({ available: false, rssi: null }), 0);

const meterRight = controller.topologySignalMeterGeometry({
  from: { x: 0, y: 20 }, to: { x: 10, y: 20 }, iconSize: 30
}, 9);
const meterLeft = controller.topologySignalMeterGeometry({
  from: { x: 20, y: 20 }, to: { x: 10, y: 20 }, iconSize: 30
}, 9);
assert.equal(meterRight.side, 1,
  'signal meter was not placed away from a left-side RF line');
assert.equal(meterLeft.side, -1,
  'signal meter was not placed away from a right-side RF line');
assert.ok(meterRight.x > 25 && meterLeft.x + meterLeft.width < -5,
  'signal meter overlaps the client icon');
const meterBottom = controller.topologySignalMeterGeometry({
  from: { x: 0, y: 20 }, to: { x: 10, y: 20 }, iconSize: 30
}, 0);
assert.ok(Math.abs((meterBottom.y + meterBottom.height) - 35) < 0.001,
  'signal meter does not span the complete client icon height');

console.log('PASS: topology layout and ten-segment client signal meters are deterministic');
