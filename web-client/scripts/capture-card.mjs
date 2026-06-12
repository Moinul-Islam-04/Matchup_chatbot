// Verifies the live-match card UI by mocking the /api/chat SSE response with a
// synthetic match payload (no live game needed), then screenshots the result.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(__dirname, "..", "..", "docs", "screenshots", "live-match-card.png");

const match = {
  queue: "Ranked Solo/Duo",
  gameLengthSec: 754,
  teams: [
    {
      side: "Blue side",
      players: [
        { champion: "Zeri", riotId: "PinkWard#NA1", isJungle: false, isYou: false, rank: "Master · 91 LP" },
        { champion: "Lee Sin", riotId: "BORK#NA1", isJungle: true, isYou: false, rank: "Emerald IV · 0 LP" },
        { champion: "Akshan", riotId: "Alyeska#NA1", isJungle: false, isYou: false, rank: "Master · 249 LP" },
        { champion: "Lulu", riotId: "GuyuY#NA1", isJungle: false, isYou: false, rank: "Master · 159 LP" },
        { champion: "Jayce", riotId: "MCJIMIN#NA1", isJungle: false, isYou: false, rank: "Master · 309 LP" },
      ],
    },
    {
      side: "Red side",
      players: [
        { champion: "Veigar", riotId: "I love Booba#Bbali", isJungle: false, isYou: true, rank: "Master · 210 LP" },
        { champion: "Rek'Sai", riotId: "Hextech Man#NA1", isJungle: true, isYou: false, rank: "Master · 22 LP" },
        { champion: "Shaco", riotId: "Splasher#NA1", isJungle: false, isYou: false, rank: "Master · 45 LP" },
        { champion: "Karma", riotId: "exar kun#NA1", isJungle: false, isYou: false, rank: "Master · 147 LP" },
        { champion: "Graves", riotId: "Anilist#NA1", isJungle: false, isYou: false, rank: "Diamond I · 75 LP" },
      ],
    },
  ],
  bans: ["Yasuo", "Kassadin", "Yone"],
};

const sse =
  `event: tool\ndata: ${JSON.stringify({ name: "get_live_match_context" })}\n\n` +
  `event: match\ndata: ${JSON.stringify(match)}\n\n` +
  `event: text\ndata: ${JSON.stringify({ delta: "You're on **Veigar** (red side), bot lane. Biggest threats: **Rek'Sai** + **Shaco** is a scary early gank duo, and **Akshan** snowballs. Which lane are you? I'll break down the matchup." })}\n\n` +
  `event: done\ndata: {}\n\n`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 820, height: 1000 }, deviceScaleFactor: 2 });

await page.route("**/api/chat", (route) =>
  route.fulfill({ status: 200, contentType: "text/event-stream; charset=utf-8", body: sse }),
);

await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.fill("textarea", "is I love Booba#Bbali in a game? show me the lobby");
await page.click(".composer button");
await page.waitForSelector(".mc-card", { timeout: 15000 });
await page.waitForTimeout(1200); // let icons load
await page.addStyleTag({ content: ".app{height:auto !important} .messages{overflow:visible !important}" });
await page.screenshot({ path: out, fullPage: true });
console.error("saved " + out);
await browser.close();
