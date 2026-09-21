/**
 * pi-trace-recorder — pi extension that records a coding-agent session as a
 * replayable trajectory (see schema.ts for the file format).
 *
 * It observes exactly the two places CLAUDE.md allows the harness to be
 * touched, plus lifecycle events around them:
 *
 *   context assembly  → `context`                      (harness-side view)
 *   request emission  → `before_provider_request`,
 *                        `after_provider_response`,
 *                        `message_update`, `message_end`  (wire-side view + timing)
 *
 * It never modifies anything: every handler returns undefined.
 *
 * Trace directory resolution (first hit wins):
 *   1. `--trace-dir <path>`  CLI flag
 *   2. `AWL_TRACE_DIR`       environment variable
 *   3. `<repo>/traces/`      i.e. ../../traces relative to this file
 *
 * Usage:
 *   pi -e /path/to/agent-workload-lab/extension/src/index.ts
 * or add the path to `extensions` in ~/.pi/agent/settings.json.
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { hostname } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { type ExtensionAPI, type ExtensionContext, VERSION as PI_VERSION } from "@earendil-works/pi-coding-agent";

import { type AssistantLike, type DeltaKind, TraceRecorder } from "./recorder.ts";
import { EXTENSION_VERSION, type ModelInfo } from "./schema.ts";
import { JsonlFileSink } from "./sink.ts";

const TAG = "[pi-trace-recorder]";

export default function piTraceRecorder(pi: ExtensionAPI): void {
	pi.registerFlag("trace-dir", {
		description: "Directory for trajectory JSONL files (default: $AWL_TRACE_DIR or <repo>/traces)",
		type: "string",
	});

	let recorder: TraceRecorder | null = null;

	// Every handler is wrapped: a recorder bug must degrade to "no trace",
	// never to a broken agent session (CLAUDE.md §10).
	const guard =
		<E>(fn: (event: E, ctx: ExtensionContext) => void) =>
		(event: E, ctx: ExtensionContext): void => {
			if (!recorder) return;
			try {
				fn(event, ctx);
			} catch (err) {
				process.stderr.write(`${TAG} handler error: ${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`);
			}
		};

	// ── session lifecycle ──────────────────────────────────────────────────

	pi.on("session_start", (event, ctx) => {
		try {
			recorder?.close("reopen");
			const { dir, source } = resolveTraceDir(pi.getFlag("trace-dir"));
			const file = uniquePath(dir, `${compactIso(Date.now())}_${ctx.sessionManager.getSessionId()}`);
			const sink = new JsonlFileSink(file);
			recorder = new TraceRecorder(sink);
			recorder.open({
				session_id: ctx.sessionManager.getSessionId(),
				session_file: ctx.sessionManager.getSessionFile() ?? null,
				session_reason: event.reason,
				previous_session_file: event.previousSessionFile ?? null,
				cwd: ctx.cwd,
				hostname: hostname(),
				platform: `${process.platform}-${process.arch}`,
				node_version: process.version,
				pi_version: PI_VERSION,
				extension_version: EXTENSION_VERSION,
				extension_git_commit: gitHead(extensionDir()),
				model: modelInfo(ctx.model),
				thinking_level: ctx.thinkingLevel ?? null,
				trace_dir_source: source,
			});
			if (ctx.hasUI) ctx.ui.setStatus("trace", `rec → ${file}`);
		} catch (err) {
			recorder = null;
			process.stderr.write(`${TAG} failed to start recording: ${String(err)}\n`);
		}
	});

	pi.on(
		"session_shutdown",
		guard((event) => {
			recorder?.close(event.reason);
			recorder = null;
		}),
	);

	pi.on(
		"model_select",
		guard((event) => {
			const model = modelInfo(event.model);
			if (model) recorder?.modelSelect(event.source, model, modelInfo(event.previousModel));
		}),
	);

	// ── agent run ──────────────────────────────────────────────────────────

	pi.on("agent_start", guard(() => recorder?.agentStart()));

	pi.on(
		"before_agent_start",
		guard((event) => {
			recorder?.userPrompt(event.prompt, event.images?.length ?? 0, event.systemPrompt);
		}),
	);

	pi.on("agent_end", guard((event) => recorder?.agentEnd(event.messages.length)));
	pi.on("agent_settled", guard(() => recorder?.agentSettled()));

	// ── turn ───────────────────────────────────────────────────────────────

	pi.on("turn_start", guard((event) => recorder?.turnStart(event.turnIndex, event.timestamp)));

	pi.on(
		"turn_end",
		guard((event) => {
			const m = event.message as { stopReason?: unknown };
			const stopReason = typeof m.stopReason === "string" ? m.stopReason : null;
			recorder?.turnEnd(event.turnIndex, stopReason, event.toolResults.length);
		}),
	);

	// ── intercept point 1: context assembly (observe only) ────────────────

	pi.on(
		"context",
		guard((event) => {
			recorder?.context(event.messages);
		}),
	);

	// ── intercept point 2: model request (observe only) ───────────────────

	pi.on(
		"before_provider_request",
		guard((event, ctx) => {
			recorder?.requestStart(event.payload, modelInfo(ctx.model), ctx.thinkingLevel ?? null);
		}),
	);

	pi.on(
		"after_provider_response",
		guard((event) => {
			recorder?.responseReceived(event.status, event.headers);
		}),
	);

	pi.on(
		"message_update",
		guard((event) => {
			const kind = deltaKind(event.assistantMessageEvent.type);
			if (kind) recorder?.streamDelta(kind);
		}),
	);

	pi.on(
		"message_end",
		guard((event) => {
			if (event.message.role !== "assistant") return;
			recorder?.requestEnd(event.message as unknown as AssistantLike);
		}),
	);

	// ── tools ──────────────────────────────────────────────────────────────

	pi.on(
		"tool_execution_start",
		guard((event) => recorder?.toolStart(event.toolCallId, event.toolName, event.args)),
	);

	pi.on(
		"tool_execution_end",
		guard((event) => recorder?.toolEnd(event.toolCallId, event.toolName, event.result, event.isError)),
	);

	// ── compaction ─────────────────────────────────────────────────────────

	pi.on(
		"session_compact",
		guard((event) => {
			const e = event.compactionEntry;
			recorder?.compaction({
				reason: event.reason,
				will_retry: event.willRetry,
				from_extension: event.fromExtension,
				tokens_before: e.tokensBefore,
				summary_chars: e.summary.length,
				usage: e.usage
					? {
							input: e.usage.input,
							output: e.usage.output,
							cacheRead: e.usage.cacheRead,
							cacheWrite: e.usage.cacheWrite,
							totalTokens: e.usage.totalTokens,
						}
					: null,
			});
		}),
	);

	pi.on(
		"session_compact_failed",
		guard((event) => {
			recorder?.compactionFailed({
				reason: event.reason,
				aborted: event.aborted,
				error_message: event.errorMessage ?? null,
			});
		}),
	);
}

// ── helpers ───────────────────────────────────────────────────────────────

function deltaKind(type: string): DeltaKind | null {
	switch (type) {
		case "text_delta":
			return "text";
		case "thinking_delta":
			return "thinking";
		case "toolcall_delta":
			return "toolcall";
		default:
			return null;
	}
}

function modelInfo(model: ExtensionContext["model"]): ModelInfo | null {
	if (!model) return null;
	return {
		provider: model.provider,
		id: model.id,
		api: model.api,
		base_url: model.baseUrl,
		context_window: model.contextWindow,
		max_tokens: model.maxTokens,
		reasoning: model.reasoning,
	};
}

export function resolveTraceDir(flag: boolean | string | undefined): {
	dir: string;
	source: "flag" | "env" | "default";
} {
	if (typeof flag === "string" && flag.length > 0) return { dir: resolve(flag), source: "flag" };
	const env = process.env["AWL_TRACE_DIR"];
	if (env && env.length > 0) return { dir: resolve(env), source: "env" };
	return { dir: resolve(extensionDir(), "..", "..", "traces"), source: "default" };
}

function extensionDir(): string {
	try {
		return dirname(fileURLToPath(import.meta.url));
	} catch {
		return process.cwd();
	}
}

function gitHead(cwd: string): string | null {
	try {
		return execFileSync("git", ["rev-parse", "HEAD"], { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
	} catch {
		return null;
	}
}

/** 2026-09-18T10:03:04.123Z → 20260918T100304.123 */
function compactIso(ms: number): string {
	return new Date(ms).toISOString().replace(/[-:]/g, "").slice(0, 19);
}

/** `<dir>/<stem>.jsonl`, or `<stem>-2.jsonl`, … if taken (reload keeps the session id). */
function uniquePath(dir: string, stem: string): string {
	let candidate = join(dir, `${stem}.jsonl`);
	for (let n = 2; existsSync(candidate); n++) candidate = join(dir, `${stem}-${n}.jsonl`);
	return candidate;
}
