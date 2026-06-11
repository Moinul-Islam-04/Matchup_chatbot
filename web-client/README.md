# LoL Companion — Web Client

Next.js chat UI that runs a Claude tool-use loop and connects to the
[LoL MCP server](../lol-mcp-server) over **stdio** to resolve champion/live-match
data.

## Architecture

```
Browser (app/page.tsx)
   │  POST /api/chat  (SSE stream back)
   ▼
app/api/chat/route.ts  ── Claude agentic loop (claude-opus-4-8, adaptive thinking)
   │                         streams text + tool-call status events
   ▼
lib/mcp.ts  ── spawns `uv run lol-mcp-server` (stdio), bridges MCP tools → Anthropic tools
   ▼
../lol-mcp-server  (Python / FastMCP)  →  Riot API + Data Dragon
```

The MCP client is cached on `globalThis` so dev-mode reloads don't spawn a new
Python process per request.

## Setup

```powershell
cd web-client
npm install
Copy-Item .env.local.example .env.local   # then fill in ANTHROPIC_API_KEY
```

`.env.local` keys:
- `ANTHROPIC_API_KEY` — required.
- `LOL_MCP_COMMAND` / `LOL_MCP_ARGS` — how to launch the server (default `uv run lol-mcp-server`). On Windows, use the absolute `uv.exe` path if the spawn can't resolve `uv` from PATH.
- `LOL_MCP_DIR` — path to the Python server (default `../lol-mcp-server`).

## Run

```powershell
npm run dev    # http://localhost:3000
```

Ask things like *"I'm Graves vs Diana jungle — when does she spike and what do I build?"*
or *"Who is Revenge#Fake up against right now?"*.

## Notes

- `runtime = "nodejs"` on the route — the stdio MCP client needs `child_process`.
- The Riot key lives in the **Python server's** `.env`, not here.
