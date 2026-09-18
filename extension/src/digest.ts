import { createHash } from "node:crypto";

import type { MessageDigest } from "./schema.ts";

/**
 * Deterministic JSON: object keys sorted recursively, arrays in order.
 * Same content → same string regardless of insertion order, so hashes are
 * comparable across turns even if pi rebuilds message objects.
 */
export function stableStringify(value: unknown): string {
	return JSON.stringify(sortKeys(value));
}

function sortKeys(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(sortKeys);
	if (value !== null && typeof value === "object") {
		const out: Record<string, unknown> = {};
		for (const key of Object.keys(value as Record<string, unknown>).sort()) {
			out[key] = sortKeys((value as Record<string, unknown>)[key]);
		}
		return out;
	}
	return value;
}

export function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

/**
 * Minimal structural view of a pi AgentMessage. We only read fields that
 * exist on every role; everything else is optional and probed defensively so
 * a new message role never breaks recording.
 */
interface MessageLike {
	role?: unknown;
	content?: unknown;
	toolName?: unknown;
	toolCallId?: unknown;
	isError?: unknown;
	timestamp?: unknown;
}

export function digestMessage(message: unknown, index: number): MessageDigest {
	const json = stableStringify(message);
	const m = (message ?? {}) as MessageLike;
	const digest: MessageDigest = {
		i: index,
		role: typeof m.role === "string" ? m.role : "unknown",
		sha256: sha256(json),
		chars: json.length,
		kinds: contentKinds(m.content),
	};
	if (typeof m.toolName === "string") digest.tool_name = m.toolName;
	if (typeof m.toolCallId === "string") digest.tool_call_id = m.toolCallId;
	if (typeof m.isError === "boolean") digest.is_error = m.isError;
	if (typeof m.timestamp === "number") digest.timestamp = m.timestamp;
	return digest;
}

function contentKinds(content: unknown): string[] {
	if (!Array.isArray(content)) return [];
	const kinds: string[] = [];
	for (const block of content) {
		const type = (block as { type?: unknown } | null)?.type;
		if (typeof type === "string" && !kinds.includes(type)) kinds.push(type);
	}
	return kinds;
}

/** JSON length of a value; falls back to String() for unserializable input. */
export function jsonChars(value: unknown): number {
	try {
		const s = JSON.stringify(value);
		return s === undefined ? 0 : s.length;
	} catch {
		return String(value).length;
	}
}
