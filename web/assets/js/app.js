// AutoValue - start-up, routing, theme and server status.
import { api, cached } from "./api.js";
import { createEstimatePage } from "./estimate.js";
import { int, pct } from "./format.js";
import { createGarage } from "./garage.js";
import { icon } from "./icons.js";
import { renderMarket } from "./market.js";
import { renderModel } from "./model.js";
import { $, h } from "./ui.js";

const ROUTES = {
  "/": { view: "estimate", title: "AutoValue · Used-car price estimator" },
  "/market": { view: "market", title: "Market insights · AutoValue" },
  "/model": { view: "model", title: "How good is the model? · AutoValue" },
  "/about": { view: "about", title: "About the project · AutoValue" },
};

// ------------------------------------------------------------------ theme
function initTheme() {
  const button = $("#theme-btn");
  const system = window.matchMedia("(prefers-color-scheme: dark)");
  const apply = (theme) => {
    document.documentElement.dataset.theme = theme;
    button.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
  };
  apply(document.documentElement.dataset.theme || (system.matches ? "dark" : "light"));
  button.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem("autovalue.theme", next);
    } catch {
      /* ignore */
    }
    apply(next);
  });
  system.addEventListener("change", (event) => {
    let stored = null;
    try {
      stored = localStorage.getItem("autovalue.theme");
    } catch {
      /* ignore */
    }
    if (!stored) apply(event.matches ? "dark" : "light");
  });
}

// ----------------------------------------------------------------- status
function setStatus(online) {
  const node = $("#api-status");
  node.dataset.state = online ? "online" : "offline";
  $("#api-status-text").textContent = online ? "Model online" : "Server offline";
  node.title = online ? "Connected to the prediction server" : "Can't reach the prediction server";
}

async function checkHealth() {
  try {
    await api("/health");
    setStatus(true);
  } catch {
    setStatus(false);
  }
}

// ----------------------------------------------------------- about page
function fillFacts(performance) {
  const facts = {
    listings: int(performance.data.clean_rows),
    raw: int(performance.data.raw_rows),
    duplicates: int(performance.data.duplicate_rows_removed),
    typical: pct(performance.test_metrics.median_ape, 0),
    coverage: pct(performance.interval.test_coverage_percent, 0),
    confidence: `${performance.interval.confidence_percent}%`,
    r2: performance.test_metrics.r2.toFixed(2),
    model: performance.model_name,
    reference: String(performance.data.reference_year),
    yearmax: String(performance.data.year_max),
    test: int(performance.data.test_rows),
    brands: String(performance.data.brands),
  };
  document.querySelectorAll("[data-fact]").forEach((node) => {
    if (facts[node.dataset.fact] !== undefined) node.textContent = facts[node.dataset.fact];
  });
}

// ----------------------------------------------------------------- router
function start(estimate) {
  const rendered = new Set();
  const loaders = {
    market: () => renderMarket($("#market-root"), { onEstimate: (inputs) => openEstimate(estimate, inputs) }),
    model: () => renderModel($("#model-root")),
  };

  async function route() {
    const [path, queryString = ""] = location.hash.replace(/^#/, "").split("?");
    const match = ROUTES[path || "/"] || ROUTES["/"];
    document.querySelectorAll("[data-view]").forEach((view) => (view.hidden = view.dataset.view !== match.view));
    document.querySelectorAll(".nav a").forEach((link) => {
      if (link.dataset.route === match.view) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    document.title = match.title;
    if (match.view === "estimate") estimate.applyQuery(new URLSearchParams(queryString));
    if (loaders[match.view] && !rendered.has(match.view)) {
      rendered.add(match.view);
      try {
        await loaders[match.view]();
      } catch (error) {
        rendered.delete(match.view);
        const target = $(`#${match.view}-root`);
        target.replaceChildren(
          h(
            "div",
            { class: "callout callout--error", role: "alert" },
            icon("alert"),
            h("div", {}, h("strong", {}, "This page couldn't load. "), error.message),
            h("button", { type: "button", class: "btn btn--ghost btn--sm callout__action", onClick: route }, icon("refresh", "icon-sm"), "Try again"),
          ),
        );
      }
    }
  }

  window.addEventListener("hashchange", () => {
    route();
    window.scrollTo({ top: 0 });
  });
  route();
}

function openEstimate(estimate, inputs) {
  if (!["", "#/"].includes(location.hash) && !location.hash.startsWith("#/?")) location.hash = "#/";
  estimate.load(inputs);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ------------------------------------------------------------------- boot
async function boot() {
  initTheme();
  checkHealth();
  setInterval(checkHealth, 30_000);

  cached("/insights/performance")
    .then(fillFacts)
    .catch(() => {});

  let catalog;
  try {
    catalog = await api("/catalog/details");
  } catch (error) {
    setStatus(false);
    $("#results-skeleton").replaceChildren(
      h(
        "div",
        { class: "callout callout--error", role: "alert" },
        icon("alert"),
        h("div", {}, h("strong", {}, "Can't reach the prediction server. "), "Start it with ", h("code", {}, "uvicorn main:app --reload"), " and reload this page."),
      ),
    );
    return;
  }

  let estimate;
  const garage = createGarage({ onLoad: (inputs) => openEstimate(estimate, inputs) });
  estimate = createEstimatePage({ catalog, garage, setStatus });
  start(estimate);
  if (!location.hash.includes("?")) estimate.start();
}

boot();
