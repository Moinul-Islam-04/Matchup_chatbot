// Lightweight liveness probe for uptime pingers (keep-alive against free-tier
// spin-down) and platform health checks. Avoids rendering the full page.
export const runtime = "nodejs";

export async function GET() {
  return Response.json({ status: "ok", service: "lol-web-client" });
}
