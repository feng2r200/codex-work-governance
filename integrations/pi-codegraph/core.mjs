// Optional host adapter. No imports from a plugin cache, SDK or package manager.
import { spawn } from 'node:child_process';
import { access, mkdtemp, realpath, stat } from 'node:fs/promises';
import { closeSync, constants, openSync, writeSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { isAbsolute, join, parse } from 'node:path';
import { stripVTControlCharacters } from 'node:util';
import { StringDecoder } from 'node:string_decoder';

export const ACTIONS = Object.freeze({
  explore: { command: 'explore', required: ['query'], fields: ['max_files'] },
  node: { command: 'node', fields: ['file', 'symbol', 'offset', 'limit', 'symbols_only'] },
  search: { command: 'query', required: ['query'], fields: ['kind', 'limit'] },
  files: { command: 'files', fields: ['filter', 'pattern', 'format', 'max_depth', 'no_metadata'] },
  callers: { command: 'callers', required: ['symbol'], fields: [] },
  callees: { command: 'callees', required: ['symbol'], fields: [] },
  impact: { command: 'impact', required: ['symbol'], fields: ['depth'] },
  affected: { command: 'affected', required: ['files'], fields: ['depth', 'filter', 'quiet'] },
  status: { command: 'status', fields: [] },
  init: { command: 'init', fields: [] },
  sync: { command: 'sync', fields: [] },
  index: { command: 'index', fields: ['force', 'quiet', 'verbose'] },
});
const MUTATIONS = new Set(['init', 'sync', 'index']);
const QUERIES = new Set(Object.keys(ACTIONS).filter(a => !MUTATIONS.has(a) && a !== 'status'));
const NUMBERS = { max_files: 1, offset: 1, limit: 1, max_depth: 0, depth: 1 };
const FLAGS = { max_files: '--max-files', offset: '--offset', limit: '--limit',
  kind: '--kind', filter: '--filter', pattern: '--pattern', format: '--format',
  max_depth: '--max-depth', depth: '--depth' };
const BOOLEANS = { symbols_only: '--symbols-only', no_metadata: '--no-metadata',
  quiet: '--quiet', verbose: '--verbose', force: '--force' };
export const HELP = `Local CodeGraph adapter (explicit configured CLI, no PATH fallback).
Actions requiring absolute project_path:
${Object.entries(ACTIONS).map(([a, d]) => `  ${a}: ${[...(d.required ?? []), ...(d.fields ?? [])].join(', ') || '(no extra fields)'}`).join('\n')}
node requires file or symbol; both disambiguate a symbol by file.
help: this reference. diagnose: configured CLI path, version and command capabilities.
Queries reject unknown/stale index readiness; no automatic refresh is performed.
init/sync/index change only derived index state and require task authority.
Admin, package management, force-init, unlock and destructive actions are excluded.
Use the code-intelligence Skill for applicability, authority and safe checkout selection.`;

function failure(message, details = {}) {
  return { content: [{ type: 'text', text: message }], details, isError: true };
}

/** Bounded memory, full private output file, no shell, cancellation of process group. */
export async function runCommand(cli, args, { cwd, signal, timeoutMs = 0,
  maxBytes = 50 * 1024, maxLines = 2000, killAfterMs = 5000 } = {}) {
  if (signal?.aborted) return failure('CodeGraph cancelled before launch.', { cancelled: true, exit_code: -1 });
  const dir = await mkdtemp(join(tmpdir(), 'wg-codegraph-'));
  const outputPath = join(dir, 'output.txt');
  const fd = openSync(outputPath, 'wx', 0o600);
  const stdoutPath = join(dir, 'stdout.txt'), stderrPath = join(dir, 'stderr.txt');
  const stdoutFd = openSync(stdoutPath, 'wx', 0o600), stderrFd = openSync(stderrPath, 'wx', 0o600);
  return new Promise(resolve => {
    let head = Buffer.alloc(0), bytes = 0, cancelled = false, timedOut = false;
    let spawnError, ioError, killTimer, timeout;
    const grouped = process.platform !== 'win32';
    const child = spawn(cli, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], detached: grouped });
    function kill(sig) {
      try { if (grouped && child.pid) process.kill(-child.pid, sig); else child.kill(sig); }
      catch (error) { if (error.code !== 'ESRCH') spawnError ??= error; }
    }
    function terminate() {
      kill('SIGTERM');
      killTimer ??= setTimeout(() => kill('SIGKILL'), killAfterMs);
      killTimer.unref();
    }
    const abort = () => { cancelled = true; terminate(); };
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) abort();
    if (timeoutMs) timeout = setTimeout(() => { timedOut = true; terminate(); }, timeoutMs);
    function combined(text) {
      const chunk = Buffer.from(text);
      try { writeSync(fd, chunk); }
      catch (error) { ioError ??= error; terminate(); }
      const available = Math.max(0, maxBytes - head.length);
      if (available) head = Buffer.concat([head, chunk.subarray(0, available)]);
    }
    function capture(stream, streamFd) {
      const decoder = new StringDecoder('utf8');
      stream.on('data', chunk => {
        try { writeSync(streamFd, chunk); }
        catch (error) { ioError ??= error; terminate(); }
        bytes += chunk.length;
        combined(decoder.write(chunk));
      });
      stream.on('end', () => combined(decoder.end()));
    }
    // Pipes may interleave at byte boundaries. Decode independently for the
    // human-readable combined artifact; keep each original stream losslessly.
    capture(child.stdout, stdoutFd);
    capture(child.stderr, stderrFd);
    child.on('error', error => { spawnError = error; });
    child.on('close', (code, exitSignal) => {
      // A parent can exit on SIGTERM while a resistant descendant closes its
      // stdio and survives. Finish cancellation for the whole attached group.
      if (cancelled || timedOut || ioError) kill('SIGKILL');
      clearTimeout(timeout);
      clearTimeout(killTimer);
      signal?.removeEventListener('abort', abort);
      closeSync(fd);
      closeSync(stdoutFd);
      closeSync(stderrFd);
      const allHead = stripVTControlCharacters(head.toString('utf8'));
      const lines = allHead.split('\n');
      const truncated = bytes > head.length || lines.length > maxLines;
      let text = lines.slice(0, maxLines).join('\n');
      if (spawnError) text = `CodeGraph launch failed: ${spawnError.message}\n${text}`;
      if (ioError) text = `CodeGraph output capture failed: ${ioError.message}\n${text}`;
      if (cancelled) text = `CodeGraph cancelled.\n${text}`;
      if (timedOut) text = `CodeGraph timed out.\n${text}`;
      if (truncated) text += `\n[output truncated; full output: ${outputPath}]`;
      resolve({ content: [{ type: 'text', text: text || `(CodeGraph exited ${code ?? exitSignal})` }],
        details: { cli_path: cli, args, exit_code: code ?? -1, signal: exitSignal,
          cancelled, timed_out: timedOut, truncated, total_bytes: bytes, output_path: outputPath,
          stdout_path: stdoutPath, stderr_path: stderrPath },
        isError: code !== 0 || !!spawnError || !!ioError || cancelled || timedOut });
    });
  });
}

/** Inspect the actual configured executable, not a semantic version guess. */
export async function inspectCli(cli, options = {}) {
  if (typeof cli !== 'string' || !isAbsolute(cli)) throw new Error('Configure an absolute CLI path; PATH lookup is forbidden.');
  await access(cli, constants.X_OK);
  const version = await runCommand(cli, ['--version'], { ...options, timeoutMs: 10000 });
  if (version.isError) throw new Error(`CLI version probe failed: ${version.content[0].text}`);
  const help = await runCommand(cli, ['--help'], { ...options, timeoutMs: 10000 });
  if (help.isError || help.details.truncated) throw new Error('CLI capability probe failed or was truncated.');
  const text = help.content[0].text;
  const commands = [...new Set(Object.values(ACTIONS).map(d => d.command))];
  const missing = commands.filter(c => !new RegExp(`^\\s{2,}${c}(?=[\\s\\[<])`, 'm').test(text));
  if (missing.length) throw new Error(`Incompatible configured CodeGraph ${cli} (${version.content[0].text.trim()}): missing commands ${missing.join(', ')}. No PATH fallback.`);
  return { cli_path: cli, cli_version: version.content[0].text.trim(), commands };
}

export async function prepare(params) {
  const d = Object.hasOwn(ACTIONS, params.action) ? ACTIONS[params.action] : undefined;
  if (!d) throw new Error(`Unsupported action: ${params.action}. Use help. Admin/repair actions are not exposed.`);
  const allowed = new Set(['action', 'project_path', ...(d.required ?? []), ...d.fields]);
  for (const key of Object.keys(params)) if (!allowed.has(key)) throw new Error(`Unexpected field for ${params.action}: ${key}`);
  if (typeof params.project_path !== 'string' || !isAbsolute(params.project_path)) throw new Error('project_path must be an explicit absolute checkout/source root.');
  const project = await realpath(params.project_path);
  if (!(await stat(project)).isDirectory()) throw new Error('project_path must be a directory.');
  if (MUTATIONS.has(params.action) && (project === parse(project).root || project === await realpath(homedir()))) {
    throw new Error('Index mutation at home or filesystem root is forbidden, including symlink aliases.');
  }
  for (const key of d.required ?? []) {
    if (key === 'files') {
      if (!Array.isArray(params.files) || !params.files.length || params.files.some(f => typeof f !== 'string' || !f.trim())) throw new Error('files must contain at least one non-empty path.');
    } else if (typeof params[key] !== 'string' || !params[key].trim()) throw new Error(`${key} must be non-empty.`);
  }
  if (params.action === 'node' && !params.file?.trim() && !params.symbol?.trim()) throw new Error('node requires file or symbol.');
  for (const key of d.fields) {
    const v = params[key];
    if (v === undefined) continue;
    if (key in NUMBERS) {
      if (!Number.isSafeInteger(v) || v < NUMBERS[key]) throw new Error(`${key} must be an integer >= ${NUMBERS[key]}.`);
    } else if (key in BOOLEANS) {
      if (typeof v !== 'boolean') throw new Error(`${key} must be boolean.`);
    } else if (typeof v !== 'string' || !v.trim()) throw new Error(`${key} must be a non-empty string.`);
  }
  if (params.format && !['tree', 'flat', 'grouped'].includes(params.format)) throw new Error('format must be tree, flat or grouped.');
  const args = [d.command];
  if (MUTATIONS.has(params.action) || params.action === 'status') {
    if (params.action === 'init') args.push('--yes');
    if (params.action === 'status') args.push('--json');
  } else {
    args.push('--path', project);
    if (['search', 'callers', 'callees', 'impact', 'affected'].includes(params.action)) args.push('--json');
  }
  if (params.file !== undefined) args.push('--file', params.file);
  for (const key of d.fields) {
    if (params[key] === undefined) continue;
    if (FLAGS[key]) args.push(FLAGS[key], String(params[key]));
    if (BOOLEANS[key] && params[key]) args.push(BOOLEANS[key]);
  }
  const positional = MUTATIONS.has(params.action) || params.action === 'status' ? [project]
    : params.action === 'affected' ? params.files
      : params.action === 'node' ? (params.symbol ? [params.symbol] : [])
        : params.query !== undefined ? [params.query] : params.symbol ? [params.symbol] : [];
  if (positional.length) args.push('--', ...positional);
  return { project, args };
}

export function readinessIssue(s, project) {
  if (s.projectPath !== project) return 'status project identity does not match requested root';
  if (s.initialized !== true || s.index?.state !== 'complete') return 'index uninitialized or incomplete';
  if (s.worktreeMismatch !== null || s.index?.reindexRecommended !== false) return 'worktree mismatch, reindex required, or unknown readiness';
  const built = s.index?.builtWithExtractionVersion, current = s.index?.currentExtractionVersion;
  if (!Number.isSafeInteger(built) || !Number.isSafeInteger(current) || built !== current) return 'extraction version mismatch or unknown';
  const pending = s.pendingChanges;
  if (!pending || ['added', 'modified', 'removed'].some(k => !Number.isSafeInteger(pending[k]) || pending[k] !== 0)) return 'pending changes or unknown freshness';
  return null;
}

export async function execute(params, { cli, cwd, signal } = {}) {
  try {
    if (['help', 'diagnose'].includes(params.action)) {
      for (const key of Object.keys(params)) if (key !== 'action') throw new Error(`Unexpected field for ${params.action}: ${key}`);
    }
    if (params.action === 'help') return { content: [{ type: 'text', text: HELP }], details: {}, isError: false };
    // Validate action and target before executing even a harmless CLI probe.
    const prepared = params.action === 'diagnose' ? null : await prepare(params);
    const identity = await inspectCli(cli, { cwd: prepared?.project ?? cwd, signal });
    if (params.action === 'diagnose') return { content: [{ type: 'text', text: JSON.stringify(identity, null, 2) }], details: identity, isError: false };
    if (QUERIES.has(params.action)) {
      const status = await runCommand(cli, ['status', '--json', '--', prepared.project], { cwd: prepared.project, signal });
      if (status.isError) return { ...status, details: { ...status.details, ...identity, phase: 'readiness' } };
      let s;
      try { s = JSON.parse(status.content[0].text); }
      catch { return failure('Cannot parse index readiness; no graph query executed.', { ...identity, phase: 'readiness', output_path: status.details.output_path }); }
      const issue = readinessIssue(s, prepared.project);
      if (issue) return failure(`CodeGraph query blocked: ${issue}. Use the code-intelligence Skill readiness flow; no automatic refresh/repair performed.`, { ...identity, phase: 'readiness', status: s });
    }
    const result = await runCommand(cli, prepared.args, { cwd: prepared.project, signal });
    return { ...result, details: { ...result.details, ...identity, action: params.action, project_path: prepared.project } };
  } catch (error) {
    return failure(error.message, { action: params.action, cli_path: cli, cancelled: !!signal?.aborted });
  }
}
