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
assert.ok(nodes.slice(1).every(node =>
  positions.get(node.id).x > controllerPosition.x),
  'a star satellite was not placed after the Controller');
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

console.log('PASS: star and branch topologies use the same space-efficient Controller-first hierarchy');
