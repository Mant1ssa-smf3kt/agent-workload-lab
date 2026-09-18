import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

/** Destination for trace lines. Implementations must never throw out of `write`. */
export interface Sink {
	write(line: string): void;
	close(): void;
}

/**
 * Append-only JSONL file. Synchronous writes keep records ordered and durable
 * even if the process dies mid-session; per-request cost is a few ms, which is
 * negligible next to model and tool time.
 *
 * On the first write failure the sink disables itself and reports once via
 * `onError`; recording must never take down the agent session.
 */
export class JsonlFileSink implements Sink {
	private disabled = false;

	constructor(
		readonly path: string,
		private readonly onError: (err: unknown) => void = (err) => {
			process.stderr.write(`[pi-trace-recorder] write failed, recording disabled: ${String(err)}\n`);
		},
	) {
		try {
			mkdirSync(dirname(path), { recursive: true });
		} catch (err) {
			this.disabled = true;
			this.onError(err);
		}
	}

	write(line: string): void {
		if (this.disabled) return;
		try {
			appendFileSync(this.path, `${line}\n`, "utf8");
		} catch (err) {
			this.disabled = true;
			this.onError(err);
		}
	}

	close(): void {
		this.disabled = true;
	}

	get isDisabled(): boolean {
		return this.disabled;
	}
}

/** In-memory sink for tests. */
export class MemorySink implements Sink {
	readonly lines: string[] = [];
	closed = false;

	write(line: string): void {
		this.lines.push(line);
	}

	close(): void {
		this.closed = true;
	}

	records(): unknown[] {
		return this.lines.map((l) => JSON.parse(l) as unknown);
	}
}
