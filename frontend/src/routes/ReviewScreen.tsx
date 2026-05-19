import { lazy, Suspense, useMemo, useState, type CSSProperties } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Btn } from "@/components/primitives/Btn";
import { FieldRow } from "@/components/primitives/FieldRow";
import { Icons } from "@/components/primitives/Icons";
import { LineItemsTable } from "@/components/primitives/LineItemsTable";
import { LoadingSplash } from "@/components/primitives/LoadingSplash";
import { PanelSplitter } from "@/components/primitives/PanelSplitter";
import { TaxBreakdownTable } from "@/components/primitives/TaxBreakdownTable";
import { TriagePill } from "@/components/primitives/TriagePill";
import { VendorMemoryCard } from "@/components/primitives/VendorMemoryCard";
import { ReasonCard } from "@/components/reason-cards/ReasonCard";
import type { ReasonActionContext } from "@/components/reason-cards/types";
import { usePanelWidth } from "@/hooks/usePanelWidth";
import {
  useConfirmMutation,
  useDismissDuplicateMutation,
  useInboxQuery,
  useInvoiceQuery,
  useInvoiceVendorQuery,
  useMarkUnprocessableMutation,
  useRetryMutation,
} from "@/state/invoices";
import type {
  ExtractedField,
  InvoiceOut,
  TriageState,
} from "@/types/generated/domain";
import { formatNumber } from "@/utils/format";

const PdfViewer = lazy(() =>
  import("@/components/primitives/PdfViewer").then((m) => ({
    default: m.PdfViewer,
  })),
);

const FIELDS: { key: string; label: string }[] = [
  { key: "vendor_name", label: "Vendor" },
  { key: "invoice_number", label: "Invoice #" },
  { key: "invoice_date", label: "Date" },
  { key: "subtotal", label: "Subtotal" },
  { key: "tax", label: "Tax" },
  { key: "total", label: "Total" },
  { key: "currency", label: "Currency" },
];

function pillVariant(inv: InvoiceOut): TriageState | "unprocessable" {
  if (inv.review_status === "unprocessable") return "unprocessable";
  return (inv.current_extraction?.predicted_triage_state ??
    "needs_review") as TriageState;
}

function minConfidence(inv: InvoiceOut): number | null {
  const cpf = inv.current_extraction?.confidence_per_field;
  if (!cpf) return null;
  const vals = Object.values(cpf);
  if (vals.length === 0) return null;
  return Math.min(...vals);
}

function reasonKey(
  r: NonNullable<
    InvoiceOut["current_extraction"]
  >["predicted_triage_reasons"][number],
): string {
  if ("field" in r) return `${r.type}:${r.field}`;
  if ("invoice_id" in r) return `${r.type}:${r.invoice_id}`;
  if ("vendor_name" in r) return `${r.type}:${r.vendor_name}`;
  if ("stage" in r) return `${r.type}:${r.stage}`;
  return r.type ?? "reason";
}

export function ReviewScreen() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: invoice, isLoading, error } = useInvoiceQuery(id);
  const { data: allInvoices = [] } = useInboxQuery();
  const { data: vendor } = useInvoiceVendorQuery(id);
  const [sideWidth, setSideWidth] = usePanelWidth({
    storageKey: "sift.review.sideWidth.v1",
    defaultWidth: 520,
    min: 360,
    max: 820,
  });

  const confirm = useConfirmMutation();
  const dismissDup = useDismissDuplicateMutation();
  const markUnp = useMarkUnprocessableMutation();
  const retry = useRetryMutation();

  const byId = useMemo(
    () => Object.fromEntries(allInvoices.map((i) => [i.id, i])),
    [allInvoices],
  );

  const [activeField, setActiveField] = useState<string | null>(null);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [manualMode, setManualMode] = useState(false);

  const fields = useMemo(() => {
    const base = (invoice?.current_extraction?.extracted_fields ??
      {}) as Record<string, ExtractedField>;
    const out: Record<string, ExtractedField> = { ...base };
    for (const [k, v] of Object.entries(overrides)) {
      out[k] = {
        ...(out[k] ?? {
          confidence: 1,
          source: "manual-correction",
          bbox: null,
          page: 0,
        }),
        value: v,
        confidence: 1,
        source: "manual-correction",
      } as ExtractedField;
    }
    return out;
  }, [invoice, overrides]);

  const bboxes = useMemo(
    () =>
      Object.entries(fields).flatMap(([name, f]) =>
        Array.isArray(f?.bbox)
          ? [{ name, bbox: f.bbox as [number, number, number, number] }]
          : [],
      ),
    [fields],
  );

  if (isLoading) {
    return <LoadingSplash size="page" message="Loading invoice" />;
  }
  if (error || !invoice) {
    return (
      <div style={{ padding: 24, color: "var(--ink-60)" }}>
        <div style={{ fontSize: 16, marginBottom: 6 }}>Invoice not found.</div>
        <div style={{ fontSize: 12.5, marginBottom: 16 }}>
          It may have been removed, or the ID is wrong.
        </div>
        <Btn icon={Icons.arrowL} onClick={() => navigate("/inbox")}>
          Back to inbox
        </Btn>
      </div>
    );
  }

  const reasons = invoice.current_extraction?.predicted_triage_reasons ?? [];
  const variant = pillVariant(invoice);
  const isUnprocessable = invoice.review_status === "unprocessable";

  const reasonCtx: ReasonActionContext = {
    invoiceId: invoice.id,
    reasons,
    byId,
    confirm: () => confirm.mutate(invoice.id),
    dismissDup: (againstId) => dismissDup.mutate({ id: invoice.id, againstId }),
    markUnp: () => markUnp.mutate(invoice.id),
    retry: (opts) => retry.mutate({ id: invoice.id, ...(opts ?? {}) }),
    setEditingField,
    setManualMode,
    navigate: (to) => navigate(to),
  };

  const commitField = (name: string, value: string) => {
    setOverrides((o) => ({ ...o, [name]: value }));
    setEditingField(null);
  };

  const pdfSrc = `/api/invoices/${invoice.id}/file`;

  const vendorName = String(fields.vendor_name?.value ?? "Invoice");
  const invoiceNumber = String(fields.invoice_number?.value ?? "no invoice #");
  const currency = String(fields.currency?.value ?? "");
  const total =
    typeof fields.total?.value === "number" ? fields.total.value : null;

  return (
    <div
      className="review-grid"
      style={{ "--review-side-w": `${sideWidth}px` } as CSSProperties}
    >
      <div className="pdf-stage">
        {isUnprocessable ? (
          <div className="pdf-paper pdf-paper-encrypted">
            <div
              style={{
                width: 56,
                height: 56,
                background: "var(--surface-recess)",
                display: "grid",
                placeItems: "center",
                color: "var(--ink-60)",
                marginBottom: 14,
              }}
            >
              <Icons.lock />
            </div>
            <div style={{ fontWeight: 600, color: "var(--ink)", fontSize: 15 }}>
              Couldn't read this PDF
            </div>
            <div
              className="muted"
              style={{ marginTop: 6, fontSize: 13, maxWidth: 320 }}
            >
              Sift couldn't read this file. You can re-upload an unlocked copy,
              or enter the fields manually on the right.
            </div>
          </div>
        ) : (
          <Suspense
            fallback={<LoadingSplash size="page" message="Rendering PDF" />}
          >
            <PdfViewer
              src={pdfSrc}
              bboxes={bboxes}
              activeField={activeField}
              onHoverBbox={setActiveField}
            />
          </Suspense>
        )}
      </div>

      <PanelSplitter
        className="review-resizer"
        width={sideWidth}
        onChange={setSideWidth}
        min={360}
        max={820}
        side="right"
        ariaLabel="Resize review panel"
      />

      <div className="review-side">
        <div
          style={{
            padding: "14px 16px",
            borderBottom: "1px solid var(--hairline)",
            background: "var(--canvas)",
            position: "sticky",
            top: 0,
            zIndex: 4,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              marginBottom: 10,
            }}
          >
            <Btn
              variant="ghost"
              size="sm"
              icon={Icons.arrowL}
              onClick={() => navigate("/inbox")}
            >
              Inbox
            </Btn>
            <TriagePill variant={variant} pct={minConfidence(invoice)} />
            <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
              <Btn
                size="sm"
                variant="ghost"
                icon={Icons.refresh}
                title="Retry extraction"
                onClick={() => retry.mutate({ id: invoice.id })}
                disabled={retry.isPending}
              >
                {retry.isPending ? "Retrying…" : "Retry"}
              </Btn>
            </div>
          </div>

          <div
            style={{ fontSize: 17, fontWeight: 600, letterSpacing: "-0.01em" }}
          >
            {vendorName}
          </div>
          <div
            className="muted"
            style={{ fontSize: 12, marginTop: 2, display: "flex", gap: 10 }}
          >
            <span className="mono">{invoiceNumber}</span>
            <span>·</span>
            <span suppressHydrationWarning>
              {new Date(invoice.uploaded_at).toLocaleString()}
            </span>
            {total != null && (
              <>
                <span>·</span>
                <span
                  className="num"
                  style={{ color: "var(--ink)", fontWeight: 500 }}
                >
                  {currency} {formatNumber(total)}
                </span>
              </>
            )}
          </div>

          <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
            <Btn
              variant="primary"
              icon={Icons.check}
              onClick={() => confirm.mutate(invoice.id)}
            >
              Confirm
              <span className="ml-1 bg-white/[0.12] px-1 font-mono text-[12px]">
                C
              </span>
            </Btn>
            <Btn icon={Icons.x} onClick={() => markUnp.mutate(invoice.id)}>
              Dismiss
            </Btn>
          </div>
        </div>

        {}
        {reasons.length > 0 && (
          <div className="review-side-section">
            <div className="review-side-section-title">
              Why this needs attention
              <span
                className="mono"
                style={{ marginLeft: 6, color: "var(--ink-48)" }}
              >
                {reasons.length} {reasons.length === 1 ? "reason" : "reasons"}
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {reasons.map((r) => (
                <ReasonCard key={reasonKey(r)} reason={r} ctx={reasonCtx} />
              ))}
            </div>
          </div>
        )}

        {}
        <div className="review-side-section">
          <div
            className="review-side-section-title"
            style={{ display: "flex", alignItems: "center" }}
          >
            <span>Extracted fields</span>
            {manualMode && (
              <span
                className="source"
                data-kind="manual"
                style={{ marginLeft: 8 }}
              >
                <Icons.pen />
                <span>Manual entry mode</span>
              </span>
            )}
          </div>

          <div className="card" style={{ marginBottom: 12 }}>
            {FIELDS.map(({ key, label }) => (
              <FieldRow
                key={key}
                name={key}
                label={label}
                field={fields[key] ?? null}
                isActive={activeField === key}
                onActivate={setActiveField}
                isEditing={editingField === key}
                onEdit={
                  manualMode || invoice.review_status === "pending"
                    ? setEditingField
                    : null
                }
                onCommit={commitField}
              />
            ))}
          </div>
        </div>

        <div className="review-side-section">
          <div className="review-side-section-title">Line items</div>
          <LineItemsTable
            items={invoice.current_extraction?.line_items ?? []}
            currency={currency}
          />
        </div>

        <div className="review-side-section">
          <div className="review-side-section-title">Tax breakdown</div>
          <TaxBreakdownTable
            rows={invoice.current_extraction?.tax_breakdown ?? []}
            currency={currency}
          />
        </div>

        {}
        {vendor?.memory && (
          <div className="review-side-section">
            <div className="review-side-section-title">Vendor memory</div>
            <VendorMemoryCard
              memory={vendor.memory}
              vendorName={vendor.name}
              currency={currency}
            />
          </div>
        )}

        <div style={{ height: 24 }} />
      </div>
    </div>
  );
}
