# Sift

Sift takes messy vendor invoices in mixed formats and turns them into clean,
structured data that an AP clerk can review and query.

## Language

**Invoice**:
A request for payment sent by a vendor to the AP clerk's company, arriving as
a PDF, scan, or email attachment.
_Avoid_: Bill, document, receipt

**Vendor**:
The supplier issuing an Invoice. Identified by name + (optionally) tax ID.
_Avoid_: Supplier, payee, merchant, seller

**AP Clerk**:
The end user. Accounts-payable operator at a mid-market company who processes
incoming Invoices day-to-day.
_Avoid_: User, customer, operator, accountant

**Line Item**:
A single billed row inside an Invoice (description, quantity, unit price,
total, optional tax).
_Avoid_: Row, entry, charge

**Extraction**:
The result of running Sift over an Invoice — the structured fields it pulled
out, with per-field confidence.
_Avoid_: Parse, scan result, OCR output

**Confidence**:
A 0–1 score Sift assigns to each extracted field, capturing how sure the
extraction is. Drives Triage State.
_Avoid_: Score, certainty, probability

**Composite Confidence**:
The specific computation Sift uses to produce a field's Confidence:
`min(structural_score, history_score)` per ADR-0003, plus a Cascade
agreement-score override on disputed fields. Structural comes from
validators (math reconciliation, format checks). History comes from a
Z-score against Vendor History numeric stats. The full computation lives
in `app/domain/confidence.py` and emits a per-field provenance trace.
_Avoid_: Final score, combined score, confidence calculation

**Triage State**:
The one-of-three label Sift assigns each Invoice for the AP Clerk's Inbox:
`confident` (no clerk action needed), `needs_review` (with specific reasons),
or `likely_duplicate` (paired with the suspected original).
_Avoid_: Status, state, flag

**Duplicate**:
A captured Invoice that matches an Invoice already in the corpus, detected
by content fingerprint and/or perceptual hash. Same vendor + same invoice
number + similar amount is the strongest signal.
_Avoid_: Copy, repeat, dup

**Anomaly**:
An extracted value that deviates meaningfully from prior Invoices by the same
Vendor (e.g. total >3σ from vendor mean). Surfaced as a Triage reason, not
silently corrected.
_Avoid_: Outlier, weird value

**Vendor History**:
The set of prior Invoices Sift has seen from a given Vendor, used both to
inform extraction (date format, typical layout) and to detect anomalies.
_Avoid_: Vendor data, vendor profile

**Cascade**:
The tiered Haiku → Sonnet → Opus model escalation Sift runs against an
Invoice when initial-tier output is uncertain. Triggers reactively on math
fail, unseen Vendor, or low Composite Confidence (ADR-0003). Disputed
fields are replaced by the higher tier and their Composite Confidence is
overridden by the cross-model agreement score. Also engages when a clerk
explicitly forces a tier (Cmd+K), preserving the same agreement-scoring
discipline.
_Avoid_: Fallback, retry, tier escalation, model chain

## Relationships

- An **AP Clerk** uploads **Invoices** to Sift
- Each **Invoice** has exactly one **Vendor** and one or more **Line Items**
- Each **Invoice** produces exactly one **Extraction** with a **Triage State**
- **Vendor History** is the aggregate of prior **Invoices** from one **Vendor**
- A **Duplicate** is an **Invoice** that matches another **Invoice** in the corpus

## Scope

**In scope:**
- Vendor invoices arriving as PDF (digital or scanned) and image attachments
- English-language invoices
- Single-currency per invoice
- Extract → review → query loop for an AP Clerk

**Out of scope (deliberate cuts):**
- Handwritten invoices
- Non-English invoices
- Multi-currency reconciliation
- Approval workflows / ERP integration
- Receipts, contracts, resumes, bank statements
