import type { ExtensionAPI } from '@earendil-works/pi-coding-agent';
import { Type } from 'typebox';
import { readFile } from 'node:fs/promises';
import { ACTIONS, execute } from './core.mjs';

// Explicitly installed adapter only. The root governance package exports no extension.
export default function register(pi: ExtensionAPI) {
  pi.registerTool({
    name: 'codegraph',
    label: 'CodeGraph (local)',
    description: 'Use your explicitly configured local CodeGraph CLI for source exploration, exact source, symbol search, dependency/impact analysis and derived-index maintenance. Requires absolute project_path except help/diagnose. Queries check index freshness and never refresh automatically. diagnose reports the actual CLI path/version. No CLI install/upgrade, lock repair or destructive/admin commands.',
    promptSnippet: 'Inspect source and dependencies through an explicitly configured local CodeGraph CLI',
    promptGuidelines: [
      'Use codegraph for structural source questions; use native inspection for prose, logs and configuration. The code-intelligence Skill owns applicability and safe index readiness.',
      'Pass an explicit absolute checkout/source root as codegraph project_path; start with explore for an area and use node/search/callers/callees/impact/affected for focused follow-up.',
      'codegraph init/sync/index change derived index state and require task authority. No automatic refresh or repair is performed; use diagnose to inspect CLI identity rather than assuming shell PATH matches the tool.',
    ],
    parameters: Type.Object({
      action: Type.Union([...Object.keys(ACTIONS), 'help', 'diagnose'].map(a => Type.Literal(a))),
      project_path: Type.Optional(Type.String({ description: 'Explicit absolute checkout/source root' })),
      query: Type.Optional(Type.String()),
      symbol: Type.Optional(Type.String()),
      file: Type.Optional(Type.String()),
      files: Type.Optional(Type.Array(Type.String())),
      max_files: Type.Optional(Type.Integer({ minimum: 1 })),
      offset: Type.Optional(Type.Integer({ minimum: 1 })),
      limit: Type.Optional(Type.Integer({ minimum: 1 })),
      depth: Type.Optional(Type.Integer({ minimum: 1 })),
      kind: Type.Optional(Type.String()),
      filter: Type.Optional(Type.String()),
      pattern: Type.Optional(Type.String()),
      format: Type.Optional(Type.Union(['tree', 'flat', 'grouped'].map(f => Type.Literal(f)))),
      max_depth: Type.Optional(Type.Integer({ minimum: 0 })),
      no_metadata: Type.Optional(Type.Boolean()),
      symbols_only: Type.Optional(Type.Boolean()),
      quiet: Type.Optional(Type.Boolean()),
      verbose: Type.Optional(Type.Boolean()),
      force: Type.Optional(Type.Boolean({ description: 'Only supported for index at a non-protected explicit root; never init' })),
    }, { additionalProperties: false }),
    async execute(_id, params, signal, _onUpdate, ctx) {
      try {
        const config = JSON.parse(await readFile(new URL('./config.json', import.meta.url), 'utf8'));
        return await execute(params, { cli: config.cli, cwd: ctx.cwd, signal });
      } catch (error) {
        return { content: [{ type: 'text' as const, text: `Local CodeGraph configuration error: ${error instanceof Error ? error.message : String(error)}` }], details: {}, isError: true };
      }
    },
  });
}
