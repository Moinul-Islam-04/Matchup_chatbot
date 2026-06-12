# LoL MCP Server

An MCP server exposing League of Legends data (Riot API + Data Dragon) as tools,
for use by a Claude-powered chatbot companion.

## Tools

| Tool | Status | Description |
|------|--------|-------------|
| `get_champion_info(champion_name)` | ✅ | Base stats, abilities, powerspike/matchup context (Data Dragon — no API key needed) |
| `get_item_info(item_name)` | ✅ | Cost, build path, stats, and effects (Data Dragon) |
| `get_rune_info(rune_name)` | ✅ | Tree, keystone status, and effect text (Data Dragon) |
| `get_live_match_context(summoner_name, tag_line)` | ✅ | Current match teams, champions & bans by Riot ID (Riot Spectator API — needs `RIOT_API_KEY`) |

## Setup

```powershell
cd lol-mcp-server
uv sync                       # create venv + install deps
Copy-Item .env.example .env   # fill in RIOT_API_KEY later (not needed for champion info)
```

## Run (stdio)

```powershell
uv run lol-mcp-server
```

The server speaks the MCP **stdio** transport: JSON-RPC on stdout, logs on stderr.

## Run (Streamable HTTP — for deployment)

```powershell
$env:MCP_TRANSPORT="http"; $env:PORT="8000"; uv run lol-mcp-server
# → MCP endpoint at http://0.0.0.0:8000/mcp/
```

Or via Docker (used for Render/Railway/Fly):

```bash
docker build -t lol-mcp-server .
docker run -e RIOT_API_KEY=RGAPI-... -p 8000:8000 lol-mcp-server
```

`MCP_TRANSPORT` selects the transport (`stdio` default, `http` for deployment);
`HOST`/`PORT`/`MCP_PATH` configure the HTTP listener (`PORT` falls back to the
platform's injected `$PORT`). HTTP mode is stateless.

## Inspect (Phase 2)

```powershell
npx @modelcontextprotocol/inspector uv run lol-mcp-server
```

## Layout

```
lol-mcp-server/
├─ pyproject.toml
├─ .env.example
└─ src/lol_mcp_server/
   ├─ server.py          # FastMCP app + tool registrations (entrypoint)
   ├─ config.py          # env-driven Config
   ├─ logging_setup.py   # stderr-only logging (protects stdio JSON-RPC)
   ├─ data_dragon.py     # Data Dragon client + TTL cache
   └─ formatting.py      # raw payload -> LLM-friendly markdown
```
