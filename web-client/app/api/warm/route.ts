// Pre-warm: open (and cache) the MCP connection when a user lands on the page,
// so a sleeping hosted MCP server is already awake by the time they ask their
// first question. Best-effort — never surfaces an error to the client.
import { getMcpClient } from "@/lib/mcp";

export const runtime = "nodejs";

export async function GET() {
  try {
    const client = await getMcpClient();
    await client.listTools();
    return Response.json({ status: "warm" });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json({ status: "cold", error: message });
  }
}
