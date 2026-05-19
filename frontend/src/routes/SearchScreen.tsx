import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Btn } from "@/components/primitives/Btn";
import { Icons } from "@/components/primitives/Icons";
import { LoadingSplash } from "@/components/primitives/LoadingSplash";
import { TriagePill } from "@/components/primitives/TriagePill";
import {
  EMPTY_QUERY,
  type FilterClause,
  type StructuredQuery,
  useInvoicePrefetcher,
  useSearchQuery,
  useTranslateMutation,
} from "@/state/invoices";
import type { InvoiceOut, TriageState } from "@/types/generated/domain";
import { formatMoney } from "@/utils/format";

function parseQueryParam(raw: string | null): StructuredQuery {
  if (!raw) return { ...EMPTY_QUERY };
  try {
    const parsed = JSON.parse(raw) as StructuredQuery;
    return {
      filters: Array.isArray(parsed.filters) ? parsed.filters : [],
      limit: parsed.limit ?? 50,
      sort: parsed.sort ?? null,
      untranslated_intent: parsed.untranslated_intent ?? null,
    };
  } catch {
    return { ...EMPTY_QUERY };
  }
}

async function downloadExport(
  query: StructuredQuery,
  format: "csv" | "json",
): Promise<void> {
  const res = await fetch(`/api/search/export?format=${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(query),
  });
  if (!res.ok) return;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const today = new Date().toISOString().slice(0, 10);
  a.download = `sift-export-${today}.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function chipLabel(c: FilterClause): string {
  const valueText = Array.isArray(c.value)
    ? c.value.join(" to ")
    : typeof c.value === "boolean"
      ? c.value
        ? "true"
        : "false"
      : String(c.value);
  const opLabel: Record<string, string> = {
    eq: "=",
    neq: "≠",
    gt: ">",
    gte: "≥",
    lt: "<",
    lte: "≤",
    in: "in",
    between: "between",
    contains: "contains",
    fts_matches: "matches",
  };
  return `${c.field} ${opLabel[c.op] ?? c.op} ${valueText}`;
}

function pillVariant(inv: InvoiceOut): TriageState | "unprocessable" {
  if (inv.review_status === "unprocessable") return "unprocessable";
  return (inv.current_extraction?.predicted_triage_state ??
    "needs_review") as TriageState;
}

export function SearchScreen() {
  const [params, setParams] = useSearchParams();
  const query = parseQueryParam(params.get("q"));
  const [nlInput, setNlInput] = useState("");
  const navigate = useNavigate();
  const prefetchInvoice = useInvoicePrefetcher();

  const translate = useTranslateMutation();
  const { data: results = [], isFetching, error } = useSearchQuery(query);

  const setQuery = (next: StructuredQuery) => {
    setParams({ q: JSON.stringify(next) }, { replace: true });
    setNlInput("");
  };

  const clearAll = () => {
    setParams({}, { replace: true });
    setNlInput("");
  };

  const removeChip = (idx: number) => {
    const next: StructuredQuery = {
      ...query,
      filters: query.filters.filter((_, i) => i !== idx),
    };
    setQuery(next);
  };

  const onNlSubmit = async (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed) {
      clearAll();
      return;
    }
    try {
      const translated = await translate.mutateAsync(trimmed);
      setQuery({
        filters: translated.filters,
        limit: translated.limit ?? 50,
        sort: translated.sort ?? null,
        untranslated_intent: translated.untranslated_intent ?? null,
      });
    } catch (e) {
      setQuery({
        ...EMPTY_QUERY,
        untranslated_intent: trimmed,
      });
    }
  };

  const handleNlKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void onNlSubmit(nlInput);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-hairline px-5 py-3.5">
        <div className="flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 border border-hairline bg-white px-3 py-2 focus-within:border-action">
            <Icons.search />
            <input
              type="text"
              value={nlInput}
              onChange={(e) => setNlInput(e.target.value)}
              onKeyDown={handleNlKey}
              placeholder="Ask in plain English, e.g. 'duplicates from Vega over $5,000 this month'"
              className="flex-1 border-none bg-transparent text-sm focus:outline-none focus-visible:outline-none"
            />
            {translate.isPending && (
              <span className="text-xs text-ink-48">translating…</span>
            )}
          </div>
          <Btn variant="primary" onClick={() => void onNlSubmit(nlInput)}>
            Search
          </Btn>
          {query.filters.length > 0 && (
            <>
              <Btn variant="ghost" onClick={() => downloadExport(query, "csv")}>
                Export CSV
              </Btn>
              <Btn
                variant="ghost"
                onClick={() => downloadExport(query, "json")}
              >
                Export JSON
              </Btn>
              <Btn variant="ghost" onClick={clearAll}>
                Clear
              </Btn>
            </>
          )}
        </div>

        {query.filters.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[12px] uppercase tracking-[0.06em] text-ink-48">
              Filters
            </span>
            {query.filters.map((c, i) => (
              <ChipWithRemove
                key={chipKey(c)}
                label={chipLabel(c)}
                onRemove={() => removeChip(i)}
              />
            ))}
          </div>
        )}

        {query.untranslated_intent && (
          <div className="mt-2.5 flex items-start gap-2 border border-[#e6c75a] bg-[#fdf3da] px-3 py-2 text-xs text-[#7a4a00]">
            <span className="mt-px">⚠</span>
            <div>
              <b>Partial translation.</b> The system couldn't translate "
              <em>{query.untranslated_intent}</em>" into a structured filter;
              surfaced here so it's not silently dropped.
            </div>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto px-5 py-3">
        {error ? (
          <div className="p-4 text-ink-60">Search failed: {String(error)}</div>
        ) : isFetching && results.length === 0 ? (
          <LoadingSplash size="page" message="Searching" />
        ) : results.length === 0 ? (
          <div className="p-8 text-center text-[13.5px] text-ink-60">
            {query.filters.length === 0
              ? "Type a query above to search the corpus."
              : "No invoices match this query."}
          </div>
        ) : (
          <table className="w-full border-collapse text-[13.5px]">
            <thead>
              <tr>
                {SEARCH_COLS.map(([label, w]) => (
                  <th
                    key={label}
                    style={{ width: w }}
                    className="border-b border-hairline px-3 py-2 text-left text-[12px] uppercase tracking-[0.06em] text-ink-48"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.map((inv) => {
                const fields = inv.current_extraction?.extracted_fields ?? {};
                const vendor = fields.vendor_name?.value ?? "–";
                const invoiceNum = fields.invoice_number?.value ?? "–";
                const total = fields.total?.value;
                const currency = String(fields.currency?.value ?? "");
                const date = fields.invoice_date?.value ?? "–";
                return (
                  <tr
                    key={inv.id}
                    onClick={() => navigate(`/invoice/${inv.id}`)}
                    onMouseEnter={() => prefetchInvoice(inv.id)}
                    onFocus={() => prefetchInvoice(inv.id)}
                    className="cursor-pointer border-b border-hairline-soft"
                  >
                    <td className="px-3 py-2.5">
                      <TriagePill variant={pillVariant(inv)} />
                    </td>
                    <td className="px-3 py-2.5">{String(vendor)}</td>
                    <td className="num px-3 py-2.5">{String(invoiceNum)}</td>
                    <td className="num px-3 py-2.5">{String(date)}</td>
                    <td className="num px-3 py-2.5 text-right">
                      {total == null
                        ? "–"
                        : formatMoney(Number(total), currency)}
                    </td>
                    <td className="px-3 py-2.5 text-ink-60">
                      {inv.review_status}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

const SEARCH_COLS: [string, number][] = [
  ["triage", 110],
  ["vendor", 220],
  ["invoice #", 160],
  ["date", 110],
  ["total", 110],
  ["status", 110],
];

function chipKey(c: FilterClause): string {
  return `${c.field}|${c.op}|${JSON.stringify(c.value)}`;
}

function ChipWithRemove({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 border border-[#c2d4ee] bg-[#eef3fb] py-1 pl-2.5 pr-1 font-mono text-xs text-ink-80">
      {label}
      <button
        onClick={onRemove}
        type="button"
        aria-label={`Remove ${label}`}
        className="inline-grid size-[18px] place-items-center border-none bg-transparent p-0 text-ink-60"
      >
        ✕
      </button>
    </span>
  );
}
