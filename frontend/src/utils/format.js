// Currency is a tenant setting; these defaults match the demo tenants.
// Whole amounts show without decimals; amounts with cents keep them (KES 99.49 must not show as KES 99).
export const money = (v, currency = "KES") => {
  const n = Number(v || 0);
  const cents = Math.round(n * 100) % 100 !== 0;
  return new Intl.NumberFormat("en-KE", { style: "currency", currency, currencyDisplay: "code",
    minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 }).format(n);
};

export const compactMoney = (v, currency = "KES") =>
  new Intl.NumberFormat("en", { style: "currency", currency, currencyDisplay: "code", notation: "compact", maximumFractionDigits: 1 }).format(v || 0);

export const number = (v) => new Intl.NumberFormat("en").format(v || 0);

export const pct = (v, digits = 1) => `${Number(v || 0).toFixed(digits)}%`;

export const fullName = (p) => [p?.first_name, p?.last_name].filter(Boolean).join(" ");

export const titleCase = (s = "") => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** Shows an em dash for figures that aren't available yet (e.g. before any results are published). */
export const orDash = (v, fn = (x) => x) => (v === null || v === undefined || v === "" ? "—" : fn(v));

/** "5 min ago", "Yesterday", or a date, from an ISO timestamp. Non-ISO strings pass through. */
export function timeAgo(value) {
  const d = new Date(value);
  if (!value || Number.isNaN(d.getTime())) return value || "";
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 172800) return "Yesterday";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export const shortDate = (value) => (value ? String(value).slice(0, 10) : "—");
