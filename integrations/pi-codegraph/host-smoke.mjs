#!/usr/bin/env node
// Explicit local integration test: real Pi loader + nested tool pipeline + real CLI.
// No model prompt, provider request or mutation outside the disposable fixture.
import assert from 'node:assert/strict';
import { mkdtemp, readFile, realpath, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const options = {};
for (let i = 2; i < process.argv.length; i += 2) options[process.argv[i]] = process.argv[i + 1];
assert.ok(options['--sdk'] && options['--adapter'], 'Usage: node host-smoke.mjs --sdk /absolute/pi/dist/index.js --adapter /absolute/installed-directory [--agent-dir /actual/agent]');
const sdk = await import(pathToFileURL(resolve(options['--sdk'])).href);
const temporary = await realpath(await mkdtemp(join(tmpdir(), 'wg-codegraph-live-')));
const project = join(temporary, 'project');
const { mkdir } = await import('node:fs/promises');
await mkdir(project);
await writeFile(join(project, 'package.json'), '{"type":"module"}\n');
await writeFile(join(project, 'source.js'), `export function wgLeaf731() { return 'WG_LOCAL_PROBE_731'; }\nexport function wgMain731() { return wgLeaf731(); }\n`);
await writeFile(join(project, 'source.test.js'), `import { wgMain731 } from './source.js';\nexport function wgTest731() { return wgMain731(); }\n`);
const receipts = [], nestedEvents = [];
let session;
try {
  const actualAgent = options['--agent-dir'];
  const agentDir = actualAgent ? resolve(actualAgent) : join(temporary, 'agent');
  const settingsManager = actualAgent ? sdk.SettingsManager.create(project, agentDir)
    : sdk.SettingsManager.inMemory({ packages: [], extensions: [] });
  const resourceLoader = new sdk.DefaultResourceLoader({
    cwd: project, agentDir, settingsManager,
    noExtensions: !actualAgent,
    additionalExtensionPaths: actualAgent ? [] : [join(resolve(options['--adapter']), 'index.ts')],
    noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    extensionFactories: [pi => pi.registerTool({
      name: 'adapter_smoke_driver', label: 'Adapter smoke driver', description: 'Test-only nested tool caller',
      parameters: { type: 'object', properties: { request: { type: 'object', additionalProperties: true } }, required: ['request'] },
      async execute(_id, { request }, signal, _update, ctx) {
        const outcome = await ctx.executeTool('codegraph', request, { signal });
        return { ...outcome.result, isError: outcome.isError };
      },
    })],
  });
  await resourceLoader.reload();
  assert.deepEqual(resourceLoader.getExtensions().errors, [], 'real extension loader must have no errors');
  // Nested calls require an assistant parent. Seed an explicit synthetic fixture
  // through the authoritative SessionManager, not by mutating agent messages.
  // This tests host execution/validation, not model selection or reasoning.
  const sessionManager = sdk.SessionManager.inMemory();
  sessionManager.appendMessage({ role: 'assistant',
    content: [{ type: 'toolCall', id: 'local-smoke-parent', name: 'adapter_smoke_driver', arguments: {} }],
    api: 'openai-responses', provider: 'fixture', model: 'no-model-invoked',
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    stopReason: 'toolUse', timestamp: Date.now(),
  });
  ({ session } = await sdk.createAgentSession({ cwd: project, agentDir, settingsManager,
    resourceLoader, sessionManager, tools: ['codegraph', 'adapter_smoke_driver'] }));
  const registered = session.getAllTools().filter(t => t.name === 'codegraph');
  assert.equal(registered.length, 1, 'exactly one CodeGraph tool must be registered');
  assert.ok(registered[0].sourceInfo.path.startsWith(resolve(options['--adapter'])), JSON.stringify(registered));
  session.subscribe(e => { if (e.type === 'tool_execution_end' && e.toolName === 'codegraph') nestedEvents.push(e); });
  const driver = session.agent.state.tools.find(t => t.name === 'adapter_smoke_driver');
  assert.ok(driver, 'real session must wrap the driver');
  async function call(request, expectedError = false) {
    const r = await driver.execute('local-smoke-parent', { request }, new AbortController().signal);
    assert.equal(!!r.isError, expectedError, `${request.action}: ${r.content.map(c => c.text ?? '').join('\n')}`);
    receipts.push({ action: request.action, isError: !!r.isError, details: r.details });
    return r;
  }
  const config = JSON.parse(await readFile(join(resolve(options['--adapter']), 'config.json'), 'utf8'));
  const diagnostic = await call({ action: 'diagnose' });
  assert.equal(diagnostic.details.cli_path, config.cli);
  assert.ok(diagnostic.details.commands.includes('explore'));
  await call({ action: 'help' });
  await call({ action: 'explore', query: 'wgLeaf731' }, true); // missing explicit root
  await call({ action: 'unlock', project_path: project }, true); // real schema/pipeline rejection
  const request = (action, fields = {}) => ({ action, project_path: project, ...fields });
  await call(request('init'));
  const status = await call(request('status'));
  const state = JSON.parse(status.content[0].text);
  assert.equal(state.initialized, true);
  assert.ok(state.nodeCount > 0 && state.dbSizeBytes > 0);
  assert.ok((await stat(state.indexPath)).isDirectory(), 'actual index must exist at destination');
  const explore = await call(request('explore', { query: 'wgLeaf731 wgMain731', max_files: 3 }));
  assert.match(explore.content[0].text, /WG_LOCAL_PROBE_731/);
  const node = await call(request('node', { file: 'source.js', offset: 1, limit: 2 }));
  assert.match(node.content[0].text, /WG_LOCAL_PROBE_731/);
  assert.match(node.content[0].text, /wgMain731/);
  await call(request('node', { symbol: 'wgLeaf731', file: 'source.js' }));
  const search = await call(request('search', { query: 'wgLeaf731', kind: 'function', limit: 4 }));
  assert.match(search.content[0].text, /wgLeaf731/);
  const files = await call(request('files', { pattern: '*.js', format: 'flat', max_depth: 0, no_metadata: true }));
  assert.match(files.content[0].text, /source\.js/);
  const callers = await call(request('callers', { symbol: 'wgLeaf731' }));
  assert.match(callers.content[0].text, /wgMain731/);
  const callees = await call(request('callees', { symbol: 'wgMain731' }));
  assert.match(callees.content[0].text, /wgLeaf731/);
  await call(request('impact', { symbol: 'wgLeaf731', depth: 2 }));
  const affected = await call(request('affected', { files: ['source.js'], depth: 3 }));
  assert.match(affected.content[0].text, /source\.test\.js/);
  await writeFile(join(project, 'source.js'), `export function wgLeaf731() { return 'WG_LOCAL_UPDATED_731'; }\nexport function wgMain731() { return wgLeaf731(); }\n`);
  await call(request('explore', { query: 'wgLeaf731' }), true); // freshness refusal, never auto-sync
  await call(request('sync'));
  const changed = await call(request('node', { file: 'source.js' }));
  assert.match(changed.content[0].text, /WG_LOCAL_UPDATED_731/);
  await call(request('index', { quiet: true }));
  await call(request('status'));
  assert.ok(nestedEvents.some(e => e.isError), 'host must observe actual errors');
  assert.ok(nestedEvents.some(e => !e.isError), 'same host pipeline must observe successes');
  console.log(JSON.stringify({ observed_at: new Date().toISOString(), passed: true,
    host: 'real Pi SDK loader and ctx.executeTool pipeline; no model prompt',
    registered, nested_event_count: nestedEvents.length, receipts,
    artifact_readback: ['real CodeGraph index', 'explore sentinel source', 'node changed source', 'call paths', 'affected test path'],
  }, null, 2));
} finally {
  session?.dispose();
  await rm(temporary, { recursive: true, force: true });
}
