# Design Process Framework

_Started 2026-05-13 16:25 UTC_

---

## User

Based on all of this knowledge i want to create design and UX for this product don't directly jump to the solution first understand the problem statement understand the user who will use this and then build it UX according to that

## Assistant

_[tool: read_file]_

_[tool: read_file]_

_[tool: read_file]_

_[tool: read_file]_

_[tool: read_file]_

_[tool: read_file]_

_[tool: read_file]_

_[tool: read_file]_

_[tool: questions_v2]_

I've read through the implementation plan and all six ADRs. Before I design anything, let me play back what I understand, and then ask the questions I need to design well.

---

## The problem (as I understand it)

**Invoices are messy; AP work is brittle.** Vendor invoices arrive as digital PDFs, scans, photos — every vendor has its own layout, its own date format, its own way of breaking out tax. An AP clerk's day is:

1. **Open invoice** → manually retype the header (vendor, invoice #, date, subtotal, tax, total, currency) into the AP/ERP system.
2. **Sanity-check** → does the math reconcile? Is it a duplicate of one I keyed in last week? Is this vendor's total weirdly higher than usual?
3. **Approve or push back** → route for payment, or escalate.

The pain isn't typing — it's the **judgment work hidden inside the typing**. The clerk's real job is catching the math-errors, the duplicate, the new-vendor-let-me-look-again invoice. Existing tools either (a) dump LLM extractions on you with no signal of trust, so you re-read every field anyway, or (b) flag *everything* "needs review" and bury you.

**Sift's bet:** structured data + a *calibrated* confidence layer + per-vendor memory, so the clerk can blast through the `confident` pile in seconds and spend their attention only where it matters.

## The user

**Primary: the AP Clerk.** A few mental notes from the docs:

- They are **keyboard-fluent**, dense-table-tolerant, and process **dozens-to-hundreds of invoices per session**. Speed of the confident-path is the whole game.
- They are **risk-averse by training** — wrong invoice paid = real money. They will not trust a field unless they can see *why* the system thinks it's right (bbox highlight on the PDF, source of the value, confidence number, reason for any flag).
- They want **bulk operations with undo**, not one-at-a-time confirm clicks, for the easy stuff.
- When the LLM fails entirely (encrypted PDF, photo of a napkin, etc.) they still need a path — **manual entry inside Sift**, not "go open Excel."
- They will occasionally ask **analytical questions** ("how much did we spend with Vega last quarter?", "any duplicates from Acme this month?") — Cmd+K NL search needs to *feel* like real query power, not a chatbot toy.

**Secondary: the AP Lead / Finance Manager.** Glances at the inbox, runs ad-hoc queries, exports for the controller. Cares about audit trail and "what did we ask the system?"

## The non-negotiable design tensions

From the ADRs, four things are load-bearing for the UX:

1. **Confidence is composite, not LLM self-reported** (ADR-0003). A field can be `confident` because math reconciled, OR `needs_review` because it's two cents off. The UI has to surface the *specific reason*, not "model uncertain."
2. **Triage state ≠ review status** (ADR-0006). `predicted_triage_state` is the system's guess (Confident / Needs review / Likely duplicate / Unprocessable). `review_status` is what the clerk did (pending / confirmed / dismissed / unprocessable). The inbox needs both, distinguishably.
3. **Always-create-extraction-rows on failure** (ADR-0006). Even encrypted PDFs get a row. The Review screen has to handle the "extraction failed" case as a first-class layout, not a missing-data error state.
4. **Chips ARE the state for NL search** (ADR-0004). The Cmd+K box translates NL → typed chips → SQL. Chips are removable, editable; an "untranslated intent" sliver above the result list shows what got dropped.

---

Before I build, I want to lock the design system direction. A few quick questions:

## User

Questions timed out; go with defaults

## Assistant

_[tool: update_todos]_

Going with sensible defaults: **finance-tool serious** (dense, tabular, monospace numerics), one direction with Tweaks panel, hi-fi clickable React prototype, soft colored triage pills with numeric confidence, bidirectional bbox↔field hover, all in a single HTML file with sidebar navigation between Inbox / Review / Search.

_[tool: copy_starter_component]_

_[tool: write_file]_

Now the sample data file with all triage states represented:

_[tool: write_file]_

Now the primitives — TriagePill, ConfidenceBadge, SourceBadge, Chip, ReasonCard, etc:

_[tool: write_file]_

Now the PDF mockup component — fake invoice papers with bbox overlays for the bidirectional hover:

_[tool: write_file]_

Now the Inbox screen:

_[tool: write_file]_

Now the Review screen — the centerpiece of the prototype:

_[tool: write_file]_

Now the Search palette (Cmd+K) — NL→chips→results:

_[tool: write_file]_

Now the App shell, sidebar, and tweaks panel — and wire it all up:

_[tool: write_file]_

_[tool: grep]_

_[tool: grep]_

_[tool: read_file]_

_[tool: read_file]_

Good — TweakRadio options support `{value, label}` and TweakColor needs string colors. Let me fix the app.jsx:

_[tool: str_replace_edit]_

Now the main index.html that loads everything:

_[tool: write_file]_

_[tool: show_html]_

_[tool: done]_

_[tool: fork_verifier_agent]_

Built **Sift** as a working hi-fi prototype. The design starts from the problem, not the solution:

**Problem framing:** AP clerks aren't slow at typing — they're carrying the cognitive load of *judging* every invoice (math correct? duplicate? new vendor? anomaly?). Sift's job is to do the judgment, surface *why*, and let the clerk blow through the confident pile while spending real attention only on the flagged ones.

**What's in the prototype:**

- **Inbox** — table with status-filter tabs (Needs review · Confident · Duplicates · Unprocessable · Confirmed), upload zone, "Why" column with typed reason chips per row, keyboard shortcut hints.
- **Review screen** — split view: mocked invoice PDF on the left with **bidirectional bbox↔field hover** (hover a row → bbox highlights; hover the bbox → row highlights), fields panel on the right with composite confidence bars + source badges (Haiku / Sonnet / Opus / vendor memory / manual), typed reason cards (math fails, anomaly, duplicate, low confidence, missing field, unseen vendor, extraction failed), vendor memory card, and cascade trace.
- **Reason cards** — each typed reason has its own card layout and contextual actions (e.g. "Edit total / Re-extract" for math fails, "Open original / Mark duplicate" for duplicates, "Force Opus" for low confidence).
- **Manual entry mode** — encrypted PDFs land in a first-class failure layout with a manual-entry path so the clerk never dead-ends.
- **⌘K Search palette** — NL input that translates to typed chips with the "untranslated intent" amber notice when something gets dropped (per ADR-0004). Try `Vega invoices last 3 months over $5k`, `duplicates this month`, `biggest invoices this quarter`.
- **Tweaks panel** — density (Tight/Comfy/Roomy), accent (Indigo/Emerald/Amber/Rose), triage-pill style (Soft/Solid/Outline), and quick-jump to any demo invoice.

**Try this flow:** open *Acme Freight* (math fails by $0.40) → hover field rows to see bbox highlights → click the "Edit total" action on the math-fails reason card. Then open *Bramble Coffee* to see the duplicate flow, *Halcyon Software* for the 4.2σ anomaly, *TidePoint Energy* for the encrypted-PDF failure path, and ⌘K to see chip-based NL search.

## User

can we make the rounded edges to 0 i don't like the rounded edges

## Assistant

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: done]_

Done — all corners are now sharp. Only the small status dots (the sidebar "all systems normal" indicator and the dots inside triage pills) stay round since they're functionally circular indicators.

## User

you can use this design.md for building the design

## Assistant

_[tool: copy_files]_

I'll apply the principles from your design spec (calm, minimal, photography-first, single quiet blue accent, weight 600 headlines with tight tracking, near-black ink on parchment, the dark global-nav, generous whitespace) — adapted for a data-dense triage tool, and respecting your no-rounded-edges direction. So the *energy* of that design language without literally cloning the Apple product tile (which doesn't fit an AP workflow anyway).

Saving the current direction first, then rebuilding the stylesheet:

_[tool: write_file]_

_[tool: write_file]_

Now I need to append the rest of the styles — buttons, pills, tables, cards, fields, reasons, dropzone, PDF, etc:

_[tool: run_script]_

_[tool: run_script]_

_[tool: str_replace_edit]_

Let me check how it looks now and also fix the accent override in app.jsx to match the new palette:

_[tool: str_replace_edit]_

_[tool: show_html]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: str_replace_edit]_

Looking good! Just one cosmetic issue — the PDF header's right column is wrapping. Let me fix that and also check the search palette:

_[tool: str_replace_edit]_

_[tool: grep]_

_[tool: str_replace_edit]_

_[tool: run_script]_

_[tool: str_replace_edit]_

_[tool: grep]_

_[tool: grep]_

_[tool: grep]_

_[tool: grep]_

_[tool: grep]_

_[tool: grep]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: save_screenshot]_

_[tool: view_image]_

_[tool: done]_

_[tool: fork_verifier_agent]_

Applied the design language from your spec, adapted for a data-dense tool (so no full-bleed product tiles, but the energy comes through):

**What changed:**
- **Type system** swapped to SF Pro Display/Text first with Inter fallback. Body at 15px (compromise between Apple's 17px reading-pace and AP-tool density). Headlines weight 600 with tight tracking (`-0.012em` on the page title) for that Apple-tight feel.
- **Color** — parchment canvas (#f5f5f7), pure-white surfaces, near-black ink (#1d1d1f), Action Blue (#0066cc) as the single quiet accent on every interactive element. Triage pills toned down to muted earth tones instead of saturated.
- **Dark sidebar** — replaced the light sidebar with a near-black global-nav surface (#1d1d1f) with Apple's gray text hierarchy.
- **Frosted topbar** — `backdrop-filter: blur(20px) saturate(180%)` on the top bar.
- **Shadow philosophy** — eliminated UI shadows entirely. The single drop-shadow is reserved for the "PDF paper" since that's the closest thing to a product render in this tool. Cards, buttons, the palette modal — all flat.
- **Press feedback** — `transform: scale(0.97)` on every button/pill (the system-wide micro-interaction in your spec).
- **No rounded edges** preserved from earlier (only the small status dots stay round).
- **Accent tweak** swapped to the 4 hex colors from the spec palette (Action Blue / a confident emerald / amber / rose).

Same data, same components, same Cmd+K behavior — just a quieter, more confident skin. Try the accent swatches in the Tweaks panel to see the single-accent rule in action.

## User

Verifier agent check completed

## Assistant

_[tool: run_script]_

_[tool: grep]_

_[tool: done]_

Fixed. All stale token references in the inline styles across `review.jsx`, `search-palette.jsx`, `pdf-mockup.jsx`, `inbox.jsx`, and `app.jsx` are now mapped to the new palette (`--ink` family, `--canvas`, `--surface-recess`, `--hairline`, `--primary`). The cascade-trace tiles, vendor-memory dividers, sticky review-header bottom border, and palette footer separators will all paint correctly now.

## User

can you change the font to Jakarta Sans it will be better

## Assistant

_[tool: str_replace_edit]_

_[tool: str_replace_edit]_

_[tool: done]_

Switched to Plus Jakarta Sans (300–800 weights loaded). Geist Mono stays for the tabular numerics and chip key/op text. Jakarta's slightly humanist shapes work nicely with the calm parchment + dark-sidebar treatment.

