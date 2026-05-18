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
    title: "Anomalies — an optional add-on",
    body: 'Not core to the extract → review loop, but a useful side-view. Real Z-scores against this vendor\'s own history, not "the model felt unsure." Skip it if you only care about clearing the inbox.',
    placement: "right",
  },
  {
    id: "search",
    selector: '[data-tour="topbar-search"]',
    title: "Search in plain English",
    body: 'Type "anomalies from Halcyon over $50k" — it becomes a typed query you can edit, share, and export as CSV with the query embedded in the file header.',
    placement: "bottom",
  },
  {
    id: "api-usage",
    selector: '[data-tour="api-usage"]',
    title: "API spend — interview demo cap",
    body: "This is a demo for an interview round, so there's a hard USD limit on the Anthropic API. The bar shows spend against that cap. When it hits zero, new extractions and search translations are blocked until the cap is raised — drop a PDF anyway and you'll get a clear error, not a silent failure.",
    placement: "right",
  },
];
