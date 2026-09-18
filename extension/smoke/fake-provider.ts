import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
export default function (pi: ExtensionAPI) {
  pi.registerProvider("fake", {
    name: "Fake",
    baseUrl: "http://127.0.0.1:18080/v1",
    apiKey: "fake-key",
    api: "openai-completions",
    models: [{ id: "fake-1", name: "Fake 1", reasoning: false, input: ["text"], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 32000, maxTokens: 1024 }],
  });
}
