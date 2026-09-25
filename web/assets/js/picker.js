// Searchable car picker (an accessible combobox).
import { initials, int } from "./format.js";
import { h } from "./ui.js";

const normalise = (text) => text.toLowerCase().replace(/\s+/g, " ").trim();

/** Wrap every match of the typed words in <mark>, using text nodes only. */
function highlighted(text, words) {
  const lower = text.toLowerCase();
  const hits = new Array(text.length).fill(false);
  for (const word of words) {
    if (!word) continue;
    let from = lower.indexOf(word);
    while (from !== -1) {
      for (let i = from; i < from + word.length; i++) hits[i] = true;
      from = lower.indexOf(word, from + word.length);
    }
  }
  const fragment = document.createDocumentFragment();
  let i = 0;
  while (i < text.length) {
    const start = i;
    const on = hits[i];
    while (i < text.length && hits[i] === on) i++;
    const piece = text.slice(start, i);
    fragment.append(on ? h("mark", {}, piece) : document.createTextNode(piece));
  }
  return fragment;
}

/**
 * items: [{ brand, model, listings }]
 * onSelect({ name, brand, model, listings })  - `model` is null for "any model of this brand"
 */
export function createPicker(root, { items, onSelect }) {
  const input = root.querySelector(".picker__input");
  const list = root.querySelector(".picker__list");
  const clear = root.querySelector(".picker__clear");

  const brands = new Map();
  for (const item of items) brands.set(item.brand, (brands.get(item.brand) || 0) + item.listings);
  const popular = [...items].sort((a, b) => b.listings - a.listings).slice(0, 12);

  let options = [];
  let active = -1;
  let selectedName = "";

  const display = (name) => (name && brands.has(name) ? `${name} (any model)` : name);

  function search(query) {
    const words = normalise(query).split(" ").filter(Boolean);
    if (!words.length) return popular;
    const matches = items
      .filter((item) => {
        const haystack = normalise(`${item.brand} ${item.model}`);
        return words.every((word) => haystack.includes(word));
      })
      .map((item) => {
        const model = normalise(item.model);
        const brand = normalise(item.brand);
        let score = 0;
        if (model.startsWith(words.at(-1))) score += 2;
        if (brand.startsWith(words[0])) score += 1;
        if (model === words.at(-1)) score += 2;
        return { item, score };
      })
      .sort((a, b) => b.score - a.score || b.item.listings - a.item.listings)
      .slice(0, 40)
      .map(({ item }) => item);
    const whole = normalise(query);
    const brandOptions = [...brands.entries()]
      .filter(([brand]) => normalise(brand).startsWith(whole))
      .slice(0, 2)
      .map(([brand, listings]) => ({ brand, model: null, listings }));
    return [...matches, ...brandOptions];
  }

  function setActive(index, scroll = true) {
    active = index;
    [...list.querySelectorAll('[role="option"]')].forEach((node, i) => node.setAttribute("aria-selected", String(i === index)));
    const node = list.querySelector(`#picker-option-${index}`);
    if (node) {
      input.setAttribute("aria-activedescendant", node.id);
      if (scroll) node.scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function render(query) {
    options = search(query);
    const words = normalise(query).split(" ").filter(Boolean);
    const children = [];
    if (!words.length) children.push(h("li", { class: "picker__group", role: "presentation" }, "Most listed cars"));
    if (!options.length) {
      children.push(h("li", { class: "picker__empty", role: "presentation" }, `No car matches “${query}”. Try a model name such as Swift, City or Innova.`));
    }
    options.forEach((option, index) => {
      const name = option.model ? `${option.brand} ${option.model}` : `${option.brand} (any model)`;
      const node = h(
        "li",
        { id: `picker-option-${index}`, class: "picker__option", role: "option", "aria-selected": "false" },
        h("span", { class: "avatar", "aria-hidden": "true" }, initials(option.brand)),
        h(
          "span",
          { class: "picker__option-main" },
          h("span", { class: "picker__option-name" }, highlighted(name, words)),
          h("span", { class: "picker__option-meta" }, option.model ? option.brand : "Brand only: a rougher estimate"),
        ),
        h("span", { class: "picker__option-count" }, `${int(option.listings)} listings`),
      );
      node.addEventListener("mousedown", (event) => {
        event.preventDefault();
        choose(index);
      });
      node.addEventListener("mousemove", () => active !== index && setActive(index, false));
      children.push(node);
    });
    list.replaceChildren(...children);
    setActive(options.length ? 0 : -1);
  }

  function open() {
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function close() {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function choose(index) {
    const option = options[index];
    if (!option) return;
    selectedName = option.model ? `${option.brand} ${option.model}` : option.brand;
    input.value = display(selectedName);
    close();
    onSelect({ name: selectedName, brand: option.brand, model: option.model, listings: option.listings });
  }

  input.addEventListener("focus", () => {
    input.select();
    render("");
    open();
  });
  input.addEventListener("input", () => {
    render(input.value);
    open();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (list.hidden) {
        render(input.value === display(selectedName) ? "" : input.value);
        open();
      } else if (options.length) setActive((active + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (options.length) setActive((active - 1 + options.length) % options.length);
    } else if (event.key === "Enter") {
      if (!list.hidden && active >= 0) {
        event.preventDefault();
        choose(active);
      }
    } else if (event.key === "Escape") {
      input.value = display(selectedName);
      close();
    }
  });
  input.addEventListener("blur", () => {
    input.value = display(selectedName);
    close();
  });
  clear.addEventListener("click", () => {
    input.value = "";
    input.focus();
    render("");
    open();
  });

  return {
    set(name) {
      selectedName = name;
      input.value = display(name);
    },
  };
}
