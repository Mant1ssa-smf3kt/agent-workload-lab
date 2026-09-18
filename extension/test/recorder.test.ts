import { describe, expect, it } from "vitest";

import { digestMessage, sha256, stableStringify } from "../src/digest.ts";
import { type AssistantLike, TraceRecorder } from "../src/recorder.ts";
import type { ContextRecord, RequestRecord, ToolRecord, TraceRecord } from "../src/schema.ts";
import { TRACE_SCHEMA_VERSION } from "../src/schema.ts";
import { MemorySink } from "../src/sink.ts";

/** Deterministic clock: every call advances by `step` ms. */
function fakeClock(start = 1_000_000, step = 10): () => number {
	let now = start - step;
	return () => (now += step);
}

const HEADER = {
	session_id: "sess-1",
	session_file: "/tmp/sess-1.jsonl",
	session_reason: "startup",
	previous_session_file: null,
	cwd: "/work",
	hostname: "box",
	platform: "darwin-arm64",
	node_version: "v26",
	pi_version: "0.85.1",
	extension_version: "0.1.0",
	extension_git_commit: null,
	model: null,
	thinking_level: null,
	trace_dir_source: "default" as const,
};

const MODEL = {
	provider: "openai",
	id: "gpt-x",
	api: "openai-completions",
	base_url: "http://localhost:30000/v1",
	context_window: 128000,
	max_tokens: 4096,
	reasoning: false,
};

function assistant(over: Partial<AssistantLike> = {}): AssistantLike {
	return {
		role: "assistant",
		content: [{ type: "text", text: "hello" }],
		usage: { input: 100, output: 5, cacheRead: 80, cacheWrite: 0, totalTokens: 105 },
		stopReason: "stop",
		...over,
	};
}

function setup() {
	const sink = new MemorySink();
	const rec = new TraceRecorder(sink, fakeClock());
	rec.open(HEADER);
	const records = () => sink.records() as TraceRecord[];
	const ofType = <T extends TraceRecord>(type: T["type"]) => records().filter((r) => r.type === type) as T[];
	return { sink, rec, records, ofType };
}

describe("TraceRecorder", () => {
	it("writes a schema-versioned header as seq 0 and a shutdown on close", () => {
		const { rec, records, sink } = setup();
		rec.close("quit");
		const [header, shutdown] = records();
		expect(header).toMatchObject({ type: "header", seq: 0, schema: TRACE_SCHEMA_VERSION, session_id: "sess-1" });
		expect(shutdown).toMatchObject({ type: "shutdown", reason: "quit", n_runs: 0, n_requests: 0, n_tools: 0 });
		expect(sink.closed).toBe(true);
	});

	it("assigns strictly increasing seq and non-decreasing t", () => {
		const { rec, records } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.context([]);
		rec.turnEnd(0, "stop", 0);
		rec.agentEnd(2);
		rec.close("quit");
		const rs = records();
		rs.forEach((r, i) => expect(r.seq).toBe(i));
		for (let i = 1; i < rs.length; i++) expect(rs[i]!.t).toBeGreaterThanOrEqual(rs[i - 1]!.t);
	});

	it("records a full request with all timing points in order", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		const payload = { model: "gpt-x", messages: [{ role: "user", content: "hi" }] };
		rec.requestStart(payload, MODEL, "off");
		rec.responseReceived(200, { "x-request-id": "abc" });
		rec.streamDelta("thinking");
		rec.streamDelta("text");
		rec.streamDelta("text");
		rec.requestEnd(assistant());

		const [r] = ofType<RequestRecord>("request");
		expect(r).toBeDefined();
		expect(r!.req).toBe(0);
		expect(r!.run).toBe(0);
		expect(r!.turn).toBe(0);
		expect(r!.outcome).toBe("done");
		expect(r!.http_status).toBe(200);
		expect(r!.response_headers).toEqual({ "x-request-id": "abc" });
		expect(r!.first_delta_type).toBe("thinking");
		expect(r!.n_deltas).toBe(3);
		expect(r!.t).toBe(r!.t_request);
		expect(r!.t_request).toBeLessThan(r!.t_response!);
		expect(r!.t_response).toBeLessThan(r!.t_first_delta!);
		expect(r!.t_first_delta).toBeLessThan(r!.t_first_content!);
		expect(r!.t_first_content).toBeLessThan(r!.t_end!);
		expect(r!.usage).toEqual({ input: 100, output: 5, cacheRead: 80, cacheWrite: 0, totalTokens: 105 });
		expect(r!.output).toMatchObject({ text_chars: 5, thinking_chars: 0, tool_calls: [] });
		expect(r!.payload).toEqual(payload);
		expect(r!.payload_sha256).toBe(sha256(JSON.stringify(payload)));
		expect(r!.payload_chars).toBe(JSON.stringify(payload).length);
		expect(r!.model).toEqual(MODEL);
		expect(r!.thinking_level).toBe("off");
	});

	it("t_first_content skips thinking deltas; text-first stream sets both to the same delta", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.requestStart({}, null, null);
		rec.streamDelta("text");
		rec.requestEnd(assistant());
		const [r] = ofType<RequestRecord>("request");
		expect(r!.first_delta_type).toBe("text");
		// Same delta → clock called twice in a row, so exactly one step apart.
		expect(r!.t_first_content! - r!.t_first_delta!).toBe(10);
	});

	it("digests tool calls in the assistant output", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.requestStart({}, null, null);
		rec.requestEnd(
			assistant({
				content: [
					{ type: "thinking", thinking: "hmm" },
					{ type: "toolCall", id: "c1", name: "bash", arguments: { command: "ls" } },
				],
				stopReason: "toolUse",
			}),
		);
		const [r] = ofType<RequestRecord>("request");
		expect(r!.output).toMatchObject({
			text_chars: 0,
			thinking_chars: 3,
			tool_calls: [{ id: "c1", name: "bash", args_chars: JSON.stringify({ command: "ls" }).length }],
		});
		expect(r!.stop_reason).toBe("toolUse");
	});

	it("closes a dangling request as superseded when a new one starts", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.requestStart({ a: 1 }, null, null);
		rec.responseReceived(500, {});
		// no requestEnd — pi retried with a fresh stream
		rec.requestStart({ a: 2 }, null, null);
		rec.requestEnd(assistant());
		const rs = ofType<RequestRecord>("request");
		expect(rs).toHaveLength(2);
		expect(rs[0]).toMatchObject({ req: 0, outcome: "superseded", http_status: 500, t_end: null, usage: null, payload: { a: 1 } });
		expect(rs[1]).toMatchObject({ req: 1, outcome: "done", payload: { a: 2 } });
	});

	it("maps error/aborted stop reasons to outcomes and keeps errorMessage", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.requestStart({}, null, null);
		rec.requestEnd(assistant({ stopReason: "error", errorMessage: "boom", usage: undefined }));
		rec.requestStart({}, null, null);
		rec.requestEnd(assistant({ stopReason: "aborted" }));
		const rs = ofType<RequestRecord>("request");
		expect(rs[0]).toMatchObject({ outcome: "error", error_message: "boom", usage: null });
		expect(rs[1]).toMatchObject({ outcome: "aborted" });
	});

	it("closes an open request as aborted on agent_end and as unfinished on close", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.requestStart({}, null, null);
		rec.agentEnd(1);
		rec.agentStart();
		rec.turnStart(0, 2);
		rec.requestStart({}, null, null);
		rec.close("quit");
		const rs = ofType<RequestRecord>("request");
		expect(rs.map((r) => r.outcome)).toEqual(["aborted", "unfinished"]);
		expect(rs.map((r) => r.run)).toEqual([0, 1]);
	});

	it("handles unserializable payloads without throwing", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		const cyc: Record<string, unknown> = {};
		cyc["self"] = cyc;
		rec.requestStart(cyc, null, null);
		rec.requestEnd(assistant());
		const [r] = ofType<RequestRecord>("request");
		expect(r!.payload).toBeNull();
		expect(r!.payload_sha256).toBeNull();
		expect(r!.payload_error).toMatch(/circular/i);
		expect(r!.outcome).toBe("done");
	});

	it("records tools keyed by call id, tolerating interleaving and a missed start", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.toolStart("a", "bash", { command: "sleep 1" });
		rec.toolStart("b", "read", { path: "x" });
		rec.toolEnd("b", "read", { content: [{ type: "text", text: "file body" }] }, false);
		rec.toolEnd("a", "bash", { content: [] }, true);
		rec.toolEnd("c", "edit", {}, false); // never started
		const ts = ofType<ToolRecord>("tool");
		expect(ts.map((t) => t.tool_call_id)).toEqual(["b", "a", "c"]);
		expect(ts[0]).toMatchObject({ name: "read", is_error: false, args: { path: "x" } });
		expect(ts[0]!.result_chars).toBeGreaterThan(0);
		expect(ts[0]!.t_end).toBeGreaterThan(ts[0]!.t_start);
		expect(ts[1]).toMatchObject({ name: "bash", is_error: true });
		expect(ts[1]!.t_start).toBeLessThan(ts[0]!.t_start); // a started first
		expect(ts[2]).toMatchObject({ name: "edit", args: null, is_error: false });
	});

	it("flushes still-running tools as unfinished on close", () => {
		const { rec, ofType, records } = setup();
		rec.agentStart();
		rec.turnStart(0, 1);
		rec.toolStart("a", "bash", {});
		rec.close("quit");
		const [t] = ofType<ToolRecord>("tool");
		expect(t).toMatchObject({ t_end: null, result_chars: null, is_error: null });
		expect(records().at(-1)).toMatchObject({ type: "shutdown", n_tools: 1 });
	});

	it("emits the full system prompt only the first time a hash is seen, attributed to the run about to start", () => {
		const { rec, ofType } = setup();
		// pi order: before_agent_start → agent_start
		rec.userPrompt("do x", 0, "SYS A");
		rec.agentStart();
		rec.agentEnd(0);
		rec.userPrompt("do y", 2, "SYS A");
		rec.agentStart();
		rec.agentEnd(0);
		rec.userPrompt("do z", 0, "SYS B");
		rec.agentStart();
		const ups = ofType("user_prompt") as Array<{ system_prompt?: string; system_prompt_sha256: string; n_images: number; run: number }>;
		expect(ups[0]!.system_prompt).toBe("SYS A");
		expect(ups[1]!.system_prompt).toBeUndefined();
		expect(ups[1]!.system_prompt_sha256).toBe(ups[0]!.system_prompt_sha256);
		expect(ups[1]!.n_images).toBe(2);
		expect(ups[2]!.system_prompt).toBe("SYS B");
		expect(ups.map((u) => u.run)).toEqual([0, 1, 2]);
	});

	it("context digests are stable across turns and detect a rewritten message", () => {
		const { rec, ofType } = setup();
		rec.agentStart();
		const sys = { role: "user", content: "hi", timestamp: 1 };
		const asst = { role: "assistant", content: [{ type: "text", text: "ok" }], timestamp: 2 };
		const tool = { role: "toolResult", toolCallId: "c1", toolName: "read", content: [{ type: "text", text: "A".repeat(100) }], isError: false, timestamp: 3 };
		rec.turnStart(0, 1);
		rec.context([sys, asst, tool]);
		rec.turnStart(1, 2);
		// Harness truncated the tool result between turns — the classic cache killer.
		rec.context([sys, asst, { ...tool, content: [{ type: "text", text: "A".repeat(10) + "…[truncated]" }] }]);
		const [c0, c1] = ofType<ContextRecord>("context");
		expect(c0!.n_messages).toBe(3);
		expect(c0!.messages[2]).toMatchObject({ role: "toolResult", tool_name: "read", tool_call_id: "c1", is_error: false, kinds: ["text"] });
		expect(c1!.messages[0]!.sha256).toBe(c0!.messages[0]!.sha256);
		expect(c1!.messages[1]!.sha256).toBe(c0!.messages[1]!.sha256);
		expect(c1!.messages[2]!.sha256).not.toBe(c0!.messages[2]!.sha256);
		expect(c1!.total_chars).toBeLessThan(c0!.total_chars);
		expect(c1!.turn).toBe(1);
	});

	it("ignores stream/response events with no open request", () => {
		const { rec, records } = setup();
		rec.responseReceived(200, {});
		rec.streamDelta("text");
		rec.requestEnd(assistant());
		expect(records()).toHaveLength(1); // header only
	});

	it("is a no-op after close", () => {
		const { rec, records } = setup();
		rec.close("quit");
		rec.agentStart();
		rec.close("quit");
		expect(records().map((r) => r.type)).toEqual(["header", "shutdown"]);
	});
});

describe("digest", () => {
	it("stableStringify is key-order independent", () => {
		expect(stableStringify({ b: 1, a: { d: 2, c: [3, { f: 4, e: 5 }] } })).toBe(stableStringify({ a: { c: [3, { e: 5, f: 4 }], d: 2 }, b: 1 }));
	});

	it("digestMessage tolerates unknown shapes", () => {
		expect(digestMessage(null, 0)).toMatchObject({ i: 0, role: "unknown", kinds: [] });
		expect(digestMessage({ role: "custom", content: "plain string" }, 1)).toMatchObject({ role: "custom", kinds: [] });
		expect(digestMessage({ role: "user", content: [{ type: "text" }, { type: "image" }, { type: "text" }] }, 2).kinds).toEqual(["text", "image"]);
	});
});
