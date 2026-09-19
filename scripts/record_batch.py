"""Drive pi over RPC to record trajectories unattended.

Tasks come straight from docs/recording-tasks.md: every ``### tNN · <repo> · …`` section
contributes its ``bash scripts/record.sh <repo-path> <id>`` line (repo) and its blockquote
paragraphs, in order, as the prompts of one session. One pi process per task, so each task
yields exactly one trace file with real multi-run structure (a synthetic "human think gap"
separates prompts).

    uv run python scripts/record_batch.py t06 t07          # these tasks
    uv run python scripts/record_batch.py --pending        # every task without a trace yet
    uv run python scripts/record_batch.py --dry-run --all  # just show the plan

Costs cloud tokens (zai). Does not need the GPU box.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "recording-tasks.md"
EXT = ROOT / "extension" / "src" / "index.ts"
TRACES = Path(os.environ.get("AWL_TRACE_DIR", ROOT / "traces"))
REC_DIR = Path(os.environ.get("AWL_REC_DIR", Path.home() / "awl-rec"))
MODEL = os.environ.get("AWL_RECORD_MODEL", "zai/glm-5.2:off")


def log(msg: str, **fields: Any) -> None:
    sys.stderr.write(
        json.dumps({"ts": round(time.time(), 3), "msg": msg, **fields}, ensure_ascii=False) + "\n"
    )


# ── task parsing ──────────────────────────────────────────────────────────


@dataclass
class Task:
    id: str
    repo: Path
    title: str
    prompts: list[str] = field(default_factory=list)


HEADER = re.compile(r"^### (t\d{2}) · (.+)$")
RECORD_LINE = re.compile(r"^bash scripts/record\.sh (\S+) (t\d{2})\s*$")


def parse_tasks(doc: Path) -> list[Task]:
    tasks: list[Task] = []
    cur: Task | None = None
    quote: list[str] = []

    def flush_quote() -> None:
        nonlocal quote
        if cur is not None and quote:
            cur.prompts.append("\n".join(quote).strip())
        quote = []

    for line in doc.read_text(encoding="utf-8").splitlines():
        m = HEADER.match(line)
        if m:
            flush_quote()
            cur = Task(id=m.group(1), repo=Path(), title=m.group(2).strip())
            tasks.append(cur)
            continue
        if line.startswith("## ") or line.startswith("### 复核"):
            flush_quote()
            cur = None
            continue
        if cur is None:
            continue
        rm = RECORD_LINE.match(line.strip())
        if rm:
            cur.repo = Path(rm.group(1)).expanduser()
            continue
        if line.startswith(">"):
            quote.append(line[1:].strip())
        else:
            flush_quote()
    flush_quote()
    return [t for t in tasks if t.prompts and t.repo != Path()]


# ── trace bookkeeping ─────────────────────────────────────────────────────


def recorded_ids() -> set[str]:
    """Task ids that already have a trace (header.cwd ends with <repo>-<id>)."""
    done: set[str] = set()
    for p in TRACES.glob("*.jsonl"):
        try:
            with p.open(encoding="utf-8") as f:
                header = json.loads(f.readline())
            m = re.search(r"-(t\d{2})$", header.get("cwd", ""))
            if m:
                done.add(m.group(1))
        except (OSError, json.JSONDecodeError):
            continue
    return done


def newest_trace(since: float) -> Path | None:
    cands = [p for p in TRACES.glob("*.jsonl") if p.stat().st_mtime >= since]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


# ── worktree ──────────────────────────────────────────────────────────────


def worktree_add(repo: Path, task_id: str) -> Path:
    wt = REC_DIR / f"{repo.name}-{task_id}"
    if wt.exists():
        return wt
    REC_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), "HEAD"],
        check=True,
        capture_output=True,
    )
    return wt


def worktree_remove(repo: Path, wt: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)


# ── pi RPC session ────────────────────────────────────────────────────────


class PiSession:
    def __init__(self, cwd: Path, name: str, extra_args: list[str]) -> None:
        cmd = [
            "pi",
            "--mode",
            "rpc",
            "-e",
            str(EXT),
            "--trace-dir",
            str(TRACES),
            "--model",
            MODEL,
            "--name",
            name,
            *extra_args,
        ]
        self.proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.events: Queue[dict[str, Any]] = Queue()
        self.stderr_tail: list[str] = []
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        self.turns = 0
        self.tool_calls = 0
        self.errors: list[str] = []

    def _pump_stdout(self) -> None:
        assert self.proc.stdout is not None
        for raw in self.proc.stdout:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                self.events.put({"type": "_unparsed", "line": line[:200]})
        self.events.put({"type": "_eof"})

    def _pump_stderr(self) -> None:
        assert self.proc.stderr is not None
        for raw in self.proc.stderr:
            self.stderr_tail = [*self.stderr_tail, raw.rstrip()][-20:]

    def send(self, cmd: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(cmd, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def prompt_and_settle(self, message: str, timeout_s: float) -> bool:
        """Send a prompt; return True once agent_settled arrives (False on timeout/EOF)."""
        self.send({"type": "prompt", "message": message})
        deadline = time.time() + timeout_s
        while True:
            try:
                ev = self.events.get(timeout=max(0.1, min(5.0, deadline - time.time())))
            except Empty:
                if time.time() >= deadline:
                    return False
                continue
            t = ev.get("type")
            if t == "agent_settled":
                return True
            if t == "_eof":
                return False
            if t == "turn_end":
                self.turns += 1
            elif t == "tool_execution_start":
                self.tool_calls += 1
            elif t == "extension_error":
                self.errors.append(str(ev.get("error"))[:200])
            elif t == "extension_ui_request" and ev.get("method") in ("select", "confirm", "input", "editor"):
                # never block on a dialog while unattended
                self.send({"type": "extension_ui_response", "id": ev.get("id"), "cancelled": True})
            elif t == "response" and ev.get("success") is False:
                self.errors.append(f"prompt rejected: {ev.get('error')}")
                return False
            if time.time() >= deadline:
                return False

    def close(self, timeout_s: float = 60.0) -> int | None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            return self.proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                return self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                return self.proc.wait()


# ── driver ────────────────────────────────────────────────────────────────


def run_task(
    task: Task,
    gap_range: tuple[float, float],
    settle_timeout_s: float,
    extra_args: list[str],
    keep_worktree: bool,
) -> dict[str, Any]:
    rng = random.Random(f"{task.id}:{MODEL}")
    wt = worktree_add(task.repo, task.id)
    started = time.time()
    log("task start", task=task.id, repo=str(task.repo), worktree=str(wt), prompts=len(task.prompts))
    sess = PiSession(wt, f"{task.repo.name}-{task.id}", extra_args)
    outcome = "ok"
    try:
        for i, prompt in enumerate(task.prompts):
            if i > 0:
                gap = rng.uniform(*gap_range)
                log("think gap", task=task.id, seconds=round(gap, 1))
                time.sleep(gap)
            t0 = time.time()
            ok = sess.prompt_and_settle(prompt, settle_timeout_s)
            log(
                "prompt done",
                task=task.id,
                i=i,
                settled=ok,
                seconds=round(time.time() - t0, 1),
                turns=sess.turns,
                tools=sess.tool_calls,
            )
            if not ok:
                outcome = "timeout_or_exit"
                break
    finally:
        rc = sess.close()
    trace = newest_trace(started)
    result = {
        "task": task.id,
        "outcome": outcome,
        "exit_code": rc,
        "prompts_sent": min(len(task.prompts), i + 1) if task.prompts else 0,
        "turns": sess.turns,
        "tool_calls": sess.tool_calls,
        "seconds": round(time.time() - started, 1),
        "trace": trace.name if trace else None,
        "extension_errors": sess.errors,
        "stderr_tail": sess.stderr_tail[-5:],
    }
    if not keep_worktree:
        worktree_remove(task.repo, wt)
    log("task end", **result)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="task ids, e.g. t06 t07")
    ap.add_argument("--all", action="store_true", help="every task in the doc")
    ap.add_argument("--pending", action="store_true", help="every task without a trace yet")
    ap.add_argument("--doc", type=Path, default=DOC)
    ap.add_argument(
        "--gap",
        type=float,
        nargs=2,
        default=(20.0, 45.0),
        metavar=("MIN", "MAX"),
        help="think gap seconds between prompts",
    )
    ap.add_argument(
        "--settle-timeout", type=float, default=1800.0, help="max seconds to wait for one prompt to settle"
    )
    ap.add_argument("--keep-worktree", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--pi-arg",
        action="append",
        default=[],
        help="extra pi CLI arg (repeatable), e.g. --pi-arg=-e --pi-arg=/x/fake-provider.ts",
    )
    args = ap.parse_args(argv)

    tasks = parse_tasks(args.doc)
    by_id = {t.id: t for t in tasks}
    done = recorded_ids()
    if args.all:
        selected = tasks
    elif args.pending:
        selected = [t for t in tasks if t.id not in done]
    else:
        missing = [i for i in args.ids if i not in by_id]
        if missing:
            log("unknown task ids", ids=missing, known=sorted(by_id))
            return 2
        selected = [by_id[i] for i in args.ids]
    if not selected:
        log("nothing to do", parsed=len(tasks), recorded=sorted(done))
        return 0

    for t in selected:
        log(
            "plan",
            task=t.id,
            title=t.title,
            repo=str(t.repo),
            prompts=len(t.prompts),
            already_recorded=t.id in done,
            first_prompt=t.prompts[0][:60],
        )
    if args.dry_run:
        return 0

    results = [
        run_task(t, tuple(args.gap), args.settle_timeout, args.pi_arg, args.keep_worktree) for t in selected
    ]
    bad = [r for r in results if r["outcome"] != "ok" or r["trace"] is None]
    log("batch done", tasks=len(results), failed=[r["task"] for r in bad])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
