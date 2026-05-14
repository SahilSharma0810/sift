# Sift

Vendor invoices in mixed formats → clean, structured data an AP clerk can review and query.

> Built for the Zamp Engineering Project Round (Problem 01).
> See [CONTEXT.md](./CONTEXT.md) for domain language and [PLAN.md](./PLAN.md) for the 5-day execution plan.
> Architecture decisions live in [docs/adr/](./docs/adr/).

---

## Quick start (no API key required)

```bash
git clone <this repo>
cd sift
cp .env.example .env       # defaults are safe for local dev — no key needed
make dev                   # docker compose up backend + frontend + Postgres
open http://localhost:5173
```

Drop a PDF on the inbox. The pipeline runs end-to-end with **zero external API calls** — the default `SIFT_LLM_PROVIDER=stub` setting routes every LLM call through `StubLLMClient`, which returns deterministic canned extractions that exercise the full cascade (Haiku → Sonnet → Opus → agreement-score override). Useful for:

- Reviewing the codebase without spending anything
- Running the demo on a flight / offline
- CI: every test runs offline against the stub

Switch to real model calls by editing `.env`:

```env
SIFT_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

The architecture documents the swap as a single setting change — see ADR-0005 (`adapters/llm_client.py` Protocol + factory). Adding an OpenAI or local provider is a new implementation class + one factory branch.

## Stub-mode scenarios

`StubLLMClient` ships with three keyword-keyed scenarios so the demo narrative still works without keys:

| Keyword in invoice text | Scenario | Drives demo beat |
|---|---|---|
| `halcyon`            | Halcyon Software, $34,062.50 | Vendor anomaly (large value vs history) |
| `bramble`            | Bramble Catering, $750.00    | Near-duplicate review |
| `[stub:fail]` / `encrypted` | extraction_failed=True | Unprocessable + retry |
| (anything else)      | Vega Logistics, $1,180.00    | Cascade + agreement-override |

Every scenario returns a `total` that's off by $1 on tier-1 (Haiku) vs tier-2 (Sonnet) so the cascade actually fires and the trace shows real disagreement / agreement-override behavior. Different invoice text → different invoice numbers (seeded from SHA-256), so multiple uploads in stub mode show as distinct rows.

---

This README is still a placeholder for the rest of the project narrative. The real README ships on Day 5 with the 60-second demo story, architecture diagram, eval numbers, and live URL.
