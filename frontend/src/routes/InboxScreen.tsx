import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Btn } from "@/components/primitives/Btn";
import { Icons } from "@/components/primitives/Icons";
import { Kbd } from "@/components/primitives/Kbd";
import { StatusBadge } from "@/components/primitives/StatusBadge";
import { TriagePill } from "@/components/primitives/TriagePill";
import { WhyChip } from "@/components/primitives/WhyChip";
import {
  useConfirmMutation,
  useInboxQuery,
  useUploadMutation,
} from "@/state/invoices";
import type { InvoiceOut, TriageState } from "@/types/generated/domain";
import { formatNumber } from "@/utils/format";

type FilterId =
  | "all"
  | "needs_review"
  | "confident"
  | "likely_duplicate"
  | "unprocessable"
  | "confirmed";

const PAGE_SIZE = 25;

function pillVariant(inv: InvoiceOut): TriageState | "unprocessable" {
  if (inv.review_status === "unprocessable") return "unprocessable";
  return (inv.current_extraction?.predicted_triage_state ??
    "needs_review") as TriageState;
}

function minConfidence(inv: InvoiceOut): number | null {
  const cpf = inv.current_extraction?.confidence_per_field;
  if (!cpf) return null;
  const values = Object.values(cpf);
  if (values.length === 0) return null;
  return Math.min(...values);
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

export function InboxScreen() {
  const { data: invoices = [], isLoading, error } = useInboxQuery();
  const upload = useUploadMutation();
  const [filter, setFilter] = useState<FilterId>("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const confirm = useConfirmMutation();

  const toggleSelect = (id: string) => {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  const handleBulkConfirm = () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    const toastId = toast(
      `Confirming ${ids.length} ${ids.length === 1 ? "invoice" : "invoices"}…`,
      {
        duration: 10_000,
        action: {
          label: "Undo",
          onClick: () => {
            toast.dismiss(toastId);
            toast.info("Undo applied — pending confirmations cancelled.");
          },
        },
      },
    );
    for (const id of ids) {
      confirm.mutate(id);
    }
    setSelected(new Set());
  };

  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const counts = useMemo(() => {
    const c = {
      all: invoices.length,
      needs_review: 0,
      confident: 0,
      likely_duplicate: 0,
      unprocessable: 0,
      confirmed: 0,
    };
    for (const inv of invoices) {
      if (inv.review_status === "unprocessable") c.unprocessable += 1;
      if (inv.review_status === "confirmed") c.confirmed += 1;
      const t = inv.current_extraction?.predicted_triage_state;
      if (t === "needs_review" && inv.review_status === "pending")
        c.needs_review += 1;
      if (t === "confident" && inv.review_status === "pending")
        c.confident += 1;
      if (t === "likely_duplicate" && inv.review_status === "pending")
        c.likely_duplicate += 1;
    }
    return c;
  }, [invoices]);

  const filtered = useMemo(() => {
    return invoices.filter((inv) => {
      if (filter === "all") return true;
      if (filter === "unprocessable")
        return inv.review_status === "unprocessable";
      if (filter === "confirmed") return inv.review_status === "confirmed";
      const t = inv.current_extraction?.predicted_triage_state;
      if (filter === "needs_review")
        return t === "needs_review" && inv.review_status === "pending";
      if (filter === "confident")
        return t === "confident" && inv.review_status === "pending";
      if (filter === "likely_duplicate")
        return t === "likely_duplicate" && inv.review_status === "pending";
      return true;
    });
  }, [invoices, filter]);

  const [page, setPage] = useState(1);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  useEffect(() => {
    setPage(1);
  }, [filter]);
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);
  const paged = useMemo(
    () => filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filtered, page],
  );

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return;
      const pdfs = Array.from(files).filter(
        (f) => f.type === "application/pdf",
      );
      const skipped = files.length - pdfs.length;
      if (skipped > 0) {
        toast.error(
          `${skipped} non-PDF file${skipped === 1 ? "" : "s"} skipped. Only PDFs are accepted.`,
        );
      }
      if (pdfs.length === 0) return;

      if (pdfs.length === 1) {
        const file = pdfs[0];
        const id = toast.loading(`Extracting ${file.name}…`);
        try {
          const inv = await upload.mutateAsync(file);
          const vendor =
            inv.current_extraction?.extracted_fields?.vendor_name?.value ??
            "invoice";
          toast.success(`Extracted ${String(vendor)}`, { id });
        } catch (e) {
          toast.error(`Upload failed: ${(e as Error).message}`, { id });
        }
        return;
      }

      const toastId = toast.loading(`Extracting ${pdfs.length} invoices…`);
      let ok = 0;
      let failed = 0;
      for (const file of pdfs) {
        try {
          await upload.mutateAsync(file);
          ok += 1;
          toast.loading(
            `Extracting ${pdfs.length} invoices… (${ok}/${pdfs.length})`,
            {
              id: toastId,
            },
          );
        } catch {
          failed += 1;
        }
      }
      if (failed === 0) {
        toast.success(`Extracted ${ok} ${ok === 1 ? "invoice" : "invoices"}`, {
          id: toastId,
        });
      } else if (ok === 0) {
        toast.error(`All ${failed} uploads failed.`, { id: toastId });
      } else {
        toast.success(`Extracted ${ok}, ${failed} failed.`, { id: toastId });
      }
    },
    [upload],
  );

  return (
    <div className="inbox-content">
      <div
        className="dropzone"
        data-tour="dropzone"
        role="button"
        tabIndex={0}
        aria-label="Drop or select an invoice PDF to upload"
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          void handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            fileInput.current?.click();
          }
        }}
        style={
          dragOver
            ? {
                borderColor: "var(--primary)",
                background: "var(--primary-bg-soft)",
              }
            : undefined
        }
      >
        <div className="dropzone-icon">
          <Icons.upload />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, color: "var(--ink)", fontSize: 13.5 }}>
            Drop invoices to extract
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
            Drop one or many PDFs · digital or scanned
          </div>
        </div>
        <Btn variant="primary" icon={Icons.upload}>
          Upload
        </Btn>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf"
          multiple
          className="hidden"
          style={{ display: "none" }}
          onChange={(e) => {
            void handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      <div className="inbox-toolbar" style={{ marginTop: 16 }}>
        <FilterTabs filter={filter} setFilter={setFilter} counts={counts} />

        {selected.size > 0 && (
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <span
              className="mono"
              style={{
                alignSelf: "center",
                fontSize: 12,
                color: "var(--ink-60)",
              }}
            >
              {selected.size} selected
            </span>
            <Btn
              size="sm"
              icon={Icons.check}
              variant="primary"
              onClick={handleBulkConfirm}
            >
              Confirm
            </Btn>
          </div>
        )}
      </div>

      <div
        style={{
          border: "1px solid var(--hairline)",
          overflow: "hidden",
          background: "var(--surface)",
        }}
      >
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 40 }}></th>
              <th style={{ width: 150 }} data-tour="triage-col">
                Triage
              </th>
              <th>Vendor</th>
              <th>Invoice #</th>
              <th>Date</th>
              <th className="col-right">Amount</th>
              <th>Why</th>
              <th style={{ width: 76 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td
                  colSpan={8}
                  style={{
                    padding: 24,
                    textAlign: "center",
                    color: "var(--ink-60)",
                  }}
                >
                  Loading…
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td
                  colSpan={8}
                  style={{ padding: 24, textAlign: "center", color: "#b22020" }}
                >
                  Failed to load invoices.
                </td>
              </tr>
            )}
            {!isLoading && filtered.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  style={{
                    padding: 24,
                    textAlign: "center",
                    color: "var(--ink-60)",
                  }}
                >
                  {invoices.length === 0
                    ? "No invoices yet — drop one above to get started."
                    : `No invoices match the "${filter}" filter.`}
                </td>
              </tr>
            )}
            {paged.map((inv) => {
              const fields = inv.current_extraction?.extracted_fields ?? {};
              const reasons =
                inv.current_extraction?.predicted_triage_reasons ?? [];
              return (
                <tr
                  key={inv.id}
                  data-selected={selected.has(inv.id) ? "true" : "false"}
                >
                  <td
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleSelect(inv.id);
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(inv.id)}
                      readOnly
                      style={{
                        accentColor: "var(--primary)",
                        cursor: "pointer",
                      }}
                    />
                  </td>
                  <td>
                    <TriagePill
                      variant={pillVariant(inv)}
                      pct={minConfidence(inv)}
                    />
                  </td>
                  <td style={{ fontWeight: 500 }}>
                    <Link
                      to={`/invoice/${inv.id}`}
                      style={{
                        color: "inherit",
                        textDecoration: "none",
                        display: "block",
                      }}
                    >
                      {String(fields.vendor_name?.value ?? "—")}
                    </Link>
                  </td>
                  <td className="num muted">
                    {String(fields.invoice_number?.value ?? "—")}
                  </td>
                  <td className="num muted">
                    {String(fields.invoice_date?.value ?? "—")}
                  </td>
                  <td className="col-right num">
                    {fields.total?.value != null ? (
                      <span>
                        <span className="muted" style={{ marginRight: 4 }}>
                          {String(fields.currency?.value ?? "")}
                        </span>
                        {formatNumber(Number(fields.total.value))}
                      </span>
                    ) : (
                      <span className="subtle">–</span>
                    )}
                  </td>
                  <td>
                    {reasons.length === 0 ? (
                      <span className="subtle">–</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {reasons.slice(0, 2).map((r) => (
                          <WhyChip key={reasonKey(r)} reason={r} />
                        ))}
                        {reasons.length > 2 && (
                          <span className="subtle mono text-xs">
                            +{reasons.length - 2}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td>
                    <StatusBadge status={inv.review_status} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <InboxFooter
        shown={filtered.length}
        total={invoices.length}
        page={page}
        pageCount={pageCount}
        onPrev={() => setPage((p) => Math.max(1, p - 1))}
        onNext={() => setPage((p) => Math.min(pageCount, p + 1))}
      />
    </div>
  );
}

function InboxFooter({
  shown,
  total,
  page,
  pageCount,
  onPrev,
  onNext,
}: {
  shown: number;
  total: number;
  page: number;
  pageCount: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  const from = shown === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, shown);
  return (
    <div className="mt-3.5 flex flex-wrap items-center gap-2 text-xs text-ink-48">
      <span>
        <Kbd>J</Kbd> <Kbd>K</Kbd> navigate
      </span>
      <FooterSep />
      <span>
        <Kbd>Enter</Kbd> open
      </span>
      <FooterSep />
      <span>
        <Kbd>C</Kbd> confirm
      </span>
      <FooterSep />
      <span>
        <Kbd>X</Kbd> dismiss
      </span>
      <FooterSep />
      <span>
        <Kbd>⌘</Kbd> <Kbd>K</Kbd> natural-language search
      </span>
      <div className="ml-auto flex items-center gap-2">
        <span>
          {from}–{to} of {shown}
          {shown !== total && <> · {total} total</>}
        </span>
        {pageCount > 1 && (
          <>
            <FooterSep />
            <button
              type="button"
              onClick={onPrev}
              disabled={page <= 1}
              aria-label="Previous page"
              className="inline-flex h-6 w-6 items-center justify-center border border-hairline bg-surface text-ink-80 hover:bg-surface-recess disabled:cursor-not-allowed disabled:text-ink-48"
            >
              <Icons.arrowL />
            </button>
            <span className="mono text-ink-80">
              {page} / {pageCount}
            </span>
            <button
              type="button"
              onClick={onNext}
              disabled={page >= pageCount}
              aria-label="Next page"
              className="inline-flex h-6 w-6 items-center justify-center border border-hairline bg-surface text-ink-80 hover:bg-surface-recess disabled:cursor-not-allowed disabled:text-ink-48"
            >
              <Icons.arrowR />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function FooterSep() {
  return <span className="h-2.5 w-px bg-hairline" />;
}

const FILTER_TABS: {
  id: FilterId;
  label: string;
  variant?: "confident" | "needs_review" | "likely_duplicate" | "unprocessable";
}[] = [
  { id: "all", label: "All" },
  { id: "needs_review", label: "Needs review", variant: "needs_review" },
  { id: "confident", label: "Confident", variant: "confident" },
  { id: "likely_duplicate", label: "Duplicates", variant: "likely_duplicate" },
  { id: "unprocessable", label: "Unprocessable", variant: "unprocessable" },
  { id: "confirmed", label: "Confirmed" },
];

function FilterTabs({
  filter,
  setFilter,
  counts,
}: {
  filter: FilterId;
  setFilter: (v: FilterId) => void;
  counts: Record<FilterId, number>;
}) {
  return (
    <div className="seg" role="tablist">
      {FILTER_TABS.map((t) => (
        <FilterTab
          key={t.id}
          id={t.id}
          cur={filter}
          set={setFilter}
          label={t.label}
          count={counts[t.id]}
          variant={t.variant}
        />
      ))}
    </div>
  );
}

function FilterTab({
  id,
  cur,
  set,
  label,
  count,
  variant,
}: {
  id: FilterId;
  cur: FilterId;
  set: (v: FilterId) => void;
  label: string;
  count: number;
  variant?: "confident" | "needs_review" | "likely_duplicate" | "unprocessable";
}) {
  const active = cur === id;
  return (
    <button data-active={active} onClick={() => set(id)}>
      {variant && (
        <span
          className="pill-dot"
          style={{
            width: 6,
            height: 6,
            borderRadius: 50,
            background:
              variant === "confident"
                ? "var(--triage-confident)"
                : variant === "needs_review"
                  ? "var(--triage-needs-review)"
                  : variant === "likely_duplicate"
                    ? "var(--triage-duplicate)"
                    : "var(--triage-unprocessable)",
          }}
        />
      )}
      <span>{label}</span>
      <span className="seg-count">{count}</span>
    </button>
  );
}
