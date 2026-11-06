import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, chmod, rm, symlink, mkdir, realpath } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { ACTIONS, execute, prepare, readinessIssue, runCommand } from './core.mjs';
import { install } from './install.mjs';

async function fixture(t, { missing = [], status = {}, exit = 0 } = {}) {
  const root = await realpath(await mkdtemp(join(tmpdir(), 'wg-codegraph-test-')));
  t.after(() => rm(root, { recursive: true, force: true }));
  const cli = join(root, 'fixture-cli'), log = join(root, 'calls.jsonl');
  const source = `#!${process.execPath}
import fs from 'node:fs';
const args = process.argv.slice(2);
fs.appendFileSync(${JSON.stringify(log)}, JSON.stringify(args) + '\\n');
if (args[0] === '--version') console.log('fixture-1');
else if (args[0] === '--help') console.log(${JSON.stringify([...new Set(Object.values(ACTIONS).map(d => d.command))].filter(c => !missing.includes(c)).map(c => `  ${c} [options]`).join('\n'))});
else if (args[0] === 'status') console.log(JSON.stringify({ initialized:true, projectPath:process.cwd(), worktreeMismatch:null, pendingChanges:{added:0,modified:0,removed:0}, index:{state:'complete',reindexRecommended:false,builtWithExtractionVersion:27,currentExtractionVersion:27}, ...${JSON.stringify(status)} }));
else { console.log(JSON.stringify({argv:args,cwd:process.cwd(),marker:'fixture-ok'})); process.exitCode = ${exit}; }
`;
  // .mjs is unnecessary when Node receives a shebang script with ESM detection;
  // use an explicit .mjs name to keep fixture semantics independent of detection.
  const module = cli + '.mjs';
  await writeFile(module, source);
  await chmod(module, 0o700);
  return { root, cli: module, log, options: { cli: module, cwd: root }, calls: async () => (await readFile(log, 'utf8')).trim().split('\n').map(JSON.parse) };
}

const cases = [
  { action: 'explore', query: 'auth', max_files: 3 },
  { action: 'node', file: 'src/main.ts', symbol: 'main', offset: 2, limit: 8, symbols_only: true },
  { action: 'search', query: 'main', kind: 'function', limit: 4 },
  { action: 'files', filter: 'src', pattern: '*.ts', format: 'flat', max_depth: 0, no_metadata: true },
  { action: 'callers', symbol: 'main' },
  { action: 'callees', symbol: 'main' },
  { action: 'impact', symbol: 'main', depth: 2 },
  { action: 'affected', files: ['src/main.ts', 'space file.ts'], depth: 3, filter: '*.test.ts', quiet: true },
  { action: 'status' }, { action: 'init' }, { action: 'sync' },
  { action: 'index', force: true, quiet: true, verbose: true },
];
for (const params of cases) test(`maps ${params.action} and reaches configured CLI`, async t => {
  const f = await fixture(t), input = { ...params, project_path: f.root };
  const p = await prepare(input);
  const r = await execute(input, f.options);
  assert.equal(r.isError, false, r.content[0].text);
  assert.equal(r.details.cli_path, f.cli);
  assert.equal(r.details.cli_version, 'fixture-1');
  assert.deepEqual((await f.calls()).at(-1), p.args);
  assert.equal(r.details.project_path, f.root);
  if (params.action === 'init') assert.ok(p.args.includes('--yes'));
  if (params.action === 'node') assert.deepEqual(p.args.slice(-2), ['--', 'main']);
  if (!['init', 'sync', 'index', 'status'].includes(params.action)) assert.deepEqual((await f.calls())[2], ['status', '--json', '--', f.root]);
});

test('negative control: old CLI help can exit zero but is rejected', async t => {
  const f = await fixture(t, { missing: ['explore', 'node'] });
  const r = await execute({ action: 'explore', query: 'x', project_path: f.root }, f.options);
  assert.equal(r.isError, true);
  assert.match(r.content[0].text, /missing commands explore, node/);
  assert.deepEqual(await f.calls(), [['--version'], ['--help']]);
  const positive = await fixture(t);
  assert.equal((await execute({ action: 'explore', query: 'x', project_path: positive.root }, positive.options)).isError, false);
});

test('no PATH fallback for missing or relative configured CLI', async t => {
  const f = await fixture(t);
  for (const cli of ['codegraph', join(f.root, 'missing')]) {
    const r = await execute({ action: 'diagnose' }, { ...f.options, cli });
    assert.equal(r.isError, true);
  }
  assert.equal((await execute({ action: 'diagnose' }, f.options)).isError, false);
});

test('invalid, admin and extra-field requests are rejected before launch', async t => {
  const f = await fixture(t);
  for (const params of [
    { action: 'explore' }, { action: 'node' }, { action: 'affected', files: [] },
    { action: 'explore', query: 'x', max_files: -1 },
    { action: 'explore', query: 'x', max_files: Infinity },
    { action: 'search', query: 'x', limit: 1.2 },
    { action: 'files', format: 'garbage' },
    { action: 'init', force: true }, { action: 'index', force: 'true' },
    { action: 'explore', query: 'x', arbitrary_args: ['--force'] },
    ...['unlock', 'uninit', 'install', 'upgrade', '__proto__'].map(action => ({ action })),
  ]) {
    const r = await execute({ ...params, project_path: f.root }, f.options);
    assert.equal(r.isError, true, JSON.stringify(params));
  }
  await assert.rejects(() => readFile(f.log), /ENOENT/);
  assert.equal((await execute({ action: 'status', project_path: f.root }, f.options)).isError, false);
});

test('explicit root required and protected mutations reject aliases', async t => {
  const f = await fixture(t), homeAlias = join(f.root, 'home-alias');
  await symlink(homedir(), homeAlias);
  for (const action of ['init', 'sync', 'index']) {
    for (const project_path of ['.', '/', homedir(), homeAlias]) {
      const r = await execute({ action, project_path }, f.options);
      assert.equal(r.isError, true, `${action} ${project_path}`);
    }
  }
  await assert.rejects(() => readFile(f.log), /ENOENT/);
});

test('query and symbol option-like values stay positional without shell interpolation', async t => {
  const f = await fixture(t);
  const query = '--help; $(touch should-not-exist)';
  const r = await execute({ action: 'explore', query, project_path: f.root }, f.options);
  assert.equal(r.isError, false);
  const calls = await f.calls();
  assert.deepEqual(calls.at(-1).slice(-2), ['--', query]);
  await assert.rejects(() => readFile(join(f.root, 'should-not-exist')), /ENOENT/);
});

for (const status of [
  { initialized: false }, { projectPath: '/other' }, { worktreeMismatch: {} },
  { worktreeMismatch: undefined }, { pendingChanges: { added: 0, modified: 1, removed: 0 } },
  { pendingChanges: {} }, { index: { state: 'complete', reindexRecommended: true } },
  { index: { state: 'complete', reindexRecommended: false, builtWithExtractionVersion: 26, currentExtractionVersion: 27 } },
]) test(`readiness blocks without refresh: ${JSON.stringify(status)}`, async t => {
  // JSON cannot encode undefined: test the missing field directly as well below.
  const f = await fixture(t, { status });
  if (Object.hasOwn(status, 'worktreeMismatch') && status.worktreeMismatch === undefined) {
    assert.match(readinessIssue({ projectPath: f.root, initialized: true, index: { state: 'complete' } }, f.root), /unknown readiness/);
    return;
  }
  const r = await execute({ action: 'explore', query: 'x', project_path: f.root }, f.options);
  assert.equal(r.isError, true);
  assert.equal(r.details.phase, 'readiness');
  assert.ok((await f.calls()).every(a => !['explore', 'sync', 'index', 'init'].includes(a[0])));
});

test('nonzero exit propagates tool error, with full stdout and stderr artifact', async t => {
  const f = await fixture(t, { exit: 7 });
  const r = await execute({ action: 'explore', query: 'x', project_path: f.root }, f.options);
  assert.equal(r.isError, true);
  assert.equal(r.details.exit_code, 7);
  assert.match(await readFile(r.details.output_path, 'utf8'), /fixture-ok/);
});

test('runner bounds long output and directly preserves exact destination bytes', async t => {
  const f = await fixture(t), text = '\u001b[31m' + '中'.repeat(30000) + '\u001b[0m\n' + 'line\n'.repeat(3000);
  const producer = join(f.root, 'producer.mjs');
  await writeFile(producer, `process.stdout.write(${JSON.stringify(text)}); process.stderr.write('stderr-sentinel');`);
  const r = await runCommand(process.execPath, [producer], { cwd: f.root });
  assert.equal(r.isError, false);
  assert.equal(r.details.truncated, true);
  assert.ok(Buffer.byteLength(r.content[0].text) < 52 * 1024);
  assert.ok(!r.content[0].text.includes('\u001b'));
  // Independent pipes do not guarantee cross-stream order. Verify both streams'
  // exact bytes without inventing a stdout-before-stderr ordering contract.
  const captured = await readFile(r.details.output_path, 'utf8');
  assert.equal(captured.split('stderr-sentinel').length, 2);
  assert.equal(captured.replace('stderr-sentinel', ''), text);
  assert.equal(r.details.total_bytes, Buffer.byteLength(text + 'stderr-sentinel'));
  assert.equal(await readFile(r.details.stdout_path, 'utf8'), text);
  assert.equal(await readFile(r.details.stderr_path, 'utf8'), 'stderr-sentinel');
  t.after(() => rm(r.details.output_path, { force: true }));
});

test('runner enforces line limit even when output is small', async t => {
  const f = await fixture(t);
  const r = await runCommand(process.execPath, ['-e', 'console.log("x\\n".repeat(2500))'], { cwd: f.root });
  assert.equal(r.details.truncated, true);
  assert.ok(r.content[0].text.split('\n').length <= 2002);
  assert.ok((await readFile(r.details.output_path, 'utf8')).split('\n').length > 2500);
});

test('cancellation and timeout are errors and terminate a SIGTERM-resistant process', async t => {
  const f = await fixture(t), script = 'process.on("SIGTERM",()=>{});setInterval(()=>{},1000)';
  const controller = new AbortController();
  const promise = runCommand(process.execPath, ['-e', script], { cwd: f.root, signal: controller.signal, killAfterMs: 100 });
  const timer = setTimeout(() => controller.abort(), 200);
  const r = await promise;
  clearTimeout(timer);
  assert.equal(r.isError, true);
  assert.equal(r.details.cancelled, true);
  const timed = await runCommand(process.execPath, ['-e', script], { cwd: f.root, timeoutMs: 200, killAfterMs: 100 });
  assert.equal(timed.isError, true);
  assert.equal(timed.details.timed_out, true);
  assert.equal((await runCommand(f.cli, [], { signal: AbortSignal.abort() })).isError, true);
});

test('cancellation kills a resistant attached descendant even if its parent exits first', async t => {
  const f = await fixture(t), ready = join(f.root, 'child.pid');
  const parent = join(f.root, 'parent.mjs'), controller = new AbortController();
  const childCode = `require('fs').writeFileSync(${JSON.stringify(ready)}, String(process.pid));process.on('SIGTERM',()=>{});setInterval(()=>{},1000);`;
  await writeFile(parent, `import {spawn} from 'node:child_process';spawn(process.execPath,['-e',${JSON.stringify(childCode)}],{stdio:'ignore'});setInterval(()=>{},1000);`);
  const run = runCommand(process.execPath, [parent], { cwd: f.root, signal: controller.signal, killAfterMs: 100 });
  let pid;
  try {
    for (let i = 0; i < 100 && !pid; i++) {
      pid = Number(await readFile(ready, 'utf8').catch(() => '')) || undefined;
      if (!pid) await new Promise(r => setTimeout(r, 20));
    }
    assert.ok(pid, 'child must be alive as the positive liveness control');
    process.kill(pid, 0);
    controller.abort();
    assert.equal((await run).isError, true);
    let alive = true;
    for (let i = 0; i < 100 && alive; i++) {
      try { process.kill(pid, 0); } catch (error) { if (error.code === 'ESRCH') alive = false; else throw error; }
      if (alive) await new Promise(r => setTimeout(r, 20));
    }
    assert.equal(alive, false, 'attached child must actually terminate');
  } finally {
    controller.abort();
    await run;
    if (pid) try { process.kill(pid, 'SIGKILL'); } catch {}
  }
});

test('help and diagnose reject action-inapplicable fields', async t => {
  const f = await fixture(t);
  for (const action of ['help', 'diagnose']) {
    assert.equal((await execute({ action, force: true }, f.options)).isError, true);
  }
  await assert.rejects(() => readFile(f.log), /ENOENT/);
  assert.equal((await execute({ action: 'help' }, f.options)).isError, false);
});

test('spawn failures settle instead of throwing or pretending success', async t => {
  const f = await fixture(t);
  const r = await runCommand(join(f.root, 'absent'), [], { cwd: f.root });
  assert.equal(r.isError, true);
  assert.match(r.content[0].text, /launch failed/);
});

test('installer copies independent runtime, reads back hashes, and refuses unrelated targets', async t => {
  const f = await fixture(t), destination = join(f.root, 'installed');
  const r = await install({ cli: f.cli, destination });
  assert.equal(r.cli_path, f.cli);
  assert.deepEqual(JSON.parse(await readFile(join(destination, 'config.json'), 'utf8')), { cli: f.cli });
  assert.equal(JSON.parse(await readFile(join(destination, 'package.json'), 'utf8')).pi.extensions[0], './index.ts');
  const updated = await install({ cli: f.cli, destination });
  assert.ok(updated.backup);
  assert.equal(await readFile(join(updated.backup, 'core.mjs'), 'utf8'), await readFile(join(destination, 'core.mjs'), 'utf8'));
  const unrelated = join(f.root, 'unrelated');
  await mkdir(unrelated);
  await writeFile(join(unrelated, 'keep'), 'untouched');
  await assert.rejects(() => install({ cli: f.cli, destination: unrelated }), /lacks.*marker/);
  assert.equal(await readFile(join(unrelated, 'keep'), 'utf8'), 'untouched');
  const alias = join(f.root, 'alias');
  await symlink(destination, alias);
  await assert.rejects(() => install({ cli: f.cli, destination: alias }), /symlink/);
  await assert.rejects(() => install({ cli: 'codegraph', destination: join(f.root, 'bad') }), /absolute CLI/);
  await assert.rejects(() => install({ cli: f.cli, destination: homedir() }), /Unsafe/);
});
