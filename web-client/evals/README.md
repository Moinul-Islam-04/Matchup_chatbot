# Response-quality evals

A lightweight harness to measure answer quality and catch regressions when you
change prompts or tools. It runs each question through the **real** pipeline
(`/api/chat` → Claude + MCP tools), then uses Claude as a judge to score the
answer against per-question criteria. Tool expectations are checked in code.

## Run

```bash
npm run dev      # in one terminal — the harness hits the running app
npm run eval     # in another
```

Env (optional): `BASE_URL` (default `http://localhost:3000`), `JUDGE_MODEL`
(default `claude-opus-4-8`). `ANTHROPIC_API_KEY` is read from `.env.local`.

## Output

A per-question report plus a summary line:

```
avg overall 5.00/5  |  criteria 30/30 (100%)  |  tool use 9/10
```

- **overall** — judge's 1–5 quality score per question.
- **criteria** — fraction of per-question rubric points the judge marked met.
- **tool use** — whether the expected MCP tools were actually called.

Failures print the unmet criteria with the judge's reasoning. Full structured
results are written to `evals/results.json`.

## Files

- `eval-set.json` — the questions, each with `criteria` (judged qualitatively)
  and optional `expectTools` (checked in code). Add cases here as you find gaps.
- `run.mjs` — the harness: drives the chat endpoint, judges, reports.

## Workflow (the "loop")

1. `npm run eval` to get a baseline.
2. Change a prompt or tool.
3. Re-run. Watch the score move and read the failing criteria.

## Caveats

- The judge is itself an LLM and can misjudge obscure game facts; the system
  prompt tells it to defer to the bot on specifics it's unsure of. Treat a
  single low score as a lead to investigate, not gospel.
- Quality answers can vary run-to-run (model non-determinism) — a flaky result
  often points to a real grounding gap (that's how the Graves melee/ranged bug
  was found).
