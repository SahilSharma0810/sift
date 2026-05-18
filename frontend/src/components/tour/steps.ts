export type TourPlacement = "top" | "bottom" | "left" | "right" | "auto";

export type TourStep = {
  id: string;
  selector: string;
  title: string;
  body: string;
  placement?: TourPlacement;
  route?: string;
};

export const TOUR_STEPS: TourStep[] = [
  {
    id: "dropzone",
    selector: '[data-tour="dropzone"]',
    title: "Drop invoices to extract",
    body: "Drag one or many PDFs here — digital or scanned. The pipeline picks the right path automatically and returns header fields with per-field bounding boxes.",
    placement: "bottom",
    route: "/inbox",
  },
  {
    id: "triage",
    selector: '[data-tour="triage-col"]',
    title: 'Triage answers "what needs me?"',
    body: "Every row lands in one of three states — needs review, confident, or likely duplicate. The inbox is sorted so the rows that need your attention surface first.",
    placement: "bottom",
    route: "/inbox",
  },
  {
    id: "anomalies",
    selector: '[data-tour="nav-anomalies"]',
    title: "Anomalies are statistical",
    body: "Not \"the model felt unsure.\" Real Z-scores against this vendor's own history. Open one and you'll see the math behind the flag.",
    placement: "right",
  },
  {
    id: "search",
    selector: '[data-tour="topbar-search"]',
    title: "Search in plain English",
    body: 'Type "anomalies from Halcyon over $50k" — it becomes a typed query you can edit, share, and export as CSV with the query embedded in the file header.',
    placement: "bottom",
  },
];
