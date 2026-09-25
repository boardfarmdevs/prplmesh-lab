import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const root = fileURLToPath(new URL('../', import.meta.url));
const repository = path.resolve(root, '..');
const output = path.join(root, 'site');
const worlds = path.join(repository, 'wmediumd/configurator/worlds');
const viewer = readFileSync(path.join(worlds, 'viewer/index.html'), 'utf8');
if (!viewer.includes('<meta name="room-viewer-mode" content="no-connect">')) {
  throw new Error('Public viewer must default to disconnected mode');
}
for (const asset of ['dist/index.html', 'dist/licenses.md']) {
  if (!existsSync(path.join(root, asset)))
    throw new Error(`Build the explorer first: missing ${asset}`);
}
rmSync(output, { recursive: true, force: true });
mkdirSync(output, { recursive: true });
cpSync(path.join(root, 'dist'), path.join(output, 'explorer'), {
  recursive: true,
});
cpSync(path.join(root, 'pages-index.html'), path.join(output, 'index.html'));
for (const name of ['viewer', 'golden']) {
  cpSync(path.join(worlds, name), path.join(output, name), {
    recursive: true,
    filter: (filename) =>
      !filename.includes('__pycache__') && !filename.endsWith('.pyc'),
  });
}
const rooms = readdirSync(path.join(output, 'golden'))
  .filter((name) => name.endsWith('.world.json'))
  .sort();
const publicViewer = viewer.replace(
  '<title>wmediumd world viewer</title>',
  '<title>prplMesh — Room sandbox</title>',
);
writeFileSync(path.join(output, 'viewer/index.html'), publicViewer);
writeFileSync(path.join(output, '.nojekyll'), '');
writeFileSync(
  path.join(output, 'build.json'),
  JSON.stringify(
    {
      repository: 'boardfarmdevs/prplmesh-lab',
      revision: execFileSync('git', ['rev-parse', 'HEAD'], {
        cwd: repository,
        encoding: 'utf8',
      }).trim(),
      workingTreeDirty: Boolean(
        execFileSync('git', ['status', '--porcelain'], {
          cwd: repository,
          encoding: 'utf8',
        }).trim(),
      ),
      mode: 'disconnected',
      rooms,
    },
    null,
    2,
  ) + '\n',
);
console.log(
  `Built ${output}: explorer, manual and ${rooms.length} room previews; no live backend`,
);
