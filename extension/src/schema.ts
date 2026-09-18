/**
 * Trace file schema.
 *
 * One JSONL file per pi session. Every line is one `TraceRecord`. Records are
 * appended in the order they are finalized, which matches event order except
 * that a `request` record lands only once its stream ends (after `context`,
 * before any `tool` record of the same turn).
 *
 * All `t*` fields are wall-clock Unix milliseconds from a single clock
 * (`Date.now()`), so intervals between any two records are directly
 * subtractable. `seq` is a per-file monotonic counter and is the tie-breaker.
 *
 * Bump `TRACE_SCHEMA_VERSION` on any breaking change and note it in
 * docs/decisions.md — replayer and analysis key off it.
 */

export const TRACE_SCHEMA_VERSION = 1;
export const EXTENSION_VERSION = "0.1.0";

export interface RecordBase {
	type: string;
	/** Wall-clock ms when the record's primary event happened. */
	t: number;
	/** Monotonic per-file counter, starting at 0 for the header. */
	seq: number;
}

export interface ModelInfo {
	provider: string;
	id: string;
	api: string;
	base_url: string;
	context_window: number;
	max_tokens: number;
	reasoning: boolean;
}

export interface HeaderRecord extends RecordBase {
	type: "header";
	schema: typeof TRACE_SCHEMA_VERSION;
	session_id: string;
	session_file: string | null;
	/** Why pi started this session: startup | reload | new | resume | fork. */
	session_reason: string;
	previous_session_file: string | null;
	cwd: string;
	hostname: string;
	platform: string;
	node_version: string;
	pi_version: string;
	extension_version: string;
	/** git HEAD of the repo containing the extension, or null if unavailable. */
	extension_git_commit: string | null;
	model: ModelInfo | null;
	thinking_level: string | null;
	trace_dir_source: "flag" | "env" | "default";
}

export interface ModelSelectRecord extends RecordBase {
	type: "model_select";
	source: string;
	model: ModelInfo;
	previous: ModelInfo | null;
}

export interface AgentStartRecord extends RecordBase {
	type: "agent_start";
	run: number;
}

export interface UserPromptRecord extends RecordBase {
	type: "user_prompt";
	run: number;
	prompt: string;
	prompt_chars: number;
	n_images: number;
	system_prompt_sha256: string;
	system_prompt_chars: number;
	/** Full text, present only the first time this sha256 is seen in the file. */
	system_prompt?: string;
}

export interface AgentEndRecord extends RecordBase {
	type: "agent_end";
	run: number;
	n_messages: number;
}

export interface AgentSettledRecord extends RecordBase {
	type: "agent_settled";
	run: number;
}

export interface TurnStartRecord extends RecordBase {
	type: "turn_start";
	run: number;
	/** pi's turnIndex; resets to 0 at each agent_start. */
	turn: number;
	/** Timestamp pi attached to the event (its own Date.now()). */
	pi_timestamp: number;
}

export interface TurnEndRecord extends RecordBase {
	type: "turn_end";
	run: number;
	turn: number;
	stop_reason: string | null;
	n_tool_results: number;
}

/** Per-message digest of the harness-level context (pi's AgentMessage[]). */
export interface MessageDigest {
	i: number;
	role: string;
	/** sha256 of the canonical (sorted-key) JSON of the whole message. */
	sha256: string;
	/** Length of that JSON — a cheap token-count proxy. */
	chars: number;
	/** Content block types present, e.g. ["text","toolCall"]. Empty for string content. */
	kinds: string[];
	tool_name?: string;
	tool_call_id?: string;
	is_error?: boolean;
	timestamp?: number;
}

/**
 * Snapshot of the context pi assembled for one LLM call, before provider
 * serialization. This is the harness-side view; the wire-side view is the
 * `payload` inside the matching `request` record.
 */
export interface ContextRecord extends RecordBase {
	type: "context";
	run: number;
	turn: number;
	n_messages: number;
	total_chars: number;
	messages: MessageDigest[];
}

export interface Usage {
	input: number;
	output: number;
	cacheRead: number;
	cacheWrite: number;
	cacheWrite1h?: number;
	reasoning?: number;
	totalTokens: number;
}

export interface ToolCallDigest {
	id: string;
	name: string;
	args_chars: number;
}

export type RequestOutcome = "done" | "error" | "aborted" | "superseded" | "unfinished";

/**
 * One provider request, from payload assembly to end of stream.
 *
 * Timing points, in order:
 *   t_request     before_provider_request fired (payload final, about to send)
 *   t_response    after_provider_response fired (HTTP headers received)
 *   t_first_delta first streamed delta of any kind (thinking included)
 *   t_first_content first text or toolcall delta (thinking excluded)
 *   t_end         assistant message finalized (message_end)
 * Any of them may be null if the request ended early.
 */
export interface RequestRecord extends RecordBase {
	type: "request";
	run: number;
	turn: number;
	/** Global request counter within the file, starting at 0. */
	req: number;
	model: ModelInfo | null;
	thinking_level: string | null;
	t_request: number;
	t_response: number | null;
	t_first_delta: number | null;
	t_first_content: number | null;
	t_end: number | null;
	http_status: number | null;
	response_headers: Record<string, string> | null;
	first_delta_type: string | null;
	n_deltas: number;
	outcome: RequestOutcome;
	stop_reason: string | null;
	error_message: string | null;
	usage: Usage | null;
	output: {
		content: unknown[];
		text_chars: number;
		thinking_chars: number;
		tool_calls: ToolCallDigest[];
	} | null;
	payload_sha256: string | null;
	payload_chars: number | null;
	/** The provider payload verbatim (what the serving side saw), or null if unserializable. */
	payload: unknown;
	payload_error?: string;
}

export interface ToolRecord extends RecordBase {
	type: "tool";
	run: number;
	turn: number;
	tool_call_id: string;
	name: string;
	t_start: number;
	t_end: number | null;
	args: unknown;
	args_chars: number;
	result_chars: number | null;
	is_error: boolean | null;
}

export interface CompactionRecord extends RecordBase {
	type: "compaction";
	run: number;
	reason: string;
	will_retry: boolean;
	from_extension: boolean;
	tokens_before: number;
	summary_chars: number;
	usage: Usage | null;
}

export interface CompactionFailedRecord extends RecordBase {
	type: "compaction_failed";
	run: number;
	reason: string;
	aborted: boolean;
	error_message: string | null;
}

export interface ShutdownRecord extends RecordBase {
	type: "shutdown";
	reason: string;
	n_runs: number;
	n_requests: number;
	n_tools: number;
}

/** `Omit` that distributes over a union instead of collapsing it to common keys. */
export type DistributiveOmit<T, K extends keyof never> = T extends unknown ? Omit<T, K> : never;

export type TraceRecord =
	| HeaderRecord
	| ModelSelectRecord
	| AgentStartRecord
	| UserPromptRecord
	| AgentEndRecord
	| AgentSettledRecord
	| TurnStartRecord
	| TurnEndRecord
	| ContextRecord
	| RequestRecord
	| ToolRecord
	| CompactionRecord
	| CompactionFailedRecord
	| ShutdownRecord;

/** A record before the recorder stamps it. */
export type PendingRecord = DistributiveOmit<TraceRecord, "t" | "seq">;
/** A record that carries its own `t` but no `seq` yet. */
export type UnsequencedRecord = DistributiveOmit<TraceRecord, "seq">;
