/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export interface AnomaliesResponse {
  anomalies: AnomalyOut[];
  counts: AnomalyCounts;
  aggregates: AnomalyAggregates;
}
export interface AnomalyOut {
  id: string;
  type: "amount";
  status: "unreviewed" | "acknowledged";
  vendor: string;
  invoice_id: string;
  detected_at: string;
  headline: string;
  sub: string;
  z_score: number;
  severity: "high" | "medium" | "low";
  metric: AnomalyMetric;
  history: AnomalyHistoryPoint[];
  avg: number;
  diff?: null;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
}
export interface AnomalyMetric {
  value: number;
  currency: string;
  unit: string;
}
export interface AnomalyHistoryPoint {
  value: number;
  current?: boolean;
}
export interface AnomalyCounts {
  all: number;
  unreviewed: number;
  amount: number;
  frequency: number;
  pattern: number;
  acknowledged: number;
}
export interface AnomalyAggregates {
  total_flagged_amount: number;
  total_flagged_currency: string;
  vendors_affected: number;
  highest_severity_z?: number | null;
  highest_severity_vendor?: string | null;
}
export interface AnomalyReason {
  type?: "anomaly";
  field: string;
  vendor_mean: number;
  vendor_std: number;
  z_score: number;
}
export interface BulkAcknowledgeFailure {
  id: string;
  error: string;
}
export interface BulkAcknowledgeIn {
  /**
   * @minItems 1
   * @maxItems 200
   */
  anomaly_ids: [string, ...string[]];
}
export interface BulkAcknowledgeOut {
  acknowledged: AnomalyOut[];
  failed: BulkAcknowledgeFailure[];
}
export interface ClerkOut {
  id: string;
  email: string;
  display_name?: string | null;
}
export interface DuplicateOfReason {
  type?: "duplicate_of";
  invoice_id: string;
  similarity: number;
  match_method: "perceptual_hash" | "content_fingerprint" | "both";
}
/**
 * A single extracted field with bbox + confidence + provenance.
 *
 * See PLAN.md `extracted_fields` shape. The bbox-highlight UX (beat 1)
 * and provenance-hover UX (beat 3) both depend on this shape.
 *
 * `iso_from` / `iso_to` are populated only for `invoice_date`. They carry
 * the canonical YYYY-MM-DD form so search filters compare against a
 * single, parseable representation regardless of how the source PDF
 * wrote the date. Point dates set both fields to the same value; billing
 * periods ("9/21/20 - 9/26/20") set them to the range endpoints.
 */
export interface ExtractedField {
  value: string | number | null;
  bbox?: [unknown, unknown, unknown, unknown] | null;
  page?: number;
  confidence: number;
  source: string;
  iso_from?: string | null;
  iso_to?: string | null;
}
/**
 * Per ADR-0006. Distinct from low_confidence — this is the system,
 * not the model, having failed.
 */
export interface ExtractionFailedReason {
  type?: "extraction_failed";
  stage: "pdf_read" | "llm_call" | "validation" | "cascade_exhausted";
  detail: string;
}
export interface ExtractionOut {
  id: string;
  invoice_id: string;
  model: string;
  cascade_trace: {
    [k: string]: unknown;
  };
  extracted_fields: {
    [k: string]: ExtractedField;
  };
  confidence_per_field: {
    [k: string]: number;
  };
  predicted_triage_state: "confident" | "needs_review" | "likely_duplicate";
  predicted_triage_reasons: (
    | MathFailsReason
    | AnomalyReason
    | DuplicateOfReason
    | LowConfidenceReason
    | MissingFieldReason
    | UnseenVendorReason
    | ExtractionFailedReason
  )[];
  line_items?: LineItem[];
  tax_breakdown?: TaxBreakdownLine[];
  is_current: boolean;
  created_at: string;
}
export interface MathFailsReason {
  type?: "math_fails";
  subtotal: number;
  tax: number;
  total: number;
  delta: number;
}
export interface LowConfidenceReason {
  type?: "low_confidence";
  field: string;
  score: number;
  reason: string;
}
export interface MissingFieldReason {
  type?: "missing_field";
  field: string;
}
export interface UnseenVendorReason {
  type?: "unseen_vendor";
  vendor_name: string;
}
/**
 * A single invoice line item (one row of the line-items table).
 *
 * Day-3 quality-gated extraction surface. `description` is the only field
 * we trust enough to require; quantity/unit_price are commonly missing on
 * service invoices where the line is a flat-fee item. Math checks (sum
 * of `line_total` vs subtotal) are logged but do NOT alter triage state
 * in Day 3 — see PLAN.md Day-3 gate.
 */
export interface LineItem {
  description: string;
  quantity?: number | null;
  unit_price?: number | null;
  line_total: number;
  bbox?: [unknown, unknown, unknown, unknown] | null;
  page?: number;
  confidence?: number;
}
/**
 * One row of the per-jurisdiction tax breakdown table.
 *
 * Day-4 quality-gated extraction surface, mirrors the line-items gate.
 * Math check (sum of `amount` vs header `tax`) is logged but does NOT
 * alter triage state — see PLAN.md Day-4 gate.
 */
export interface TaxBreakdownLine {
  jurisdiction: string;
  rate?: number | null;
  amount: number;
  bbox?: [unknown, unknown, unknown, unknown] | null;
  page?: number;
  confidence?: number;
}
export interface FieldCorrectionOut {
  id: string;
  extraction_id: string;
  field_name: string;
  original_value: string | null;
  corrected_value: string;
  corrected_at: string;
}
export interface InvoiceOut {
  id: string;
  storage_key: string;
  file_hash: string;
  perceptual_hash: string | null;
  vendor_id: string | null;
  uploaded_at: string;
  review_status: "pending" | "confirmed" | "dismissed_duplicate" | "unprocessable";
  duplicate_dismissals?: string[];
  current_extraction?: ExtractionOut | null;
}
export interface LoginIn {
  email: string;
  password: string;
  remember?: boolean;
}
export interface VendorMemory {
  rules?: VendorMemoryRule[];
  stats?: VendorMemoryStats;
}
/**
 * A single learned rule applied to extractions for a vendor.
 */
export interface VendorMemoryRule {
  field: string;
  pattern_type: "date_format" | "name_normalization" | "static_value";
  value: string;
  source_correction_id: string;
  applied_count?: number;
  first_learned_at: string;
}
/**
 * Cached per-vendor stats — feeds anomaly detection AND history_score.
 *
 * Storage shape (the JSONB `memory.stats` dict) carries private Welford
 * intermediates like `_var_n_total` alongside the public fields. The
 * model is the public projection — extras are ignored, not forbidden,
 * so reading from storage after running updates doesn't blow up.
 */
export interface VendorMemoryStats {
  total_seen?: number;
  avg_total?: number;
  std_total?: number;
}
export interface VendorOut {
  id: string;
  name: string;
  tax_id?: string | null;
  normalized_name: string;
  first_seen_at: string;
  memory: VendorMemory;
}

// Python type aliases that pydantic2ts loses (it names types by field path).
export type TriageState = PredictedTriageState;
export type TriageReason = PredictedTriageReasons[number];
