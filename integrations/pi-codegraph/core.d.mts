export interface ToolResult {
  content: Array<{ type: 'text'; text: string }>;
  details: Record<string, unknown>;
  isError: boolean;
}
export interface RunOptions {
  cwd?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  maxBytes?: number;
  maxLines?: number;
  killAfterMs?: number;
}
export const ACTIONS: Readonly<Record<string, { command: string; required?: string[]; fields: string[] }>>;
export const HELP: string;
export function runCommand(cli: string, args: string[], options?: RunOptions): Promise<ToolResult>;
export function inspectCli(cli: string, options?: RunOptions): Promise<{ cli_path: string; cli_version: string; commands: string[] }>;
export function prepare(params: Record<string, unknown>): Promise<{ project: string; args: string[] }>;
export function readinessIssue(status: Record<string, unknown>, project: string): string | null;
export function execute(params: Record<string, unknown>, options: { cli: string; cwd?: string; signal?: AbortSignal }): Promise<ToolResult>;
