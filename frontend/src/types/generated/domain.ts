/**
 * Domain types — mirrors backend/app/domain/models.py.
 *
 * IMPORTANT: This file is the single source of truth for frontend TS types
 * but is hand-maintained for now (pydantic2ts requires cross-container
 * tooling that's not pulling its weight on a 5-day build). When the backend
 * domain models change, update this file in the same commit. CI should
 * eventually auto-generate this from Pydantic via json-schema-to-typescript.
 */

// ---------- Discriminated unions ----------
export type TriageState = 'confident' | 'needs_review' | 'likely_duplicate'

export type ReviewStatus =
  | 'pending'
  | 'confirmed'
  | 'dismissed_duplicate'
  | 'unprocessable'

export type ExtractionSource =
  | 'pymupdf+haiku'
  | 'claude-vision'
  | 'memory-applied'
  | 'manual-correction'
  | 'manual-entry'
  | string // service emits "pymupdf+<full model name>" — keep loose

// ---------- ExtractedField (per-field shape stored in extracted_fields JSONB) ----------
export interface ExtractedField {
  value: string | number | null
  bbox: [number, number, number, number] | null
  page: number
  confidence: number
  source: ExtractionSource
}

// ---------- Triage reasons (discriminated union by `type`) ----------
export interface MathFailsReason {
  type: 'math_fails'
  subtotal: number
  tax: number
  total: number
  delta: number
}

export interface AnomalyReason {
  type: 'anomaly'
  field: string
  vendor_mean: number
  vendor_std: number
  z_score: number
}

export interface DuplicateOfReason {
  type: 'duplicate_of'
  invoice_id: string
  similarity: number
  match_method: 'perceptual_hash' | 'content_fingerprint' | 'both'
}

export interface LowConfidenceReason {
  type: 'low_confidence'
  field: string
  score: number
  reason: string
}

export interface MissingFieldReason {
  type: 'missing_field'
  field: string
}

export interface UnseenVendorReason {
  type: 'unseen_vendor'
  vendor_name: string
}

export interface ExtractionFailedReason {
  type: 'extraction_failed'
  stage: 'pdf_read' | 'llm_call' | 'validation' | 'cascade_exhausted'
  detail: string
}

export type TriageReason =
  | MathFailsReason
  | AnomalyReason
  | DuplicateOfReason
  | LowConfidenceReason
  | MissingFieldReason
  | UnseenVendorReason
  | ExtractionFailedReason

// ---------- Vendor memory ----------
export interface VendorMemoryRule {
  field: string
  pattern_type: 'date_format' | 'name_normalization' | 'static_value'
  value: string
  source_correction_id: string
  applied_count: number
  first_learned_at: string
}

export interface VendorMemoryStats {
  total_seen: number
  avg_total: number
  std_total: number
}

export interface VendorMemory {
  rules: VendorMemoryRule[]
  stats: VendorMemoryStats
}

// ---------- Top-level DTOs ----------
export interface VendorOut {
  id: string
  name: string
  tax_id: string | null
  normalized_name: string
  first_seen_at: string
  memory: VendorMemory
}

export interface ExtractionOut {
  id: string
  invoice_id: string
  model: string
  cascade_trace: Record<string, unknown>
  extracted_fields: Record<string, ExtractedField>
  confidence_per_field: Record<string, number>
  predicted_triage_state: TriageState
  predicted_triage_reasons: TriageReason[]
  is_current: boolean
  created_at: string
}

export interface InvoiceOut {
  id: string
  file_path: string
  file_hash: string
  perceptual_hash: string | null
  vendor_id: string | null
  uploaded_at: string
  review_status: ReviewStatus
  current_extraction: ExtractionOut | null
}

export interface FieldCorrectionOut {
  id: string
  extraction_id: string
  field_name: string
  original_value: string | null
  corrected_value: string
  corrected_at: string
}
