// Drives the running dev server (http://localhost:3000) with a headless browser,
// asks each question, waits for the streamed answer to settle, and saves a
// full-page screenshot to ../docs/screenshots/.
import { chromium } from "playwright";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "..", "..", "docs", "screenshots");
fs.mkdirSync(outDir, { recursive: true });

const questions = [
  {
    file: "matchup-graves-diana.png",
    text: "I'm playing Graves vs Diana jungle. When does she powerspike and what should I build?",
  },
  {
    file: "champion-thresh.png",
    text: "Quick — what's Thresh's hook (Q) cooldown and his main engage combo?",
  },
  {
    file: "poke-lane-caitlyn.png",
    text: "I'm Caitlyn into a Zeri + Lulu bot lane. How do I play it and when do I spike?",
  },
];

const BASE = process.env.BASE_URL ?? "http://localhost:3000";

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 820, height: 1100 },
  deviceScaleFactor: 2,
});

for (const q of questions) {
  console.error(`\n→ ${q.text}`);
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.fill("textarea", q.text);
  await page.click('.composer button');

  // Wait until the last assistant bubble stops growing for ~2s (stream done).
  await page.waitForFunction(
    () => {
      const bubbles = document.querySelectorAll(".bubble.assistant");
      const last = bubbles[bubbles.length - 1];
      if (!last) return false;
      const txt = last.textContent ?? "";
      if (txt.length < 40) return false;
      const w = window;
      if (w.__lastLen === txt.length) {
        w.__stableSince = w.__stableSince ?? Date.now();
        return Date.now() - w.__stableSince > 2000;
      }
      w.__lastLen = txt.length;
      w.__stableSince = Date.now();
      return false;
    },
    { timeout: 120000, polling: 400 },
  );

  // Expand the fixed-height layout so the full conversation is captured.
  await page.addStyleTag({
    content: ".app{height:auto !important} .messages{overflow:visible !important}",
  });
  await page.waitForTimeout(300);

  const dest = path.join(outDir, q.file);
  await page.screenshot({ path: dest, fullPage: true });
  console.error(`  saved ${dest}`);
}

await browser.close();
console.error("\nDone.");
