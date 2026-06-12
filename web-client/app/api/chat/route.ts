import Anthropic from "@anthropic-ai/sdk";
import { getAnthropicTools, callMcpTool } from "@/lib/mcp";

// The MCP stdio client spawns a child process, so this route must run on the
// Node.js runtime (not Edge).
export const runtime = "nodejs";
export const maxDuration = 60;

const MODEL = "claude-opus-4-8";

const SYSTEM_PROMPT = `You are a League of Legends companion that gives sharp, in-game advice.

You have tools to pull real data:
- get_champion_info: base stats, abilities (with cooldowns), and powerspike/matchup cues for a champion.
- get_live_match_context: the actual champions/teams in a player's current game (needs a Riot ID like "Name#TAG").

Guidance:
- When the user names champions, CALL get_champion_info to ground your advice in real cooldowns/stats — don't guess from memory.
- For "who am I against right now" style questions, use get_live_match_context.
- Be concise and practical: lead with the answer (powerspike timing, what to build, how to trade), then a brief why.
- Talk like a knowledgeable duo partner, not a wiki.

CRITICAL — live matches have NO lane data:
- get_live_match_context returns accurate champions and teams but Riot does NOT provide lane/role assignments. The ONLY role you can know is the jungler (the tool marks who has Smite).
- NEVER fabricate a top/mid/bot map or state a specific lane opponent. Do not assume a champion's "usual" lane — players pick champions off-role (e.g. Veigar bot, not mid).
- The asked-about player's champion is tagged \`<-- asked about\`. Identify it, then: list the full ENEMY team comp, call out the jungler and the biggest threats, and if the user wants their direct lane matchup, ASK which lane they're playing (or which enemy they're laning against) before breaking down a 1v1.`;

type ClientMessage = { role: "user" | "assistant"; content: string };

/** Unwrap Node/undici "fetch failed" wrappers to show the underlying cause. */
function describeError(err: unknown): string {
  if (!(err instanceof Error)) return String(err);
  const cause = (err as { cause?: unknown }).cause;
  if (cause && typeof cause === "object") {
    const code = "code" in cause ? String((cause as { code: unknown }).code) : "";
    const causeMsg = cause instanceof Error ? cause.message : "";
    const detail = [code, causeMsg].filter(Boolean).join(": ");
    if (detail) return `${err.message} (${detail})`;
  }
  return err.message;
}

export async function POST(req: Request) {
  if (!process.env.ANTHROPIC_API_KEY) {
    return new Response(
      JSON.stringify({ error: "ANTHROPIC_API_KEY is not set in .env.local" }),
      { status: 500, headers: { "content-type": "application/json" } },
    );
  }

  const { messages: incoming } = (await req.json()) as { messages: ClientMessage[] };
  const anthropic = new Anthropic();

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = (event: string, data: unknown) =>
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`),
        );

      try {
        const tools = await getAnthropicTools();
        const messages: Anthropic.MessageParam[] = incoming.map((m) => ({
          role: m.role,
          content: m.content,
        }));

        // Agentic loop: keep calling the model, resolving tool calls via MCP,
        // until it stops asking for tools.
        for (let turn = 0; turn < 8; turn++) {
          const modelStream = anthropic.messages.stream({
            model: MODEL,
            max_tokens: 8000,
            thinking: { type: "adaptive" },
            output_config: { effort: "medium" },
            system: SYSTEM_PROMPT,
            tools,
            messages,
          });

          modelStream.on("text", (delta) => send("text", { delta }));

          const final = await modelStream.finalMessage();
          messages.push({ role: "assistant", content: final.content });

          if (final.stop_reason !== "tool_use") break;

          const toolResults: Anthropic.ToolResultBlockParam[] = [];
          for (const block of final.content) {
            if (block.type !== "tool_use") continue;
            send("tool", { name: block.name, input: block.input });
            const { text, isError } = await callMcpTool(
              block.name,
              (block.input ?? {}) as Record<string, unknown>,
            );
            toolResults.push({
              type: "tool_result",
              tool_use_id: block.id,
              content: text,
              is_error: isError,
            });
          }
          messages.push({ role: "user", content: toolResults });
        }

        send("done", {});
      } catch (err) {
        // "fetch failed" hides the real reason in err.cause — surface it.
        console.error("[/api/chat] error:", err);
        send("error", { message: describeError(err) });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
    },
  });
}
