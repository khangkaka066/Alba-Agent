/** Reads a text/event-stream response and reports each complete event until the stream ends or is aborted. */
export async function readSse(response: Response, onMessage: (event: string, data: string) => void, signal: AbortSignal): Promise<void> {
  if (!response.ok || !response.body) throw new Error(`Stream unavailable (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      const event = block.split("\n").find((line) => line.startsWith("event:"))?.slice(6).trim() ?? "message";
      const data = block.split("\n").filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
      if (data) onMessage(event, data);
      boundary = buffer.indexOf("\n\n");
    }
  }
  await reader.cancel().catch(() => undefined);
}
