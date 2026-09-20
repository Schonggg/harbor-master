// Human-facing labels for backend enums. Keys are the exact backend strings.

export const FIELD_ORDER = [
  "shipper",
  "consignee",
  "notify_party",
  "port_of_loading",
  "port_of_discharge",
  "container_count",
  "gross_weight_kg",
  "gross_weight",
  "vessel_voyage",
];

export const FIELDS = {
  shipper: { zh: "Shipper", en: "Shipper" },
  consignee: { zh: "Consignee", en: "Consignee" },
  notify_party: { zh: "Notify Party", en: "Notify Party" },
  port_of_loading: { zh: "Port of Loading", en: "Port of Loading" },
  port_of_discharge: { zh: "Port of Discharge", en: "Port of Discharge" },
  container_count: { zh: "Container Count", en: "Container Count" },
  gross_weight_kg: { zh: "Gross Weight (kg)", en: "Gross Weight (kg)" },
  gross_weight: { zh: "Gross Weight", en: "Gross Weight" },
  vessel_voyage: { zh: "Vessel / Voyage", en: "Vessel / Voyage" },
};

export function fieldZh(name) {
  return FIELDS[name]?.zh || name;
}
export function fieldEn(name) {
  return FIELDS[name]?.en || name;
}

export const STRATEGIES = {
  suffix_strip: { zh: "Suffix strip", hint: "Drop CO., LTD. / INC / GMBH and punctuation, then compare" },
  locode_map: { zh: "LOCODE map", hint: "Singapore and Singapore (SGSIN) are the same port. Map names and UN/LOCODE codes to one entity" },
  unit_convert: { zh: "Unit convert", hint: "Normalise MT / LBS / KGS to kilograms before compare" },
  ref_resolve: { zh: "Reference resolve", hint: "Resolve SAME AS CONSIGNEE style pointers to the real party" },
  numeric_extract: { zh: "Numeric extract", hint: "Pull the number head from prose like THREE (3) x 40HC" },
  label_synonym: { zh: "Label synonym", hint: "Treat Load Port and Port of Loading as the same field" },
  ocr_confusion: { zh: "OCR confusion", hint: "0/O, 1/I, 5/S corrections only when the source is OCR (ADR-003)" },
  ledger: { zh: "Ledger rule", hint: "A rule a pilot locked in from an earlier decision" },
};

export function strategyZh(name) {
  return STRATEGIES[name]?.zh || name;
}

export const FAILURES = {
  LLM_TIMEOUT: "LLM timeout",
  LLM_INVALID_JSON: "LLM returned invalid JSON",
  ATTACHMENT_CORRUPT: "Attachment corrupt / missing",
  OCR_GARBLED: "Scan garbled",
  EMPTY_EMAIL: "Empty email",
  PARSER_MISS: "Parser miss",
  DEGRADED_RULES_ONLY: "Degraded: rules only",
  CHAOS_INJECTED: "Chaos injected",
};

export function failureZh(code) {
  return FAILURES[code] || code;
}

export const SCOUT = {
  booking_confirmation: "Booking confirmation",
  shipping_instruction: "Shipping instruction (SI)",
  bill_of_lading: "Bill of lading (BL)",
  amendment_request: "Amendment request",
  discrepancy_query: "Discrepancy query",
  invoice_or_charges: "Invoice / charges",
  operational_noise: "Operational noise",
  unknown: "Unknown",
};

export function scoutZh(label) {
  return SCOUT[label] || label || "Unknown";
}

export const VERDICT = {
  CLEAR: { zh: "Release", desc: "The seven fields match, or a defence held" },
  HOLD: { zh: "Hold", desc: "A real discrepancy no defence could absorb" },
  PILOT: { zh: "Pilot", desc: "Evidence is thin or the run failed. Hand to a human." },
};

export const STATE = {
  MATCH: "Match",
  MISMATCH: "Mismatch",
  UNCERTAIN: "Review",
};

export const RISK = {
  critical: "critical",
  high: "high",
  medium: "medium",
  low: "low",
};

export const CHAOS = [
  {
    id: "attachment_corrupt",
    title: "Tear the attachment",
    desc: "Replace the SI/BL file with a missing, corrupt path.",
    glyph: "404",
    expect: "ATTACHMENT_CORRUPT",
  },
  {
    id: "ocr_garble",
    title: "Soil the scan",
    desc: "Turn O into 0, I into 1, S into 5. Low-grade fax energy.",
    glyph: "0CR",
    expect: "OCR_GARBLED",
  },
  {
    id: "llm_timeout",
    title: "Cut the LLM",
    desc: "The model times out. Rules-only mode must stamp DEGRADED.",
    glyph: "T/O",
    expect: "LLM_TIMEOUT",
  },
  {
    id: "empty_email",
    title: "Poison the inbox",
    desc: "Blank subject, body, attachments. Will it invent a verdict?",
    glyph: "NUL",
    expect: "EMPTY_EMAIL",
  },
];

export const PRESETS = {
  cautious: { zh: "Cautious", floor: 0.97 },
  balanced: { zh: "Balanced", floor: 0.92 },
  aggressive: { zh: "Aggressive", floor: 0.85 },
};
