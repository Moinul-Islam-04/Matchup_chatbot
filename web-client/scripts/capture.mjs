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
  await page.click(".composer button");

  // The textarea is disabled while busy — wait for busy→true then busy→false,
  // which is the true completion signal (text-stability falsely triggers during
  // tool-call pauses).
  await page
    .waitForSelector(".composer textarea[disabled]", { timeout: 10000 })
    .catch(() => {});
  await page.waitForSelector(".composer textarea:not([disabled])", {
    timeout: 150000,
  });
  await page.waitForTimeout(1000); // let icons finish loading

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
