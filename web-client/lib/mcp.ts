import path from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type Anthropic from "@anthropic-ai/sdk";

/**
 * Singleton MCP client connected to the LoL MCP server.
 *
 * Two transports, chosen by env:
 *   - LOL_MCP_URL set  → connect over Streamable HTTP to a hosted server
 *     (the deployment path: client and server run as separate services).
 *   - otherwise        → spawn `uv run lol-mcp-server` as a child process and
 *     speak JSON-RPC over its stdin/stdout (the local-dev path).
 *
 * The connection is cached on globalThis so Next.js's dev-mode module reloads
 * don't reconnect (or respawn the Python process) on every request.
 */

type McpGlobal = { lolMcpClient?: Promise<Client> };
const g = globalThis as unknown as McpGlobal;

export function getMcpClient(): Promise<Client> {
  if (!g.lolMcpClient) {
    g.lolMcpClient = connect();
  }
  return g.lolMcpClient;
}

async function connect(): Promise<Client> {
  const client = new Client(
    { name: "lol-web-client", version: "0.1.0" },
    { capabilities: {} },
  );

  // Hosted server over Streamable HTTP. LOL_MCP_URL is the full endpoint; as a
  // convenience LOL_MCP_HOST lets a host (e.g. a Render blueprint) inject just
  // the server's hostname and we build the https URL from it.
  const url =
    process.env.LOL_MCP_URL ??
    (process.env.LOL_MCP_HOST ? `https://${process.env.LOL_MCP_HOST}/mcp/` : undefined);
  if (url) {
    const token = process.env.LOL_MCP_TOKEN;
    const transport = new StreamableHTTPClientTransport(
      new URL(url),
      token
        ? { requestInit: { headers: { Authorization: `Bearer ${token}` } } }
        : undefined,
    );
    await client.connect(transport);
    return client;
  }

  // Local dev: spawn the Python server over stdio.
  const serverDir = path.resolve(
    process.cwd(),
    process.env.LOL_MCP_DIR ?? "../lol-mcp-server",
  );
  const command = process.env.LOL_MCP_COMMAND ?? "uv";
  const args = (process.env.LOL_MCP_ARGS ?? "run lol-mcp-server").split(" ");

  const transport = new StdioClientTransport({
    command,
    args,
    cwd: serverDir,
    // Inherit the parent env so RIOT_API_KEY etc. from the server's own .env
    // (loaded by the Python process) are available; stderr is surfaced for logs.
    stderr: "inherit",
  });
  await client.connect(transport);
  return client;
}

/** Fetch the server's tools and convert them to Anthropic tool definitions. */
export async function getAnthropicTools(): Promise<Anthropic.Tool[]> {
  const client = await getMcpClient();
  const { tools } = await client.listTools();
  return tools.map((t) => ({
    name: t.name,
    description: t.description ?? "",
    input_schema: t.inputSchema as Anthropic.Tool.InputSchema,
  }));
}

/** Execute an MCP tool call and flatten its result to a string for Claude. */
export async function callMcpTool(
  name: string,
  input: Record<string, unknown>,
): Promise<{ text: string; isError: boolean }> {
  const client = await getMcpClient();
  try {
    const result = await client.callTool({ name, arguments: input });
    const content = (result.content ?? []) as Array<{
      type: string;
      text?: string;
    }>;
    const text = content
      .filter((c) => c.type === "text")
      .map((c) => c.text ?? "")
      .join("\n")
      .trim();
    return { text: text || "(tool returned no text)", isError: Boolean(result.isError) };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { text: `Tool '${name}' failed: ${message}`, isError: true };
  }
}
