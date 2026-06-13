// Response-quality eval harness.
//
// Runs each question in eval-set.json through the real /api/chat pipeline
// (Claude + MCP tools), then uses Claude as a judge to score the answer against
// per-question criteria. Tool expectations are checked programmatically.
//
//   1. Start the app:   npm run dev   (in another terminal)
//   2. Run the evals:    npm run eval
//
// Env: BASE_URL (default http://localhost:3000), JUDGE_MODEL (default
// claude-opus-4-8). ANTHROPIC_API_KEY is read from .env.local automatically.

import Anthropic from "@anthropic-ai/sdk";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// --- load ANTHROPIC_API_KEY from .env.local (node scripts don't auto-load it) -
try {
  const env = readFileSync(path.resolve(__dirname, "..", ".env.local"), "utf8");
  for (const line of env.split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2];
  }
} catch {
  /* fall back to ambient env */
}

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const JUDGE_MODEL = process.env.JUDGE_MODEL ?? "claude-opus-4-8";
const CONCURRENCY = 3;

const anthropic = new Anthropic();
const evalSet = JSON.parse(
  readFileSync(path.resolve(__dirname, "eval-set.json"), "utf8"),
);

// --- run one question through the real chat endpoint ------------------------
async function ask(question) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages: [{ role: "user", content: question }] }),
  });
  if (!res.ok || !res.body) throw new Error(`chat HTTP ${res.status}`);

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let answer = "";
  const tools = [];

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const events = buf.split("\n\n");
    buf = events.pop() ?? "";
    for (const evt of events) {
      const em = evt.match(/^event: (.+)$/m);
      const dm = evt.match(/^data: (.+)$/m);
      if (!em || !dm) continue;
      const type = em[1];
      const data = JSON.parse(dm[1]);
      if (type === "text") answer += data.delta;
      else if (type === "tool") tools.push(data.name);
      else if (type === "error") throw new Error(`chat error: ${data.message}`);
    }
  }
  return { answer: answer.trim(), tools };
}

// --- LLM judge --------------------------------------------------------------
const JUDGE_SYSTEM = `You are a strict QA judge for a League of Legends advice chatbot.
Given a user question, evaluation criteria, the bot's answer, and which data tools it
called, decide for EACH criterion whether it is met. Be strict and evidence-based:
- Only judge from the provided answer — do not assume facts it didn't state.
- A grounding/accuracy criterion is met only if the specifics are correct and plausibly
  tool-derived (the bot has live champion/item/rune/rank data).
- The bot has authoritative, up-to-date game data and you may NOT. Do not mark a criterion
  unmet merely because a champion/item/rune specific is unfamiliar to you — only mark it
  unmet if the answer is internally inconsistent or states something you are highly
  confident is wrong. When unsure about a domain fact, give the bot the benefit of the doubt.
- Reward honesty about limitations; penalize fabrication (fake champions, invented lanes,
  made-up numbers).
Then give an overall 1-5 quality score (5 = excellent, 1 = wrong or fabricated).`;

const JUDGE_SCHEMA = {
  type: "object",
  properties: {
    criteria: {
      type: "array",
      items: {
        type: "object",
        properties: {
          criterion: { type: "string" },
          met: { type: "boolean" },
          reason: { type: "string" },
        },
        required: ["criterion", "met", "reason"],
        additionalProperties: false,
      },
    },
    overall: { type: "integer", description: "1-5 overall quality" },
    summary: { type: "string" },
  },
  required: ["criteria", "overall", "summary"],
  additionalProperties: false,
};

async function judge(q, answer, tools) {
  const resp = await anthropic.messages.create({
    model: JUDGE_MODEL,
    max_tokens: 1500,
    system: JUDGE_SYSTEM,
    output_config: { format: { type: "json_schema", schema: JUDGE_SCHEMA } },
    messages: [
      {
        role: "user",
        content: JSON.stringify(
          { question: q.question, criteria: q.criteria, toolsUsed: tools, answer },
          null,
          2,
        ),
      },
    ],
  });
  const text = resp.content.find((b) => b.type === "text")?.text ?? "{}";
  return JSON.parse(text);
}

// --- bounded-concurrency map ------------------------------------------------
async function pool(items, n, fn) {
  const out = new Array(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(n, items.length) }, async () => {
      while (next < items.length) {
        const i = next++;
        out[i] = await fn(items[i]);
      }
    }),
  );
  return out;
}

// --- main -------------------------------------------------------------------
const C = { green: "\x1b[32m", red: "\x1b[31m", dim: "\x1b[2m", gold: "\x1b[33m", reset: "\x1b[0m" };

console.error(`Running ${evalSet.length} evals against ${BASE} (judge: ${JUDGE_MODEL})…\n`);

const results = await pool(evalSet, CONCURRENCY, async (q) => {
  try {
    const { answer, tools } = await ask(q.question);
    const judgement = await judge(q, answer, tools);
    const expect = q.expectTools ?? [];
    const toolsOk = expect.every((t) => tools.includes(t));
    process.stderr.write(`  ✓ ${q.id}\n`);
    return { id: q.id, question: q.question, answer, tools, expect, toolsOk, judgement };
  } catch (e) {
    return { id: q.id, question: q.question, error: String(e) };
  }
});

// --- report -----------------------------------------------------------------
let totalCrit = 0;
let metCrit = 0;
let overallSum = 0;
let toolPass = 0;
let scored = 0;

console.log("\n" + "=".repeat(64));
for (const r of results) {
  if (r.error) {
    console.log(`${C.red}✗ ${r.id}${C.reset}  ERROR: ${r.error}`);
    continue;
  }
  const crit = r.judgement.criteria;
  const met = crit.filter((c) => c.met).length;
  totalCrit += crit.length;
  metCrit += met;
  overallSum += r.judgement.overall;
  toolPass += r.toolsOk ? 1 : 0;
  scored++;

  const ovColor = r.judgement.overall >= 4 ? C.green : r.judgement.overall >= 3 ? C.gold : C.red;
  const toolMark = r.toolsOk ? `${C.green}tools ✓${C.reset}` : `${C.red}tools ✗${C.reset}`;
  console.log(
    `${ovColor}● ${r.id}${C.reset}  [${ovColor}${r.judgement.overall}/5${C.reset}]  criteria ${met}/${crit.length}  ${toolMark}  ${C.dim}(${r.tools.join(", ") || "none"})${C.reset}`,
  );
  for (const c of crit.filter((c) => !c.met)) {
    console.log(`    ${C.red}✗${C.reset} ${c.criterion} ${C.dim}— ${c.reason}${C.reset}`);
  }
  if (!r.toolsOk) {
    console.log(`    ${C.red}✗${C.reset} expected tools ${C.dim}${JSON.stringify(r.expect)} — got ${JSON.stringify(r.tools)}${C.reset}`);
  }
}

console.log("=".repeat(64));
if (scored) {
  console.log(
    `${C.gold}SCORE${C.reset}  avg overall ${(overallSum / scored).toFixed(2)}/5  |  ` +
      `criteria ${metCrit}/${totalCrit} (${Math.round((100 * metCrit) / totalCrit)}%)  |  ` +
      `tool use ${toolPass}/${scored}`,
  );
}

const outPath = path.resolve(__dirname, "results.json");
writeFileSync(outPath, JSON.stringify({ at: new Date().toISOString(), results }, null, 2));
console.log(`${C.dim}Full results → ${outPath}${C.reset}`);
