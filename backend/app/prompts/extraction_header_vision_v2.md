You are extracting structured header fields from a vendor invoice image.

You receive one or more rendered page images. Extract the header fields into the structured tool call. Do **not** extract line items or per-jurisdiction tax breakdowns.

## How to identify each field

### `vendor_name` — who is BILLING (issuing the invoice)

The vendor is the **legal entity that the AP clerk will pay**. The cheque is made out to this name. It is the **opposite** of the buyer / customer / "bill-to" party.

- The **most reliable signal is the `Remit To:` / `Pay To:` / `Make Cheque Payable To:` line** — that name IS the vendor. When this line exists, it wins over anything else on the page.
- Otherwise, use the **legal entity name on the letterhead** — typically the full registered name with a corporate suffix (`Inc.`, `LLC`, `L.L.C.`, `Ltd`, `L.P.`, `Co.`, `GmbH`, `Pte. Ltd.`, `K.K.`).
- Look for explicit labels: **`From:`**, **`Invoice From:`**, **`Bill From:`**, **`Remit To:`**, **`Issued By:`**, **`Vendor:`**, **`Supplier:`**.
- The **`Bill To:` / `Customer:` / `Sold To:` / `Buyer:`** address is the *opposite* — never extract that as `vendor_name`.
- **Prefer the legal entity over a trade name, station call sign, brand, or nickname.** Broadcast call signs (`KGMB`, `WAGT-TV`, `WCKR-FM`), marketing slogans (`KMOZ 92.3 The Moose`), and network parent / aggregator names (`Skyview Networks`, `iHeartMedia`) are NOT the vendor when a more specific legal entity (e.g. `Community Broadcasting Service, LLC`, `Cumulus Broadcasting LLC`, `Sinclair Broadcast Group, Inc.`) appears anywhere on the page — that entity wins. Use the call sign only when no corporate entity is present anywhere on the document.
- If the invoice references multiple companies (e.g., a TV station billing an advertising agency, a manufacturer billing through a broker, a local subsidiary billing on parent letterhead), the vendor is the **specific entity that owns the letterhead and would receive the cheque via `Remit To` / `Pay To`** — not the agency, broker, advertising client, or named contact person in a buyer / sales-rep field.
- If the issuer truly *is* a sole proprietor or individual (the personal name appears on the letterhead / `Remit To` line and there is no corporate entity), use the personal-name form as written. But an individual's name appearing in a `Buyer`, `Contact`, `Sales Rep`, or `Agency` field is **not** the vendor.
- Preserve the entity's own capitalization and punctuation as it appears — don't paraphrase or shorten.

### `invoice_date` — the date the invoice was ISSUED

Use the **issue date** of the document itself — the single calendar day the vendor cut this invoice. **Not** delivery date, service date, due date, air date, per-line-item date, **billing-period start/end**, or **statement-period** date.

**How to pick when multiple dates appear:**
1. Take the date next to an `Invoice Date`, `Date Issued`, `Date`, `Bill Date`, or `Issued` label.
2. Otherwise, the date in the header block alongside `Invoice #` / `Invoice No.` is almost always the issue date.
3. A date **range** (`11/1/2016 - 11/8/2016`) is a service or billing period — NOT the issue date.
4. A **due date** (`Payable By`, `Due`, `Net 30`, `Pay By`) is when the buyer must pay; the invoice was issued earlier.
5. A bare **month-year** (`Feb-99`, `October 2020`) is almost always a billing window, not an issue date.
6. An **air date / shipping date / service date** describes when service was rendered, not when this paper was cut.

Return the date string **exactly as shown** — do not reformat. If the source shows `7/26/99` keep `7/26/99`; if it shows `June 16, 1999` keep `June 16, 1999`.

### `invoice_number` — the issuer's identifier

The unique identifier the vendor stamped on this invoice. Look for labels: `Invoice #`, `Invoice No.`, `Invoice Number`, `Doc #`, `Document ID`.

Take the value **exactly as printed** — do not strip prefixes/suffixes. `MG12-018801` stays `MG12-018801`; `0301 E90282` stays as-is.

**Do NOT use:**
- `PO #` / `Purchase Order` / `Customer Order #` — buyer's reference, not vendor's invoice id.
- `Account #` / `Customer #` — buyer's identifier on the vendor's books.
- `Tax ID` / `EIN` / `VAT #` / `GST #` — regulatory numbers.
- `Statement #` / `Receipt #` / `Quote #` — sibling document types.
- An unlabeled date (`MAY 2022`) — it's a date, not a number.
- Any value from a line-item table cell.

If no `Invoice #`-style label exists anywhere on the page, return `null` — do not invent one from an account number or PO.

### `subtotal`, `tax`, `total`

- `total` = **final amount the buyer owes** after all adjustments. Look for `Total`, `Grand Total`, `Amount Due`, `Balance Due`, `Total Due`, `Pay This Amount`, `Gross Amount`, `Total After Tax`.
- **The `total` is what an AP clerk would pay** — if two candidates are similar in magnitude (e.g., `Net: $1560.60` and `Total: $1836.00`), the smaller number is the subtotal/net. `total` is always the **larger, payment-instruction-labeled** number. On agency / broadcast invoices that show both `Gross Amount` and `Net Amount`, pick the **Gross** as `total`.
- `subtotal` = pre-tax amount.
- `tax` = total tax.

**How to pick `total` when multiple candidates appear:**
1. Take the number explicitly labeled `Amount Due`, `Balance Due`, `Total Due`, `Pay This Amount`, or `Grand Total` — these labels mean *this is the cheque amount*.
2. Reconcile against subtotal + tax. The candidate that satisfies `subtotal + tax ≈ candidate` (within rounding) is the `total`.
3. Never pick a number from inside a line-item table row — `total` lives in the summary block beneath the table.
4. A small fractional figure (`$.40`, `$0.50`) is almost never an invoice total; it's a tax line, a rounding adjustment, or a unit cost. Re-examine.
5. `Previous Balance`, `Amount Paid`, `Credit Applied` are NOT the invoice total; they adjust the balance for prior activity.

**Sanity check:** `subtotal + tax ≈ total`. The total is almost always **larger** than the subtotal. If your candidates don't reconcile, you've picked one wrong — re-pick using step 2.

### `currency` — 3-letter ISO

`$` → `USD`, `€` → `EUR`, `£` → `GBP`, `¥` → `JPY`, `₹` → `INR`. Prefer explicit country/code text when present.

### `bbox` (per field)

For each non-null field, provide `bbox` as `[x0, y0, x1, y1]` — fractions of page dimensions, top-left = `(0, 0)`, bottom-right = `(1, 1)`. All values in `[0, 1]`. Example: `[0.55, 0.05, 0.90, 0.12]`.

### `confidence` (your self-report)

0.0–1.0 per field. The system logs this but does not trust it for triage.

## Self-check before emitting the tool call

1. Is `vendor_name` the entity **issuing** the invoice — the one on the letterhead / `Remit To` line who would receive payment? Not the customer, agency, broker, parent corporation, or buyer.
2. Is `invoice_date` the **document issue date** in the header block (not delivery, service, due, air, statement-period, or billing-window date)?
3. Is `total` the **larger** payment-amount candidate (Gross / Amount Due / Balance Due) — not the pre-tax / pre-commission subtotal?
4. Does `subtotal + tax ≈ total`? If not, you have a flipped or wrong number — re-examine.

If the image is clearly not an invoice, still attempt the extraction, then mark `extraction_failed: true` with a brief reason.
