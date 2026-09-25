// Small DOM helpers and shared components.
import { icon } from "./icons.js";

export const $ = (selector, root = document) => root.querySelector(selector);

/** Build an element. Children that are strings become text nodes (never HTML). */
export function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "style") node.style.cssText = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// ------------------------------------------------------------------ toast
let toastTimer;
export function toast(message) {
  const node = $("#toast");
  node.replaceChildren(icon("check", "icon-sm"), document.createTextNode(message));
  node.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("is-visible"), 2400);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = h("textarea", { style: "position:fixed;opacity:0" });
    area.value = text;
    document.body.append(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}

// ------------------------------------------------------- segmented control
/** A row of options that behaves like radio buttons (arrow keys move the choice). */
export function segmented(container, { label, options, value, onChange }) {
  container.classList.add("segmented");
  container.setAttribute("role", "radiogroup");
  container.setAttribute("aria-label", label);
  let current = value;
  const buttons = options.map((option) =>
    h(
      "button",
      {
        type: "button",
        role: "radio",
        title: option.title,
        "aria-label": option.title || option.label,
        onClick: () => select(option.value, true),
      },
      option.label,
    ),
  );
  container.replaceChildren(...buttons);

  function select(next, emit) {
    current = next;
    buttons.forEach((button, index) => {
      const on = options[index].value === next;
      button.setAttribute("aria-checked", String(on));
      button.tabIndex = on ? 0 : -1;
    });
    if (emit) onChange(next);
  }

  container.addEventListener("keydown", (event) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    let next = options.findIndex((option) => option.value === current);
    for (let tries = 0; tries < options.length; tries++) {
      next = (next + step + options.length) % options.length;
      if (!buttons[next].disabled) break;
    }
    select(options[next].value, true);
    buttons[next].focus();
  });

  select(value, false);
  return {
    set: (next) => select(next, false),
    /** Grey out options that don't apply (e.g. a fuel the chosen model isn't sold with). */
    setAvailable(values) {
      buttons.forEach((button, index) => {
        const available = !values || values.includes(options[index].value);
        button.disabled = !available;
        button.title = available ? options[index].title || "" : `Not available for this model`;
      });
    },
  };
}

// ------------------------------------------------------------------ table
/** columns: [{key, label, align, format(value,row), render(row) -> Node}] */
export function renderTable(columns, rows) {
  const head = h("tr", {}, columns.map((column) => h("th", { class: column.align === "right" ? "right" : null, scope: "col" }, column.label)));
  const body = rows.map((row) =>
    h(
      "tr",
      {},
      columns.map((column) => {
        const cell = h("td", { class: column.align === "right" ? "right" : null });
        if (column.render) cell.append(column.render(row));
        else cell.textContent = column.format ? column.format(row[column.key], row) : row[column.key];
        return cell;
      }),
    ),
  );
  return h("table", { class: "data" }, h("thead", {}, head), h("tbody", {}, body));
}

// ------------------------------------------------------------- chart card
/** A card with a title, a chart area, and a "Table" toggle that shows the same numbers as a table. */
export function chartCard({ title, subtitle = "", className = "", tools = [] }) {
  const titleEl = h("h3", { class: "card__title" }, title);
  const subtitleEl = h("p", { class: "card__subtitle" }, subtitle);
  const chartEl = h("div", { class: "chart-area" });
  const tableEl = h("div", { class: "table-wrap table-wrap--scroll", hidden: true });
  const foot = h("div", { class: "card__foot", hidden: true });
  let table = null;

  const toggleLabel = h("span", {}, "Table");
  const toggle = h("button", { type: "button", class: "link-btn", "aria-pressed": "false" }, icon("table", "icon-sm"), toggleLabel);
  toggle.addEventListener("click", () => {
    const showTable = toggle.getAttribute("aria-pressed") !== "true";
    toggle.setAttribute("aria-pressed", String(showTable));
    toggleLabel.textContent = showTable ? "Chart" : "Table";
    chartEl.hidden = showTable;
    tableEl.hidden = !showTable;
    if (showTable && table) tableEl.replaceChildren(renderTable(...table));
  });

  const card = h(
    "article",
    { class: `card chart-card ${className}` },
    h("header", { class: "card__head" }, h("div", {}, titleEl, subtitleEl), h("div", { class: "card__tools", style: "display:flex;gap:8px;align-items:center" }, ...tools, toggle)),
    h("div", { class: "card__body" }, chartEl, tableEl),
    foot,
  );

  return {
    card,
    chartEl,
    foot,
    setTitle: (text) => (titleEl.textContent = text),
    setSubtitle: (text) => (subtitleEl.textContent = text),
    setFoot(content) {
      foot.hidden = !content;
      foot.replaceChildren(...(content ? [content] : []));
    },
    setTable(columns, rows) {
      table = [columns, rows];
      if (!tableEl.hidden) tableEl.replaceChildren(renderTable(columns, rows));
    },
  };
}

export function kpi({ label, value, sub }) {
  return h("div", { class: "card kpi" }, h("div", { class: "kpi__label" }, label), h("div", { class: "kpi__value" }, value), sub ? h("div", { class: "kpi__sub" }, sub) : null);
}

/** Animate a number from its previous value (respects reduced motion). */
export function countTo(node, target, formatFn, duration = 550) {
  const from = Number(node.dataset.value ?? target);
  node.dataset.value = String(target);
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || from === target) {
    node.textContent = formatFn(target);
    return;
  }
  const start = performance.now();
  const frame = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - (1 - t) ** 3;
    node.textContent = formatFn(from + (target - from) * eased);
    if (t < 1 && node.dataset.value === String(target)) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
