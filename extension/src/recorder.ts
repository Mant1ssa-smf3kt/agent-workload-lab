import { digestMessage, jsonChars, sha256 } from "./digest.ts";
import type {
	CompactionFailedRecord,
	CompactionRecord,
	HeaderRecord,
	ModelInfo,
	PendingRecord,
	RequestOutcome,
	RequestRecord,
	ToolCallDigest,
	TraceRecord,
	UnsequencedRecord,
	Usage,
} from "./schema.ts";
import { TRACE_SCHEMA_VERSION } from "./schema.ts";
import type { Sink } from "./sink.ts";

/** Fields the recorder fills in itself when opening a file. */
export type HeaderInput = Omit<HeaderRecord, "type" | "t" | "seq" | "schema">;

/** Subset of pi's AssistantMessage the recorder reads. Kept structural so tests need no pi types. */
export interface AssistantLike {
	role: "assistant";
	content: unknown[];
	usage?: Partial<Usage> | undefined;
	stopReason?: string | undefined;
	errorMessage?: string | undefined;
}

export type DeltaKind = "text" | "thinking" | "toolcall";

interface OpenRequest {
	run: number;
	turn: number;
	req: number;
	model: ModelInfo | null;
	thinking_level: string | null;
	payload: unknown;
	t_request: number;
	t_response: number | null;
	http_status: number | null;
	response_headers: Record<string, string> | null;
	t_first_delta: number | null;
	t_first_content: number | null;
	first_delta_type: string | null;
	n_deltas: number;
}

interface OpenTool {
	run: number;
	turn: number;
	name: string;
	args: unknown;
	t_start: number;
}

/**
 * Pure trace state machine: turns pi hook invocations into `TraceRecord`s and
 * hands them to a `Sink`. No pi imports, no I/O of its own, injectable clock —
 * so it is unit-testable without pi.
 *
 * Invariants it relies on:
 *   - pi runs at most one provider request at a time per session, so a single
 *     "open request" slot is enough. A new request while one is open means the
 *     previous stream ended without `message_end` (error/abort); it is closed
 *     as `superseded`.
 *   - `turnIndex` resets per agent run; `run` and the global `req` counter are
 *     the recorder's own.
 *   - Tool executions may interleave (parallel tool mode) → keyed by call id.
 */
export class TraceRecorder {
	private seq = 0;
	private run = -1;
	private turn = -1;
	private req = -1;
	private nTools = 0;
	private openRequest: OpenRequest | null = null;
	private readonly openTools = new Map<string, OpenTool>();
	private readonly seenSystemPrompts = new Set<string>();
	private closed = false;

	constructor(
		private readonly sink: Sink,
		private readonly clock: () => number = Date.now,
	) {}

	// ── session ────────────────────────────────────────────────────────────

	open(header: HeaderInput): void {
		this.emit({ type: "header", schema: TRACE_SCHEMA_VERSION, ...header });
	}

	modelSelect(source: string, model: ModelInfo, previous: ModelInfo | null): void {
		this.emit({ type: "model_select", source, model, previous });
	}

	close(reason: string): void {
		if (this.closed) return;
		this.finishOpenRequest("unfinished", null);
		for (const [id, tool] of this.openTools) this.finishTool(id, tool, null, null);
		this.emit({
			type: "shutdown",
			reason,
			n_runs: this.run + 1,
			n_requests: this.req + 1,
			n_tools: this.nTools,
		});
		this.closed = true;
		this.sink.close();
	}

	// ── agent run ──────────────────────────────────────────────────────────

	agentStart(): void {
		this.run += 1;
		this.turn = -1;
		this.emit({ type: "agent_start", run: this.run });
	}

	/** Fires on `before_agent_start`, i.e. *before* `agent_start` — so it belongs to the run about to begin. */
	userPrompt(prompt: string, nImages: number, systemPrompt: string): void {
		const hash = sha256(systemPrompt);
		const first = !this.seenSystemPrompts.has(hash);
		this.seenSystemPrompts.add(hash);
		this.emit({
			type: "user_prompt",
			run: this.run + 1,
			prompt,
			prompt_chars: prompt.length,
			n_images: nImages,
			system_prompt_sha256: hash,
			system_prompt_chars: systemPrompt.length,
			...(first ? { system_prompt: systemPrompt } : {}),
		});
	}

	agentEnd(nMessages: number): void {
		// A run can end with a stream still open (abort mid-stream).
		this.finishOpenRequest("aborted", null);
		this.emit({ type: "agent_end", run: this.run, n_messages: nMessages });
	}

	agentSettled(): void {
		this.emit({ type: "agent_settled", run: this.run });
	}

	// ── turn ───────────────────────────────────────────────────────────────

	turnStart(turnIndex: number, piTimestamp: number): void {
		this.turn = turnIndex;
		this.emit({ type: "turn_start", run: this.run, turn: turnIndex, pi_timestamp: piTimestamp });
	}

	turnEnd(turnIndex: number, stopReason: string | null, nToolResults: number): void {
		this.emit({
			type: "turn_end",
			run: this.run,
			turn: turnIndex,
			stop_reason: stopReason,
			n_tool_results: nToolResults,
		});
	}

	// ── harness-side context ───────────────────────────────────────────────

	context(messages: unknown[]): void {
		const digests = messages.map((m, i) => digestMessage(m, i));
		this.emit({
			type: "context",
			run: this.run,
			turn: this.turn,
			n_messages: digests.length,
			total_chars: digests.reduce((acc, d) => acc + d.chars, 0),
			messages: digests,
		});
	}

	// ── wire-side request ──────────────────────────────────────────────────

	requestStart(payload: unknown, model: ModelInfo | null, thinkingLevel: string | null): void {
		this.finishOpenRequest("superseded", null);
		this.req += 1;
		this.openRequest = {
			run: this.run,
			turn: this.turn,
			req: this.req,
			model,
			thinking_level: thinkingLevel,
			// Reference only; serialized at close so the hook adds no latency
			// before the request goes out. pi builds a fresh params object per
			// call and does not mutate it after this point.
			payload,
			t_request: this.clock(),
			t_response: null,
			http_status: null,
			response_headers: null,
			t_first_delta: null,
			t_first_content: null,
			first_delta_type: null,
			n_deltas: 0,
		};
	}

	responseReceived(status: number, headers: Record<string, string>): void {
		const r = this.openRequest;
		if (!r) return;
		r.t_response = this.clock();
		r.http_status = status;
		r.response_headers = headers;
	}

	/** Hot path: called per streamed delta. Must stay O(1) and allocation-free after the first delta. */
	streamDelta(kind: DeltaKind): void {
		const r = this.openRequest;
		if (!r) return;
		r.n_deltas += 1;
		if (r.t_first_delta === null) {
			r.t_first_delta = this.clock();
			r.first_delta_type = kind;
		}
		if (r.t_first_content === null && kind !== "thinking") {
			r.t_first_content = this.clock();
		}
	}

	requestEnd(message: AssistantLike): void {
		const outcome: RequestOutcome =
			message.stopReason === "error" ? "error" : message.stopReason === "aborted" ? "aborted" : "done";
		this.finishOpenRequest(outcome, message);
	}

	// ── tools ──────────────────────────────────────────────────────────────

	toolStart(toolCallId: string, name: string, args: unknown): void {
		this.openTools.set(toolCallId, {
			run: this.run,
			turn: this.turn,
			name,
			args,
			t_start: this.clock(),
		});
	}

	toolEnd(toolCallId: string, name: string, result: unknown, isError: boolean): void {
		const tool = this.openTools.get(toolCallId);
		if (!tool) {
			// Start was missed (e.g. recorder attached mid-turn); still record what we have.
			this.finishTool(
				toolCallId,
				{ run: this.run, turn: this.turn, name, args: null, t_start: this.clock() },
				result,
				isError,
			);
			return;
		}
		this.finishTool(toolCallId, tool, result, isError);
	}

	// ── compaction ─────────────────────────────────────────────────────────

	compaction(input: Omit<CompactionRecord, "type" | "t" | "seq" | "run">): void {
		this.emit({ type: "compaction", run: this.run, ...input });
	}

	compactionFailed(input: Omit<CompactionFailedRecord, "type" | "t" | "seq" | "run">): void {
		this.emit({ type: "compaction_failed", run: this.run, ...input });
	}

	// ── internals ──────────────────────────────────────────────────────────

	private finishOpenRequest(outcome: RequestOutcome, message: AssistantLike | null): void {
		const r = this.openRequest;
		if (!r) return;
		this.openRequest = null;

		let payloadJson: string | null = null;
		let payloadError: string | undefined;
		try {
			payloadJson = JSON.stringify(r.payload) ?? null;
		} catch (err) {
			payloadError = err instanceof Error ? err.message : String(err);
		}

		this.emitWithT({
			type: "request",
			t: r.t_request,
			run: r.run,
			turn: r.turn,
			req: r.req,
			model: r.model,
			thinking_level: r.thinking_level,
			t_request: r.t_request,
			t_response: r.t_response,
			t_first_delta: r.t_first_delta,
			t_first_content: r.t_first_content,
			t_end: message ? this.clock() : null,
			http_status: r.http_status,
			response_headers: r.response_headers,
			first_delta_type: r.first_delta_type,
			n_deltas: r.n_deltas,
			outcome,
			stop_reason: message?.stopReason ?? null,
			error_message: message?.errorMessage ?? null,
			usage: message ? normalizeUsage(message.usage) : null,
			output: message ? digestOutput(message.content) : null,
			payload_sha256: payloadJson === null ? null : sha256(payloadJson),
			payload_chars: payloadJson === null ? null : payloadJson.length,
			payload: payloadJson === null ? null : r.payload,
			...(payloadError !== undefined ? { payload_error: payloadError } : {}),
		});
	}

	private finishTool(id: string, tool: OpenTool, result: unknown, isError: boolean | null): void {
		this.openTools.delete(id);
		this.nTools += 1;
		this.emitWithT({
			type: "tool",
			t: tool.t_start,
			run: tool.run,
			turn: tool.turn,
			tool_call_id: id,
			name: tool.name,
			t_start: tool.t_start,
			t_end: isError === null ? null : this.clock(),
			args: tool.args,
			args_chars: jsonChars(tool.args),
			result_chars: isError === null ? null : jsonChars(result),
			is_error: isError,
		});
	}

	/** Emit a record stamped with the current clock. */
	private emit(record: PendingRecord): void {
		this.emitWithT({ ...record, t: this.clock() } as UnsequencedRecord);
	}

	/** Emit a record that carries its own `t` (request/tool: the start time, not the write time). */
	private emitWithT(record: UnsequencedRecord): void {
		if (this.closed) return;
		const full = { ...record, seq: this.seq } as TraceRecord;
		this.seq += 1;
		this.sink.write(JSON.stringify(full));
	}
}

function normalizeUsage(usage: Partial<Usage> | undefined): Usage | null {
	if (!usage) return null;
	const out: Usage = {
		input: usage.input ?? 0,
		output: usage.output ?? 0,
		cacheRead: usage.cacheRead ?? 0,
		cacheWrite: usage.cacheWrite ?? 0,
		totalTokens: usage.totalTokens ?? 0,
	};
	if (typeof usage.cacheWrite1h === "number") out.cacheWrite1h = usage.cacheWrite1h;
	if (typeof usage.reasoning === "number") out.reasoning = usage.reasoning;
	return out;
}

function digestOutput(content: unknown[]): NonNullable<RequestRecord["output"]> {
	let textChars = 0;
	let thinkingChars = 0;
	const toolCalls: ToolCallDigest[] = [];
	for (const block of content) {
		const b = block as { type?: unknown; text?: unknown; thinking?: unknown; id?: unknown; name?: unknown; arguments?: unknown };
		if (b.type === "text" && typeof b.text === "string") textChars += b.text.length;
		else if (b.type === "thinking" && typeof b.thinking === "string") thinkingChars += b.thinking.length;
		else if (b.type === "toolCall") {
			toolCalls.push({
				id: typeof b.id === "string" ? b.id : "",
				name: typeof b.name === "string" ? b.name : "",
				args_chars: jsonChars(b.arguments),
			});
		}
	}
	return { content, text_chars: textChars, thinking_chars: thinkingChars, tool_calls: toolCalls };
}
