import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// pi's real entry pulls in the whole TUI; we only need VERSION.
vi.mock("@earendil-works/pi-coding-agent", () => ({ VERSION: "0.85.1-test" }));

import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

import piTraceRecorder, { resolveTraceDir } from "../src/index.ts";
import type { HeaderRecord, RequestRecord, TraceRecord } from "../src/schema.ts";

type Handler = (event: unknown, ctx: ExtensionContext) => unknown;

/** Minimal fake of the pi ExtensionAPI: captures handlers, replays events. */
function fakePi(flags: Record<string, string | boolean> = {}) {
	const handlers = new Map<string, Handler[]>();
	const pi = {
		on(event: string, handler: Handler) {
			handlers.set(event, [...(handlers.get(event) ?? []), handler]);
		},
		registerFlag: vi.fn(),
		getFlag: (name: string) => flags[name],
	} as unknown as ExtensionAPI;

	const ctx = {
		cwd: "/work/repo",
		hasUI: false,
		ui: { setStatus: vi.fn() },
		sessionManager: {
			getSessionId: () => "sess-abc",
			getSessionFile: () => "/home/u/.pi/agent/sessions/x.jsonl",
		},
		model: {
			provider: "openai",
			id: "gpt-x",
			api: "openai-completions",
			baseUrl: "http://localhost:30000/v1",
			contextWindow: 128000,
			maxTokens: 4096,
			reasoning: false,
		},
		thinkingLevel: "off",
	} as unknown as ExtensionContext;

	const emit = async (type: string, event: Record<string, unknown> = {}) => {
		for (const h of handlers.get(type) ?? []) await h({ type, ...event }, ctx);
	};
	return { pi, ctx, emit, handlers };
}

function readTrace(dir: string): TraceRecord[] {
	const files = readdirSync(dir).filter((f) => f.endsWith(".jsonl"));
	expect(files).toHaveLength(1);
	return readFileSync(join(dir, files[0]!), "utf8")
		.trim()
		.split("\n")
		.map((l) => JSON.parse(l) as TraceRecord);
}

describe("pi extension wiring", () => {
	let dir: string;
	const savedEnv = process.env["AWL_TRACE_DIR"];

	beforeEach(() => {
		dir = mkdtempSync(join(tmpdir(), "awl-trace-"));
		process.env["AWL_TRACE_DIR"] = dir;
	});

	afterEach(() => {
		rmSync(dir, { recursive: true, force: true });
		if (savedEnv === undefined) delete process.env["AWL_TRACE_DIR"];
		else process.env["AWL_TRACE_DIR"] = savedEnv;
	});

	it("registers the trace-dir flag and subscribes to both intercept points", () => {
		const { pi, handlers } = fakePi();
		piTraceRecorder(pi);
		expect(pi.registerFlag).toHaveBeenCalledWith("trace-dir", expect.objectContaining({ type: "string" }));
		for (const ev of ["context", "before_provider_request", "after_provider_response", "message_update", "message_end"]) {
			expect(handlers.has(ev), ev).toBe(true);
		}
	});

	it("records one full turn end-to-end through the real hook names", async () => {
		const { pi, emit, handlers } = fakePi();
		piTraceRecorder(pi);

		await emit("session_start", { reason: "startup" });
		// real pi order (verified against 0.85.1): before_agent_start precedes agent_start
		await emit("before_agent_start", { prompt: "fix the bug", images: [], systemPrompt: "You are pi." });
		await emit("agent_start");
		await emit("turn_start", { turnIndex: 0, timestamp: 123 });

		const messages = [{ role: "user", content: "fix the bug", timestamp: 1 }];
		const contextResult = await handlers.get("context")![0]!({ type: "context", messages }, {} as ExtensionContext);
		expect(contextResult).toBeUndefined();

		const payload = { model: "gpt-x", messages: [{ role: "system", content: "You are pi." }, { role: "user", content: "fix the bug" }], stream: true };
		const reqResult = await handlers.get("before_provider_request")![0]!({ type: "before_provider_request", payload }, {
			model: { provider: "openai", id: "gpt-x", api: "openai-completions", baseUrl: "http://localhost:30000/v1", contextWindow: 128000, maxTokens: 4096, reasoning: false },
			thinkingLevel: "off",
		} as unknown as ExtensionContext);
		expect(reqResult).toBeUndefined();

		await emit("after_provider_response", { status: 200, headers: { "content-type": "text/event-stream" } });
		await emit("message_update", { message: {}, assistantMessageEvent: { type: "start" } });
		await emit("message_update", { message: {}, assistantMessageEvent: { type: "toolcall_start" } });
		await emit("message_update", { message: {}, assistantMessageEvent: { type: "toolcall_delta", delta: "{" } });
		await emit("message_update", { message: {}, assistantMessageEvent: { type: "toolcall_delta", delta: "}" } });

		const assistantMsg = {
			role: "assistant",
			content: [{ type: "toolCall", id: "call_1", name: "bash", arguments: { command: "ls" } }],
			usage: { input: 50, output: 8, cacheRead: 0, cacheWrite: 50, totalTokens: 58, cost: { total: 0 } },
			stopReason: "toolUse",
			timestamp: 5,
		};
		await emit("message_end", { message: { role: "user", content: "x" } }); // must be ignored
		await emit("message_end", { message: assistantMsg });

		await emit("tool_execution_start", { toolCallId: "call_1", toolName: "bash", args: { command: "ls" } });
		await emit("tool_execution_end", { toolCallId: "call_1", toolName: "bash", result: { content: [{ type: "text", text: "a\nb" }] }, isError: false });
		await emit("message_end", { message: { role: "toolResult", toolCallId: "call_1" } }); // ignored
		await emit("turn_end", { turnIndex: 0, message: assistantMsg, toolResults: [{ role: "toolResult" }] });
		await emit("agent_end", { messages: [messages[0], assistantMsg] });
		await emit("agent_settled");
		await emit("session_shutdown", { reason: "quit" });

		const trace = readTrace(dir);
		expect(trace.map((r) => r.type)).toEqual([
			"header",
			"user_prompt",
			"agent_start",
			"turn_start",
			"context",
			"request",
			"tool",
			"turn_end",
			"agent_end",
			"agent_settled",
			"shutdown",
		]);

		const header = trace[0] as HeaderRecord;
		expect(header).toMatchObject({
			schema: 1,
			session_id: "sess-abc",
			session_file: "/home/u/.pi/agent/sessions/x.jsonl",
			session_reason: "startup",
			cwd: "/work/repo",
			pi_version: "0.85.1-test",
			extension_version: "0.1.0",
			model: { provider: "openai", id: "gpt-x", api: "openai-completions", base_url: "http://localhost:30000/v1" },
			thinking_level: "off",
			trace_dir_source: "env",
		});
		expect(typeof header.hostname).toBe("string");
		expect(header.node_version).toBe(process.version);

		expect(trace[1]).toMatchObject({ type: "user_prompt", run: 0, prompt: "fix the bug", system_prompt: "You are pi.", n_images: 0 });
		expect(trace[4]).toMatchObject({ type: "context", turn: 0, n_messages: 1 });

		const req = trace[5] as RequestRecord;
		expect(req).toMatchObject({
			req: 0,
			run: 0,
			turn: 0,
			outcome: "done",
			stop_reason: "toolUse",
			http_status: 200,
			first_delta_type: "toolcall",
			n_deltas: 2,
			usage: { input: 50, output: 8, cacheRead: 0, cacheWrite: 50, totalTokens: 58 },
			payload,
			model: { id: "gpt-x" },
		});
		// `cost` is pi bookkeeping, not serving-side signal — must be dropped.
		expect(req.usage).not.toHaveProperty("cost");
		expect(req.output?.tool_calls).toEqual([{ id: "call_1", name: "bash", args_chars: JSON.stringify({ command: "ls" }).length }]);

		expect(trace[6]).toMatchObject({ type: "tool", tool_call_id: "call_1", name: "bash", is_error: false, args: { command: "ls" } });
		expect(trace[7]).toMatchObject({ type: "turn_end", turn: 0, stop_reason: "toolUse", n_tool_results: 1 });
		expect(trace.at(-1)).toMatchObject({ type: "shutdown", reason: "quit", n_runs: 1, n_requests: 1, n_tools: 1 });
	});

	it("survives a throwing internal path without breaking later hooks", async () => {
		const { pi, emit } = fakePi();
		piTraceRecorder(pi);
		await emit("session_start", { reason: "startup" });
		const stderr = vi.spyOn(process.stderr, "write").mockImplementation(() => true);
		// turn_end with a message that is not an object → reading .stopReason throws inside the handler
		await emit("turn_end", { turnIndex: 0, message: null, toolResults: [] });
		expect(stderr).toHaveBeenCalledWith(expect.stringContaining("handler error"));
		stderr.mockRestore();
		await emit("agent_start");
		await emit("session_shutdown", { reason: "quit" });
		expect(readTrace(dir).map((r) => r.type)).toEqual(["header", "agent_start", "shutdown"]);
	});

	it("starts a fresh file on a second session_start and closes the previous one", async () => {
		const { pi, emit } = fakePi();
		piTraceRecorder(pi);
		await emit("session_start", { reason: "startup" });
		await emit("session_start", { reason: "new", previousSessionFile: "/old.jsonl" });
		await emit("session_shutdown", { reason: "quit" });
		const files = readdirSync(dir).filter((f) => f.endsWith(".jsonl")).sort();
		expect(files).toHaveLength(2);
		const first = readFileSync(join(dir, files[0]!), "utf8").trim().split("\n").map((l) => JSON.parse(l) as TraceRecord);
		const second = readFileSync(join(dir, files[1]!), "utf8").trim().split("\n").map((l) => JSON.parse(l) as TraceRecord);
		expect(first.map((r) => r.type)).toEqual(["header", "shutdown"]);
		expect(first[1]).toMatchObject({ reason: "reopen" });
		expect(second[0]).toMatchObject({ session_reason: "new", previous_session_file: "/old.jsonl" });
	});

	it("does nothing before session_start", async () => {
		const { pi, emit } = fakePi();
		piTraceRecorder(pi);
		await emit("agent_start");
		await emit("turn_start", { turnIndex: 0, timestamp: 1 });
		expect(readdirSync(dir)).toHaveLength(0);
	});
});

describe("resolveTraceDir", () => {
	const saved = process.env["AWL_TRACE_DIR"];
	afterEach(() => {
		if (saved === undefined) delete process.env["AWL_TRACE_DIR"];
		else process.env["AWL_TRACE_DIR"] = saved;
	});

	it("prefers flag over env over default", () => {
		process.env["AWL_TRACE_DIR"] = "/from/env";
		expect(resolveTraceDir("/from/flag")).toEqual({ dir: "/from/flag", source: "flag" });
		expect(resolveTraceDir(undefined)).toEqual({ dir: "/from/env", source: "env" });
		delete process.env["AWL_TRACE_DIR"];
		const def = resolveTraceDir("");
		expect(def.source).toBe("default");
		expect(def.dir).toMatch(/\/traces$/);
		expect(def.dir).not.toContain("/extension/");
	});
});
