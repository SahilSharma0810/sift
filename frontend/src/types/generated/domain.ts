/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export type Value = string | number | null;
export type Bbox = [unknown, unknown, unknown, unknown] | null;
export type Page = number;
export type Confidence = number;
export type Source = string;
export type Jurisdiction = string;
export type Rate = number | null;
export type Amount = number;
export type Bbox1 = [unknown, unknown, unknown, unknown] | null;
export type Page1 = number;
export type Confidence1 = number;
export type Description = string;
export type Quantity = number | null;
export type UnitPrice = number | null;
export type LineTotal = number;
export type Bbox2 = [unknown, unknown, unknown, unknown] | null;
export type Page2 = number;
export type Confidence2 = number;
export type Type = "math_fails";
export type Subtotal = number;
export type Tax = number;
export type Total = number;
export type Delta = number;
export type Type1 = "anomaly";
export type Field = string;
export type VendorMean = number;
export type VendorStd = number;
export type ZScore = number;
export type Type2 = "duplicate_of";
export type InvoiceId = string;
export type Similarity = number;
export type MatchMethod = "perceptual_hash" | "content_fingerprint" | "both";
export type Type3 = "low_confidence";
export type Field1 = string;
export type Score = number;
export type Reason = string;
export type Type4 = "missing_field";
export type Field2 = string;
export type Type5 = "unseen_vendor";
export type VendorName = string;
export type Type6 = "extraction_failed";
export type Stage = "pdf_read" | "llm_call" | "validation" | "cascade_exhausted";
export type Detail = string;
export type Field3 = string;
export type PatternType = "date_format" | "name_normalization" | "static_value";
export type Value1 = string;
export type SourceCorrectionId = string;
export type AppliedCount = number;
export type FirstLearnedAt = string;
export type TotalSeen = number;
export type AvgTotal = number;
export type StdTotal = number;
export type Rules = VendorMemoryRule[];
export type Id = string;
export type Name = string;
export type TaxId = string | null;
export type NormalizedName = string;
export type FirstSeenAt = string;
export type Id1 = string;
export type InvoiceId1 = string;
export type Model = string;
export type PredictedTriageState = "confident" | "needs_review" | "likely_duplicate";
export type PredictedTriageReasons = (
  | MathFailsReason
  | AnomalyReason
  | DuplicateOfReason
  | LowConfidenceReason
  | MissingFieldReason
  | UnseenVendorReason
  | ExtractionFailedReason
)[];
export type LineItems = LineItem[];
export type TaxBreakdown = TaxBreakdownLine[];
export type IsCurrent = boolean;
export type CreatedAt = string;
export type Id2 = string;
export type FilePath = string;
export type FileHash = string;
export type PerceptualHash = string | null;
export type VendorId = string | null;
export type UploadedAt = string;
export type ReviewStatus = "pending" | "confirmed" | "dismissed_duplicate" | "unprocessable";
export type DuplicateDismissals = string[];
export type Id3 = string;
export type ExtractionId = string;
export type FieldName = string;
export type OriginalValue = string | null;
export type CorrectedValue = string;
export type CorrectedAt = string;
export type Id4 = string;
export type Email = string;
export type DisplayName = string | null;
export type Email1 = string;
export type Password = string;
export type Remember = boolean;
export type Id5 = string;
export type Type7 = "amount";
export type Status = "unreviewed" | "acknowledged";
export type Vendor = string;
export type InvoiceId2 = string;
export type DetectedAt = string;
export type Headline = string;
export type Sub = string;
export type ZScore1 = number;
export type Severity = "high" | "medium" | "low";
export type Value2 = number;
export type Currency = string;
export type Unit = string;
export type Value3 = number;
export type Current = boolean;
export type History = AnomalyHistoryPoint[];
export type Avg = number;
export type Diff = null;
export type AcknowledgedAt = string | null;
export type AcknowledgedBy = string | null;
export type Anomalies = AnomalyOut[];
export type All = number;
export type Unreviewed = number;
export type Amount1 = number;
export type Frequency = number;
export type Pattern = number;
export type Acknowledged = number;
export type TotalFlaggedAmount = number;
export type TotalFlaggedCurrency = string;
export type VendorsAffected = number;
export type HighestSeverityZ = number | null;
export type HighestSeverityVendor = string | null;
export type Id6 = string;
export type Error = string;
/**
 * @minItems 1
 * @maxItems 200
 */
export type AnomalyIds = [string, ...string[]];
export type Acknowledged1 = AnomalyOut[];
export type Failed = BulkAcknowledgeFailure[];

/**
 * A single extracted field with bbox + confidence + provenance.
 *
 * See PLAN.md `extracted_fields` shape. The bbox-highlight UX (beat 1)
 * and provenance-hover UX (beat 3) both depend on this shape.
 */
export interface ExtractedField {
  value: Value;
  bbox?: Bbox;
  page?: Page;
  confidence: Confidence;
  source: Source;
}
/**
 * One row of the per-jurisdiction tax breakdown table.
 *
 * Day-4 quality-gated extraction surface, mirrors the line-items gate.
 * Math check (sum of `amount` vs header `tax`) is logged but does NOT
 * alter triage state — see PLAN.md Day-4 gate.
 */
export interface TaxBreakdownLine {
  jurisdiction: Jurisdiction;
  rate?: Rate;
  amount: Amount;
  bbox?: Bbox1;
  page?: Page1;
  confidence?: Confidence1;
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
  description: Description;
  quantity?: Quantity;
  unit_price?: UnitPrice;
  line_total: LineTotal;
  bbox?: Bbox2;
  page?: Page2;
  confidence?: Confidence2;
}
export interface MathFailsReason {
  type?: Type;
  subtotal: Subtotal;
  tax: Tax;
  total: Total;
  delta: Delta;
}
export interface AnomalyReason {
  type?: Type1;
  field: Field;
  vendor_mean: VendorMean;
  vendor_std: VendorStd;
  z_score: ZScore;
}
export interface DuplicateOfReason {
  type?: Type2;
  invoice_id: InvoiceId;
  similarity: Similarity;
  match_method: MatchMethod;
}
export interface LowConfidenceReason {
  type?: Type3;
  field: Field1;
  score: Score;
  reason: Reason;
}
export interface MissingFieldReason {
  type?: Type4;
  field: Field2;
}
export interface UnseenVendorReason {
  type?: Type5;
  vendor_name: VendorName;
}
/**
 * Per ADR-0006. Distinct from low_confidence — this is the system,
 * not the model, having failed.
 */
export interface ExtractionFailedReason {
  type?: Type6;
  stage: Stage;
  detail: Detail;
}
/**
 * A single learned rule applied to extractions for a vendor.
 */
export interface VendorMemoryRule {
  field: Field3;
  pattern_type: PatternType;
  value: Value1;
  source_correction_id: SourceCorrectionId;
  applied_count?: AppliedCount;
  first_learned_at: FirstLearnedAt;
}
/**
 * Cached per-vendor stats — feeds anomaly detection AND history_score.
 */
export interface VendorMemoryStats {
  total_seen?: TotalSeen;
  avg_total?: AvgTotal;
  std_total?: StdTotal;
}
export interface VendorMemory {
  rules?: Rules;
  stats?: VendorMemoryStats;
}
export interface VendorOut {
  id: Id;
  name: Name;
  tax_id?: TaxId;
  normalized_name: NormalizedName;
  first_seen_at: FirstSeenAt;
  memory: VendorMemory;
}
export interface ExtractionOut {
  id: Id1;
  invoice_id: InvoiceId1;
  model: Model;
  cascade_trace: CascadeTrace;
  extracted_fields: ExtractedFields;
  confidence_per_field: ConfidencePerField;
  predicted_triage_state: PredictedTriageState;
  predicted_triage_reasons: PredictedTriageReasons;
  line_items?: LineItems;
  tax_breakdown?: TaxBreakdown;
  is_current: IsCurrent;
  created_at: CreatedAt;
}
export interface CascadeTrace {
  [k: string]: unknown;
}
export interface ExtractedFields {
  [k: string]: ExtractedField;
}
export interface ConfidencePerField {
  [k: string]: number;
}
export interface InvoiceOut {
  id: Id2;
  file_path: FilePath;
  file_hash: FileHash;
  perceptual_hash: PerceptualHash;
  vendor_id: VendorId;
  uploaded_at: UploadedAt;
  review_status: ReviewStatus;
  duplicate_dismissals?: DuplicateDismissals;
  current_extraction?: ExtractionOut | null;
}
export interface FieldCorrectionOut {
  id: Id3;
  extraction_id: ExtractionId;
  field_name: FieldName;
  original_value: OriginalValue;
  corrected_value: CorrectedValue;
  corrected_at: CorrectedAt;
}
export interface ClerkOut {
  id: Id4;
  email: Email;
  display_name?: DisplayName;
}
export interface LoginIn {
  email: Email1;
  password: Password;
  remember?: Remember;
}
export interface AnomaliesResponse {
  anomalies: Anomalies;
  counts: AnomalyCounts;
  aggregates: AnomalyAggregates;
}
export interface AnomalyOut {
  id: Id5;
  type: Type7;
  status: Status;
  vendor: Vendor;
  invoice_id: InvoiceId2;
  detected_at: DetectedAt;
  headline: Headline;
  sub: Sub;
  z_score: ZScore1;
  severity: Severity;
  metric: AnomalyMetric;
  history: History;
  avg: Avg;
  diff?: Diff;
  acknowledged_at?: AcknowledgedAt;
  acknowledged_by?: AcknowledgedBy;
}
export interface AnomalyMetric {
  value: Value2;
  currency: Currency;
  unit: Unit;
}
export interface AnomalyHistoryPoint {
  value: Value3;
  current?: Current;
}
export interface AnomalyCounts {
  all: All;
  unreviewed: Unreviewed;
  amount: Amount1;
  frequency: Frequency;
  pattern: Pattern;
  acknowledged: Acknowledged;
}
export interface AnomalyAggregates {
  total_flagged_amount: TotalFlaggedAmount;
  total_flagged_currency: TotalFlaggedCurrency;
  vendors_affected: VendorsAffected;
  highest_severity_z?: HighestSeverityZ;
  highest_severity_vendor?: HighestSeverityVendor;
}
export interface BulkAcknowledgeFailure {
  id: Id6;
  error: Error;
}
export interface BulkAcknowledgeIn {
  anomaly_ids: AnomalyIds;
}
export interface BulkAcknowledgeOut {
  acknowledged: Acknowledged1;
  failed: Failed;
}
