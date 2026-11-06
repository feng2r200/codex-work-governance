#!/usr/bin/env node
// Explicit local delivery only; never installs CodeGraph or changes Pi settings.
import { createHash } from 'node:crypto';
import { lstat, mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { inspectCli } from './core.mjs';

const SOURCE = dirname(fileURLToPath(import.meta.url));
const NAME = '@work-governance/pi-codegraph-local';
const RUNTIME_FILES = ['package.json', 'index.ts', 'core.mjs', 'core.d.mts'];

export async function install({ cli, destination }) {
  if (!destination || !isAbsolute(destination)) throw new Error('An explicit absolute --dest is required.');
  const target = resolve(destination);
  if (target === '/' || target === homedir() || target === SOURCE || SOURCE.startsWith(target + '/')) throw new Error('Unsafe installation destination.');
  const identity = await inspectCli(cli, { cwd: SOURCE });
  let existing = false;
  try {
    const st = await lstat(target);
    if (st.isSymbolicLink() || !st.isDirectory()) throw new Error('Destination must not be a symlink or non-directory.');
    const manifest = JSON.parse(await readFile(join(target, 'package.json'), 'utf8'));
    if (manifest.name !== NAME) throw new Error('Refusing to replace an unrelated directory.');
    existing = true;
  } catch (error) { if (error.code !== 'ENOENT') throw error; else if (await lstat(target).catch(() => null)) throw new Error('Existing destination lacks an adapter package marker.'); }
  await mkdir(dirname(target), { recursive: true });
  const staging = await mkdtemp(target + '.stage-');
  const hashes = {};
  let backup;
  try {
    for (const name of RUNTIME_FILES) {
      const bytes = await readFile(join(SOURCE, name));
      await writeFile(join(staging, name), bytes, { mode: 0o600 });
      hashes[name] = createHash('sha256').update(bytes).digest('hex');
    }
    const config = JSON.stringify({ cli }, null, 2) + '\n';
    await writeFile(join(staging, 'config.json'), config, { mode: 0o600 });
    hashes['config.json'] = createHash('sha256').update(config).digest('hex');
    await writeFile(join(staging, 'installation.json'), JSON.stringify({
      installed_at: new Date().toISOString(), source: SOURCE, identity, sha256: hashes,
    }, null, 2) + '\n', { mode: 0o600 });
    if (existing) {
      backup = target + '.backup-' + Date.now();
      await rename(target, backup);
    }
    try { await rename(staging, target); }
    catch (error) { if (backup) await rename(backup, target); throw error; }
    // Direct destination readback, not just a successful copy receipt.
    for (const [name, expected] of Object.entries(hashes)) {
      const actual = createHash('sha256').update(await readFile(join(target, name))).digest('hex');
      if (actual !== expected) throw new Error(`Installed bytes mismatch: ${name}`);
    }
    return { destination: target, backup: backup ?? null, ...identity, sha256: hashes,
      next: `pi install ${JSON.stringify(target)}; after validation remove the old npm bridge` };
  } finally { await rm(staging, { recursive: true, force: true }); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const args = process.argv.slice(2), options = {};
    for (let i = 0; i < args.length; i += 2) {
      if (!['--cli', '--dest'].includes(args[i]) || !args[i + 1]) throw new Error('Usage: node install.mjs --cli /absolute/codegraph --dest /absolute/install-directory');
      if (options[args[i]]) throw new Error(`Duplicate option: ${args[i]}`);
      options[args[i]] = args[i + 1];
    }
    console.log(JSON.stringify(await install({ cli: options['--cli'], destination: options['--dest'] }), null, 2));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
