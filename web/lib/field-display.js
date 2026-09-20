// Display-only SI/BL formatting. Does not change court or official scores.
// Caps, UN/LOCODE parentheses, and "Name:" / "Notify:" labels are the same fact.

const PORTS = new Set(["port_of_loading", "port_of_discharge"]);
const PARTIES = new Set(["shipper", "consignee", "notify_party"]);
const ROLE = /^(notify(?:\s+party)?|consignee|shipper|name|voyage|vessel(?:\s*\/\s*voyage)?)\s*:\s*/i;
const PAREN = /\(([^)]*)\)/g;
const LOCODE = /^[A-Z]{5}$/;

export const SEVEN_FIELDS = [
  "shipper",
  "consignee",
  "notify_party",
  "port_of_loading",
  "port_of_discharge",
  "container_count",
  "gross_weight_kg",
];

export function writingOf(fv, side) {
  if (!fv) return "";
  const fromCharge = side === "si" ? fv.charge?.left?.raw_value : fv.charge?.right?.raw_value;
  const stored = side === "si" ? fv.left_value : fv.right_value;
  return String(fromCharge || stored || "").trim();
}

export function pairWritings(fv, email) {
  let si = writingOf(fv, "si");
  let bl = writingOf(fv, "bl");
  if (email?.body_text) {
    if (!si) si = valueFromBody(email.body_text, "si", fv.field);
    if (!bl) bl = valueFromBody(email.body_text, "bl", fv.field);
  }
  if (effectiveState(fv, si, bl) === "MATCH") {
    const shared = si || bl;
    if (shared) {
      if (!si) si = shared;
      if (!bl) bl = shared;
    }
  }
  return { si, bl };
}

/** Formatted SI/BL pair for the table. Same fact → same visible text. */
export function pairView(fv, email) {
  const pair = pairWritings(fv, email);
  const state = effectiveState(fv, pair.si, pair.bl);
  let L = present(fv.field, pair.si);
  let R = present(fv.field, pair.bl);
  if (state === "MATCH" && (L.text || R.text || L.locode || R.locode)) {
    const locode = L.locode || R.locode;
    const text = pickSharedText(fv.field, L, R);
    L = { text, locode, empty: !text && !locode };
    R = { text, locode, empty: !text && !locode };
  }
  return { si: pair.si, bl: pair.bl, L, R, state };
}

export function effectiveState(fv, si = writingOf(fv, "si"), bl = writingOf(fv, "bl")) {
  const stored = fv?.state || "MATCH";
  if (stored === "UNCERTAIN") return "UNCERTAIN";
  if (stored === "MATCH") return "MATCH";
  if (si && bl && sameFact(fv?.field, si, bl)) return "MATCH";
  return stored;
}

export function sameFact(field, left, right) {
  const a = coreOf(field, left);
  const b = coreOf(field, right);
  if (a === "" || b === "") return false;
  if (a === b) return true;
  if (field === "vessel_voyage") return vesselEquivalent(fold(stripRole(left)), fold(stripRole(right)));
  return false;
}

export function coreOf(field, raw) {
  let text = stripRole(raw);
  if (!text) return "";
  if (field === "gross_weight_kg" || field === "gross_weight") {
    const n = firstNumber(text);
    return n == null ? "" : String(n);
  }
  if (field === "container_count") {
    const n = firstNumber(text);
    return n == null ? "" : String(n);
  }
  if (PARTIES.has(field)) text = text.replace(/\s*\|.*$/s, "");
  if (PORTS.has(field) || field === "vessel_voyage") text = text.replace(PAREN, " ");
  return fold(text);
}

export function present(field, raw) {
  const original = String(raw || "").trim();
  if (!original) return { text: "", locode: "", empty: true };
  const stripped = stripRole(original);
  if (PORTS.has(field)) {
    const compact = stripped.replace(/\s+/g, "").toUpperCase();
    if (LOCODE.test(compact) && compact.length === 5 && !stripped.includes("(")) {
      return { text: compact, locode: "", empty: false };
    }
    const locode = locodeOf(stripped);
    const name = titleCase(stripped.replace(PAREN, " "));
    return { text: name || stripped, locode, empty: !name };
  }
  if (PARTIES.has(field)) {
    return { text: titleCase(stripped.replace(/\s*\|.*$/s, "").replace(/\s+/g, " ")), locode: "", empty: !stripped };
  }
  if (field === "vessel_voyage") {
    return { text: formatVessel(stripped), locode: "", empty: !stripped };
  }
  if (field === "container_count") {
    const n = firstNumber(stripped);
    return { text: n == null ? stripped.replace(/\s+/g, " ") : String(n), locode: "", empty: n == null && !stripped };
  }
  if (field === "gross_weight_kg" || field === "gross_weight") {
    const n = firstNumber(stripped);
    if (n == null) return { text: stripped.replace(/\s+/g, " "), locode: "", empty: !stripped };
    return { text: `${n.toLocaleString("en-US")} kg`, locode: "", empty: false };
  }
  return { text: stripped.replace(/\s+/g, " "), locode: "", empty: !stripped };
}

export function valueFromBody(body, side, field) {
  const re = LABELS[field];
  if (!re || !body) return "";
  const siIdx = body.search(/=== SHIPPING INSTRUCTION/i);
  const blIdx = body.search(/=== BILL OF LADING/i);
  let section = body;
  if (siIdx >= 0 && blIdx >= 0) section = side === "si" ? body.slice(siIdx, blIdx) : body.slice(blIdx);
  const lines = section.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m = /^\s*([^:：]{2,40})[:：]\s*(.+)$/.exec(line);
    if (m && re.test(m[1].trim())) {
      let val = stripRole(m[2].trim());
      if (field === "vessel_voyage" && i + 1 < lines.length) {
        const voy = /^(?:voyage(?:\s*(?:no\.?|number))?|voy\.?)\s*:?\s*(.+)$/i.exec(lines[i + 1].trim());
        if (voy && !/\bV\.\w+/.test(val)) val = `${val} ${voy[1].trim()}`;
      }
      return val;
    }
    if (!m && re.test(line.trim()) && i + 1 < lines.length) {
      const nxt = lines[i + 1].trim();
      if (nxt && !/^[^:]{2,40}:\s+\S/.test(nxt)) return stripRole(nxt);
    }
  }
  return "";
}

function stripRole(raw) {
  let text = String(raw || "").trim();
  for (let i = 0; i < 4; i++) {
    const next = text.replace(ROLE, "").trim();
    if (next === text) break;
    text = next;
  }
  return text;
}

function firstNumber(raw) {
  const hit = /[\d.]+/.exec(String(raw || "").replace(/,/g, ""));
  if (!hit) return null;
  const n = Number(hit[0]);
  return Number.isFinite(n) ? Math.round(n) : null;
}

function pickSharedText(field, L, R) {
  const a = L.text || "";
  const b = R.text || "";
  if (field === "vessel_voyage") {
    if (a.includes("·") && !b.includes("·")) return a;
    if (b.includes("·") && !a.includes("·")) return b;
  }
  if (a === b) return a;
  return a.length >= b.length ? a : b;
}

function fold(text) {
  return String(text || "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function locodeOf(raw) {
  let found = "";
  String(raw || "").replace(PAREN, (_, inner) => {
    const code = String(inner || "").trim().toUpperCase();
    if (LOCODE.test(code)) found = code;
    return "";
  });
  return found;
}

function titleCase(raw) {
  const text = String(raw || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  const letters = text.replace(/[^A-Za-z]/g, "");
  const allCaps = letters.length > 2 && letters === letters.toUpperCase();
  if (!allCaps) return text;
  return text
    .toLowerCase()
    .split(" ")
    .map((word) => {
      if (!word) return word;
      const core = word.replace(/[().,]/g, "");
      if (/^\d/.test(word)) return word.toUpperCase();
      if (core.length <= 2) return word.toUpperCase();
      if (["pte", "ltd", "llc", "inc", "gmbh", "sdn", "bhd", "co", "fze", "fz", "uab"].includes(core)) {
        return word.replace(core, core.toUpperCase());
      }
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

function formatVessel(raw) {
  const text = String(raw || "").replace(/\s+/g, " ").trim();
  const m = /^(.*?)(?:\s+\/\s*|\s+)(V\.\S+)$/i.exec(text);
  if (m) return `${titleCase(m[1].trim())} · ${m[2].toUpperCase()}`;
  return titleCase(text);
}

function vesselEquivalent(a, b) {
  const [short, long] = a.length <= b.length ? [a, b] : [b, a];
  if (!long.startsWith(short)) return false;
  const rest = long.slice(short.length).trim();
  return /^(v\s?\S+|[a-z]?\d\w*)$/i.test(rest.replace(/\s+/g, " "));
}

const LABELS = {
  shipper: /^shipper\b/i,
  consignee: /^(?:consignee|to the order of|cnee)\b/i,
  notify_party: /^notify(?: party)?\b/i,
  port_of_loading: /^(?:port of loading|load(?:ing)? port|pol)\b/i,
  port_of_discharge: /^(?:port of discharge|discharge port|pod)\b/i,
  container_count: /^(?:container(?:s| count| qty)?|no\.?\s*of\s*containers|total containers)\b/i,
  gross_weight_kg: /^(?:gross\s*(?:weight|wt)|g\.?w\.?|weight)\b/i,
  gross_weight: /^(?:gross\s*(?:weight|wt)|g\.?w\.?|weight)\b/i,
  vessel_voyage: /^(?:vessel(?:\s*\/\s*voyage)?|vessel name|ocean vessel)\b/i,
};
