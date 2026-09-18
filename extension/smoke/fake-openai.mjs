// Minimal OpenAI-compatible streaming server. Turn 1: emits a bash tool call.
// Turn 2 (after a tool result is present): emits plain text. Logs each request's message count.
import { createServer } from "node:http";
let n = 0;
const sse = (res, obj) => res.write(`data: ${JSON.stringify(obj)}\n\n`);
createServer((req, res) => {
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    if (req.url === "/v1/models") { res.setHeader("content-type","application/json"); return res.end(JSON.stringify({data:[{id:"fake-1"}]})); }
    const p = JSON.parse(body || "{}");
    n += 1;
    const hasToolResult = (p.messages ?? []).some((m) => m.role === "tool");
    process.stderr.write(`[fake] req#${n} messages=${p.messages?.length} tools=${p.tools?.length ?? 0} hasToolResult=${hasToolResult}\n`);
    res.writeHead(200, { "content-type": "text/event-stream", "x-fake-request-id": `fake-${n}` });
    const id = `chatcmpl-${n}`;
    const base = { id, object: "chat.completion.chunk", created: 1, model: "fake-1" };
    setTimeout(() => {
      if (!hasToolResult) {
        sse(res, { ...base, choices: [{ index: 0, delta: { role: "assistant", tool_calls: [{ index: 0, id: "call_1", type: "function", function: { name: "bash", arguments: "" } }] }, finish_reason: null }] });
        sse(res, { ...base, choices: [{ index: 0, delta: { tool_calls: [{ index: 0, function: { arguments: JSON.stringify({ command: "cat README.md" }) } }] }, finish_reason: null }] });
        sse(res, { ...base, choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }] });
      } else {
        sse(res, { ...base, choices: [{ index: 0, delta: { role: "assistant", content: "The README says " }, finish_reason: null }] });
        sse(res, { ...base, choices: [{ index: 0, delta: { content: "hello." }, finish_reason: null }] });
        sse(res, { ...base, choices: [{ index: 0, delta: {}, finish_reason: "stop" }] });
      }
      sse(res, { ...base, choices: [], usage: { prompt_tokens: 100 + n, completion_tokens: 12, total_tokens: 112 + n, prompt_tokens_details: { cached_tokens: 40 } } });
      res.write("data: [DONE]\n\n");
      res.end();
    }, 50);
  });
}).listen(18080, () => process.stderr.write("[fake] listening on 18080\n"));
