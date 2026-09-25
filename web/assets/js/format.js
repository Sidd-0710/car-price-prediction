// Number formatting for Indian prices. All prices from the API are in lakhs (1 lakh = 100,000 rupees).
const indian = new Intl.NumberFormat("en-IN");
const MINUS = "−";

export const int = (value) => indian.format(Math.round(value));
export const km = (value) => `${int(value)} km`;

export function lakh(value) {
  return value >= 100 ? `₹${(value / 100).toFixed(2)} crore` : `₹${value.toFixed(2)} lakh`;
}

export function lakhShort(value) {
  return value >= 100 ? `₹${(value / 100).toFixed(2)} Cr` : `₹${value.toFixed(2)} L`;
}

/** 3.77 -> "₹3,77,000" */
export function rupees(lakhs) {
  return `₹${indian.format(Math.round(lakhs * 100000 / 1000) * 1000)}`;
}

export function signedLakh(value) {
  const sign = value > 0 ? "+" : value < 0 ? MINUS : "";
  return `${sign}₹${Math.abs(value).toFixed(2)} L`;
}

export function signedPct(value, digits = 1) {
  const shown = Math.abs(value).toFixed(digits);
  const sign = Number(shown) === 0 ? "" : value > 0 ? "+" : MINUS; // never "-0%"
  return `${sign}${shown}%`;
}

export const pct = (value, digits = 1) => `${value.toFixed(digits)}%`;

/** "Maruti" -> "M", "Land Rover" -> "LR", "Mercedes-Benz" -> "MB" */
export function initials(brand) {
  return brand
    .split(/[\s-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

export function plural(count, word, many = `${word}s`) {
  return `${int(count)} ${count === 1 ? word : many}`;
}
