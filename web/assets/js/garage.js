// "Garage": estimates saved in this browser, to compare cars side by side.
import { initials, int, lakhShort } from "./format.js";
import { icon } from "./icons.js";
import { $, h, toast } from "./ui.js";

const KEY = "autovalue.garage.v1";
const LIMIT = 12;

function read() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || [];
  } catch {
    return [];
  }
}

const sameInputs = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export function createGarage({ onLoad }) {
  let items = read();
  let drawer = null;
  let backdrop = null;
  let returnFocus = null;
  const badge = $("#garage-count");

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(items));
    } catch {
      /* private mode: keep it in memory only */
    }
    badge.textContent = String(items.length);
    badge.hidden = items.length === 0;
    if (drawer) renderBody();
  }

  function add(entry) {
    if (items.some((item) => sameInputs(item.inputs, entry.inputs))) {
      toast("This car is already in your garage");
      return;
    }
    items.unshift({ id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, savedAt: Date.now(), ...entry });
    items = items.slice(0, LIMIT);
    save();
    toast(`Saved to your garage (${items.length})`);
  }

  function remove(id) {
    items = items.filter((item) => item.id !== id);
    save();
  }

  function card(item, maxPrice, cheapestId) {
    const { inputs, estimate } = item;
    return h(
      "article",
      { class: "saved" },
      h(
        "div",
        { class: "saved__top" },
        h("span", { class: "avatar", "aria-hidden": "true" }, initials(item.brand)),
        h(
          "div",
          {},
          h("div", { class: "saved__name" }, item.name, item.id === cheapestId ? h("span", { class: "saved__tag" }, "Lowest") : null),
          h("div", { class: "saved__meta" }, `${inputs.year} · ${int(inputs.kms)} km · ${inputs.fuel} · ${inputs.transmission}`),
        ),
        h("div", { class: "saved__price" }, h("strong", {}, lakhShort(estimate.price)), h("span", {}, `${lakhShort(estimate.lower)} – ${lakhShort(estimate.upper)}`)),
      ),
      h("div", { class: "saved__bar", "aria-hidden": "true" }, h("span", { style: `width:${Math.max(4, (estimate.price / maxPrice) * 100)}%` })),
      h(
        "div",
        { class: "saved__actions" },
        h(
          "button",
          {
            type: "button",
            class: "btn btn--ghost btn--sm",
            onClick: () => {
              close();
              onLoad(inputs);
            },
          },
          icon("arrowRight", "icon-sm"),
          "Open estimate",
        ),
        h("button", { type: "button", class: "btn btn--quiet btn--sm", "aria-label": `Remove ${item.name}`, onClick: () => remove(item.id) }, icon("trash", "icon-sm"), "Remove"),
      ),
    );
  }

  function renderBody() {
    const body = drawer.querySelector(".drawer__body");
    const foot = drawer.querySelector(".drawer__foot");
    if (!items.length) {
      body.replaceChildren(
        h(
          "div",
          { class: "empty" },
          icon("garage"),
          h("strong", {}, "Your garage is empty"),
          "Save estimates here to compare cars side by side. They stay in this browser only.",
        ),
      );
      foot.hidden = true;
      return;
    }
    const maxPrice = Math.max(...items.map((item) => item.estimate.price));
    const cheapest = items.length > 1 ? items.reduce((a, b) => (b.estimate.price < a.estimate.price ? b : a)).id : null;
    body.replaceChildren(...items.map((item) => card(item, maxPrice, cheapest)));
    foot.hidden = false;
    foot.querySelector(".drawer__count").textContent = `${items.length} saved · bars compare the estimates`;
  }

  function onKey(event) {
    if (event.key === "Escape") close();
    if (event.key === "Tab" && drawer) {
      const focusable = [...drawer.querySelectorAll("button, a[href]")].filter((node) => !node.closest("[hidden]"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  function open() {
    if (drawer) return;
    returnFocus = document.activeElement;
    backdrop = h("div", { class: "backdrop", onClick: close });
    const closeButton = h("button", { type: "button", class: "icon-btn", "aria-label": "Close garage", onClick: close }, icon("x"));
    drawer = h(
      "aside",
      { class: "drawer", role: "dialog", "aria-modal": "true", "aria-labelledby": "garage-title" },
      h("div", { class: "drawer__head" }, h("div", {}, h("h2", { id: "garage-title" }, "Your garage"), h("p", { class: "card__subtitle" }, "Saved estimates, compared")), closeButton),
      h("div", { class: "drawer__body" }),
      h(
        "div",
        { class: "drawer__foot" },
        h("span", { class: "drawer__count card__subtitle" }),
        h(
          "button",
          {
            type: "button",
            class: "btn btn--quiet btn--sm",
            onClick: () => {
              items = [];
              save();
              toast("Garage cleared");
            },
          },
          "Clear all",
        ),
      ),
    );
    document.body.append(backdrop, drawer);
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    renderBody();
    closeButton.focus();
  }

  function close() {
    if (!drawer) return;
    drawer.remove();
    backdrop.remove();
    drawer = backdrop = null;
    document.body.style.overflow = "";
    document.removeEventListener("keydown", onKey);
    returnFocus?.focus?.();
  }

  $("#garage-btn").addEventListener("click", open);
  save();
  return { add, open, has: (inputs) => items.some((item) => sameInputs(item.inputs, inputs)) };
}
