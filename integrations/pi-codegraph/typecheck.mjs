#!/usr/bin/env node
// Typecheck against explicitly selected installed host peers, without installing
// duplicate Pi/typebox runtimes or committing machine-specific tsconfig paths.
import { spawnSync } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i]] = process.argv[i + 1];
if (![args['--sdk-root'], args['--tsc']].every(p => typeof p === 'string' && isAbsolute(p))) {
  throw new Error('Usage: node typecheck.mjs --sdk-root /installed/pi/package --tsc /installed/typescript/tsc.js');
}
const root = args['--sdk-root'], temporary = await mkdtemp(join(tmpdir(), 'wg-codegraph-types-'));
try {
  const config = join(temporary, 'tsconfig.json');
  await writeFile(config, JSON.stringify({ compilerOptions: {
    target: 'ES2023', module: 'NodeNext', moduleResolution: 'NodeNext', strict: true,
    noEmit: true, skipLibCheck: true, types: ['node'],
    typeRoots: [join(root, 'node_modules/@types')],
    paths: {
      '@earendil-works/pi-coding-agent': [join(root, 'dist/index.d.ts')],
      typebox: [join(root, 'node_modules/typebox/build/index.d.mts')],
    },
  }, files: [join(dirname(fileURLToPath(import.meta.url)), 'index.ts')] }));
  const result = spawnSync(process.execPath, [args['--tsc'], '--project', config], { stdio: 'inherit' });
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally { await rm(temporary, { recursive: true, force: true }); }
