---
status: accepted
date: 2026-05-13
---

# Dual-path extraction: PyMuPDF for digital, vision LLM for scans. No Docling.

## Context

Sift extracts structured data from vendor invoices. Invoices arrive as either
born-digital PDFs (selectable text) or scans/image-only PDFs (no embedded
text). Each demands a different extraction approach.

## Decision

**Digital PDFs:** PyMuPDF for text + bounding boxes + table detection, then
Claude Haiku 4.5 for semantic mapping to schema. Tool-use forces typed JSON
output. Schema and few-shot examples are prompt-cached. Per-vendor memory hint
is appended on top of the cached block. Low confidence on any field escalates
to Claude Sonnet 4.6.

**Scanned PDFs:** `pdf2image` to per-page PNG, then Claude Sonnet 4.6
(vision) with the same cached schema, memory, and tool-use setup. Low
confidence escalates to Claude Opus 4.7.

**Validation runs on both paths:** subtotal + tax_total = total (math check,
catches digit-flip errors); required fields present; currency code valid;
per-vendor anomaly check (total within ±3σ of vendor history); duplicate
detection by perceptual hash + content fingerprint.

## Considered Options

- **Docling for everything.** Cleanest single-pipeline story, but arXiv
  benchmark 2509.04469 shows Docling-style markdown conversion peaks at 64%
  on scanned invoices vs 92.7% for direct image-to-vision-LLM. Docling's
  EasyOCR layer is the bottleneck. On digital PDFs, Docling adds
  reconstruction overhead with no accuracy gain over PyMuPDF reading vector
  text directly.
- **Vision LLM for everything (skip PyMuPDF too).** Works, but Claude's PDF
  upload internally renders to ~2k image tokens per page — strictly more
  expensive and slightly worse than feeding extracted text on digital PDFs.
- **Gemini 3 Flash instead of Claude for vision path.** ~10× cheaper input
  tokens and benchmark-comparable on scans. Rejected for v1 because demo
  volume makes cost difference negligible (<$5), and single-SDK simplicity
  in a 5-day build is worth more than the savings. Flagged in README as
  next optimization for production scale.
- **Mistral OCR 3.** Cheap and strong on tables, but documented "digit flip"
  failure mode (output looks right, individual numbers are wrong) is
  unacceptable for AP/financial data.
- **Reducto (agentic verify-and-re-extract).** Best production answer but
  enterprise-sales pricing and integration cost = scope creep for 5 days.
- **Fine-tuned small VL model (Qwen2.5-VL etc.).** Dataset assembly +
  compute + eval eats the budget. Zero-shot frontier beats hastily-tuned
  small model in this timeframe.
- **Cloud invoice APIs (Textract Expense, Azure Form Recognizer, etc.).**
  Defeats the engineering-depth purpose of the interview; collapses
  "extraction logic" into "I called an API."

## Bbox provenance

The review UI's bbox-highlight surface (Beat 1 of the demo narrative)
requires a bounding box per extracted field on both paths.

- **Digital path:** PyMuPDF `page.get_text("words")` returns words with
  coordinates. After Haiku produces extracted values, we fuzzy-match each
  value against the word stream to recover the bbox. Multi-word values
  (vendor names, addresses) get the union rectangle of the matched tokens.
- **Vision path:** Claude Sonnet/Opus 4.6+ reliably returns bboxes for
  invoice fields when the tool-use schema includes a `bbox: [x0,y0,x1,y1]`
  property on each field. We trust the model's bbox on the vision path
  (no separate OCR pass) and validate by clipping to page dimensions.

Bbox is stored per-field in `extractions.extracted_fields` (see schema
sketch in PLAN.md). If both paths fail to produce a bbox, the field
renders without highlight — never breaks the review screen.

## Consequences

- **Backend is Python.** PyMuPDF and `pdf2image` are Python-only.
- **Two LLM call shapes to maintain** (text input vs vision input), but both
  hit the same tool-use schema and validation layer.
- **No layout-aware table model** in the pipeline. Acceptable risk: PyMuPDF's
  `find_tables()` covers the digital path; the vision LLM handles tables
  natively on scans. If line-item extraction is unreliable on the eval set
  during Day 3, Docling can be added back specifically as a table-bbox
  scaffolding step on the digital path — the architecture supports it
  without a rewrite.
- **The depth bet sits outside this ADR.** Per-vendor memory, anomaly
  detection, duplicate detection, and active learning are the "above and
  beyond" surface for the interview. This ADR only covers the extraction
  pipeline that feeds them.
