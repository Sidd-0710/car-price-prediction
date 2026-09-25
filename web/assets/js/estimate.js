// The Estimate page: form -> POST /analyze -> result card and charts. Updates live.
import { api, ApiError, cached } from "./api.js";
import { columnChart, divergingBars, lineChart } from "./charts.js";
import { initials, int, km, lakh, lakhShort, rupees, signedLakh, signedPct } from "./format.js";
import { icon } from "./icons.js";
import { createPicker } from "./picker.js";
import { $, chartCard, copyText, countTo, h, renderTable, segmented, toast } from "./ui.js";

const THIS_YEAR = new Date().getFullYear();
const STORAGE_KEY = "autovalue.last.v2";
const KMS_SLIDER_MAX = 300_000;
const MINOR_EFFECT = 2.5; // % - smaller price changes are listed as "little effect"

const DEFAULTS = { car: "Maruti Suzuki Swift", variant: "VXI", year: 2019, kms: 50_000, fuel: "Petrol", transmission: "Manual", platform: "CarDekho", owner: 0 };
const POPULAR = ["Maruti Suzuki Swift", "Hyundai Creta", "Honda City", "Kia Seltos", "Tata Nexon", "Maruti Suzuki Baleno", "Toyota Innova Crysta"];

const FUELS = ["Petrol", "Diesel", "CNG", "Electric"].map((value) => ({ value, label: value }));
const GEARBOXES = ["Manual", "Automatic"].map((value) => ({ value, label: value }));
const PLATFORMS = [
  { value: "CarDekho", label: "CarDekho", note: "Open marketplace: private owners and dealers." },
  { value: "Cars24", label: "Cars24", note: "Online dealer that buys, inspects and resells cars." },
  { value: "Spinny", label: "Spinny", note: "Online dealer that buys, inspects and resells cars." },
];
const MAX_VARIANT_OPTIONS = 80;
const OWNERS = [
  { value: 0, label: "1st", title: "First owner" },
  { value: 1, label: "2nd", title: "Second owner" },
  { value: 2, label: "3rd", title: "Third owner" },
  { value: 3, label: "4th+", title: "Fourth owner or more" },
];
const OWNER_TEXT = ["first owner", "second owner", "third owner", "fourth owner or more"];
const BAND_TEXT = { "under 2 L": "under ₹2 L", "2 to 5 L": "₹2–5 L", "5 to 10 L": "₹5–10 L", "10 to 20 L": "₹10–20 L", "over 20 L": "over ₹20 L" };

const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

function readSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

export function createEstimatePage({ catalog, garage, setStatus }) {
  const known = new Set([...catalog.map((item) => `${item.brand} ${item.model}`), ...catalog.map((item) => item.brand)]);
  const detailsOf = new Map(catalog.map((item) => [`${item.brand} ${item.model}`, item]));
  let variantInfo = { car: "", variants: [] };

  let state = sanitize({ ...DEFAULTS, ...readSaved() });
  let data = null;
  let curveMode = "year";
  let timer = null;
  let controller = null;

  // ------------------------------------------------------------ controls
  const picker = createPicker($("#picker"), {
    items: catalog,
    onSelect: ({ name }) => changeCar(name),
  });
  const variantSelect = $("#variant-select");
  variantSelect.addEventListener("change", () => {
    const chosen = variantInfo.variants.find((variant) => variant.name === variantSelect.value);
    // a variant usually implies its fuel and gearbox (e.g. "VXI AMT" is an automatic)
    update(chosen ? { variant: chosen.name, fuel: chosen.fuel, transmission: chosen.transmission } : { variant: "" });
  });

  const yearRange = $("#year-range");
  const yearInput = $("#year-input");
  const kmsRange = $("#kms-range");
  const kmsInput = $("#kms-input");
  yearRange.max = yearInput.max = String(THIS_YEAR);
  $("#year-max").textContent = String(THIS_YEAR);

  yearRange.addEventListener("input", () => update({ year: Number(yearRange.value) }));
  yearInput.addEventListener("change", () => {
    const value = parseInt(yearInput.value, 10);
    update({ year: Number.isFinite(value) ? clamp(value, 1990, THIS_YEAR) : state.year });
  });
  kmsRange.addEventListener("input", () => update({ kms: Number(kmsRange.value) }));
  kmsInput.addEventListener("change", () => {
    const value = parseInt(String(kmsInput.value).replace(/[^\d]/g, ""), 10);
    update({ kms: Number.isFinite(value) ? clamp(value, 0, 1_000_000) : state.kms });
  });

  const fuel = segmented($("#seg-fuel"), { label: "Fuel type", options: FUELS, value: state.fuel, onChange: (value) => update({ fuel: value }) });
  const gearbox = segmented($("#seg-gearbox"), { label: "Gearbox", options: GEARBOXES, value: state.transmission, onChange: (value) => update({ transmission: value }) });
  const platform = segmented($("#seg-platform"), { label: "Listed on", options: PLATFORMS, value: state.platform, onChange: (value) => update({ platform: value }) });
  const owner = segmented($("#seg-owner"), { label: "Previous owners", options: OWNERS, value: state.owner, onChange: (value) => update({ owner: value }) });

  const popular = POPULAR.filter((name) => detailsOf.has(name));
  const chips = popular.map((name) =>
    h("button", { type: "button", class: "chip", "aria-pressed": "false", onClick: () => changeCar(name) }, detailsOf.get(name).model),
  );
  $("#popular-chips").replaceChildren(...chips);

  $("#reset-btn").addEventListener("click", () => {
    update({ ...DEFAULTS });
    toast("Back to the example car");
  });

  /** A new car: forget the old variant, and pick a fuel and gearbox the model is sold with. */
  function changeCar(name) {
    const details = detailsOf.get(name);
    const changes = { car: name, variant: "" };
    if (details && !details.fuels.includes(state.fuel)) changes.fuel = details.fuels[0];
    if (details && !details.transmissions.includes(state.transmission)) changes.transmission = details.transmissions[0];
    update(changes);
  }

  async function loadVariants() {
    const car = state.car;
    if (variantInfo.car === car) return;
    variantInfo = { car, variants: [] };
    if (!detailsOf.has(car)) {
      renderVariantOptions();
      return;
    }
    try {
      const info = await cached(`/catalog/variants?car=${encodeURIComponent(car)}`);
      if (state.car !== car) return; // the user already picked another car
      variantInfo = { car, variants: info.variants };
    } catch {
      variantInfo = { car, variants: [] };
    }
    renderVariantOptions();
  }

  function renderVariantOptions() {
    const variants = variantInfo.variants.slice(0, MAX_VARIANT_OPTIONS);
    const wanted = state.variant.toLowerCase();
    const current = variantInfo.variants.find((variant) => variant.name.toLowerCase() === wanted);
    if (current && !variants.includes(current)) variants.push(current);
    const options = [h("option", { value: "" }, variants.length ? "Not sure / any variant" : "No variants listed for this car")];
    if (state.variant && !current) options.push(h("option", { value: state.variant }, `${state.variant} (not in the listings)`));
    for (const variant of variants) {
      options.push(h("option", { value: variant.name }, `${variant.name}  ·  ${variant.fuel}, ${variant.transmission}  ·  ${int(variant.listings)} listed`));
    }
    variantSelect.replaceChildren(...options);
    variantSelect.value = current ? current.name : state.variant;
    variantSelect.disabled = !variants.length && !state.variant;
    $("#variant-hint").textContent = variants.length ? `${variantInfo.variants.length} variants, most listed first` : "";
  }

  // -------------------------------------------------------- result cards
  const forecastCard = chartCard({ title: "Sell now or later?", subtitle: "" });
  const forecastHeadline = h("p", { class: "headline-stat", style: "margin-bottom:14px" });
  forecastCard.chartEl.before(forecastHeadline);

  const driversCard = chartCard({ title: "What moves the price", subtitle: "How your estimate changes if one detail were different" });

  const yearTab = h("button", { type: "button", role: "tab", "aria-selected": "true" }, "By year");
  const kmsTab = h("button", { type: "button", role: "tab", "aria-selected": "false" }, "By kilometres");
  const curveCard = chartCard({ title: "Explore the price curve", subtitle: "", tools: [h("div", { class: "card-tabs", role: "tablist", "aria-label": "Curve" }, yearTab, kmsTab)] });
  for (const [tab, mode] of [
    [yearTab, "year"],
    [kmsTab, "kms"],
  ]) {
    tab.addEventListener("click", () => {
      curveMode = mode;
      yearTab.setAttribute("aria-selected", String(mode === "year"));
      kmsTab.setAttribute("aria-selected", String(mode === "kms"));
      if (data) renderCurve();
    });
  }

  const similarBody = h("div", { class: "table-wrap" });
  const similarSubtitle = h("p", { class: "card__subtitle" });
  const similarCard = h(
    "article",
    { class: "card" },
    h("header", { class: "card__head" }, h("div", {}, h("h3", { class: "card__title" }, "Real listings like yours"), similarSubtitle)),
    h("div", { class: "card__body" }, similarBody),
  );

  $("#results-grid").replaceChildren(forecastCard.card, driversCard.card);
  $("#curve-slot").replaceChildren(curveCard.card);
  $("#similar-slot").replaceChildren(similarCard);

  $("#save-btn").addEventListener("click", () => {
    if (!data) return;
    garage.add({
      name: data.car.model_known ? data.car.matched_name : `${data.car.brand} (any model)`,
      brand: data.car.brand,
      inputs: { ...state },
      estimate: { price: data.estimate.price, lower: data.estimate.lower, upper: data.estimate.upper },
    });
    $("#save-btn-label").textContent = "Saved";
  });
  $("#copy-btn").addEventListener("click", async () => {
    if (!data) return;
    const { estimate } = data;
    const text = [
      "AutoValue estimate",
      `${describeCar()}`,
      `Estimated resale value: ${lakh(estimate.price)} (about ${rupees(estimate.price)})`,
      `Likely range (${estimate.confidence_percent}%): ${lakhShort(estimate.lower)} to ${lakhShort(estimate.upper)}`,
      `Based on ${int(data.car.listings)} listings of this model (2025–${data.reference_year}). A guide, not a valuation.`,
      shareUrl(),
    ].join("\n");
    if (await copyText(text)) toast("Summary copied");
  });
  $("#share-btn").addEventListener("click", async () => {
    if (await copyText(shareUrl())) toast("Link copied: it opens this exact estimate");
  });

  // ---------------------------------------------------------------- state
  function sanitize(input) {
    const next = { ...DEFAULTS, ...input };
    next.car = typeof next.car === "string" && next.car.trim() ? next.car.trim() : DEFAULTS.car;
    next.variant = typeof next.variant === "string" ? next.variant.trim().slice(0, 60) : "";
    next.year = clamp(parseInt(next.year, 10) || DEFAULTS.year, 1990, THIS_YEAR);
    next.kms = clamp(parseInt(next.kms, 10) || 0, 0, 1_000_000);
    if (!FUELS.some((option) => option.value === next.fuel)) next.fuel = DEFAULTS.fuel;
    if (!GEARBOXES.some((option) => option.value === next.transmission)) next.transmission = DEFAULTS.transmission;
    if (!PLATFORMS.some((option) => option.value === next.platform)) next.platform = DEFAULTS.platform;
    next.owner = clamp(parseInt(next.owner, 10) || 0, 0, 3);
    return next;
  }

  function query() {
    return new URLSearchParams({
      car: state.car,
      variant: state.variant,
      year: state.year,
      kms: state.kms,
      fuel: state.fuel,
      gearbox: state.transmission,
      platform: state.platform,
      owner: state.owner,
    }).toString();
  }

  const shareUrl = () => `${location.origin}${location.pathname}#/?${query()}`;

  function describeCar() {
    const name = [state.car, state.variant].filter(Boolean).join(" ");
    return `${name}, ${state.year}, ${km(state.kms)}, ${state.fuel}, ${state.transmission}, ${OWNER_TEXT[state.owner]}, listed on ${state.platform}`;
  }

  function syncControls() {
    picker.set(state.car);
    const details = detailsOf.get(state.car);
    $("#picker-note").textContent = details
      ? `The model learned from ${int(details.listings)} listings of this car.`
      : known.has(state.car)
        ? "Only the brand is known, so the estimate is rougher."
        : "";
    chips.forEach((chip, i) => chip.setAttribute("aria-pressed", String(popular[i] === state.car)));
    if (variantInfo.car !== state.car) loadVariants();
    else if (variantSelect.value !== state.variant) renderVariantOptions();

    yearRange.value = String(clamp(state.year, Number(yearRange.min), THIS_YEAR));
    yearRange.style.setProperty("--pct", `${((yearRange.value - yearRange.min) / (yearRange.max - yearRange.min)) * 100}%`);
    if (document.activeElement !== yearInput) yearInput.value = String(state.year);
    const age = THIS_YEAR - state.year;
    $("#year-hint").textContent = age <= 0 ? "Registered this year" : `${age} ${age === 1 ? "year" : "years"} old`;

    kmsRange.value = String(Math.min(state.kms, KMS_SLIDER_MAX));
    kmsRange.style.setProperty("--pct", `${(Math.min(state.kms, KMS_SLIDER_MAX) / KMS_SLIDER_MAX) * 100}%`);
    if (document.activeElement !== kmsInput) kmsInput.value = String(state.kms);
    $("#kms-hint").textContent = `about ${int(state.kms / Math.max(age, 1))} km a year`;

    fuel.set(state.fuel);
    fuel.setAvailable(details?.fuels);
    gearbox.set(state.transmission);
    gearbox.setAvailable(details?.transmissions);
    platform.set(state.platform);
    $("#platform-note").textContent = PLATFORMS.find((option) => option.value === state.platform).note;
    owner.set(state.owner);
  }

  function update(changes, { immediate = false } = {}) {
    state = sanitize({ ...state, ...changes });
    syncControls();
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* ignore */
    }
    if (location.hash.startsWith("#/?") || location.hash === "" || location.hash === "#/") {
      history.replaceState(null, "", `#/?${query()}`);
    }
    clearTimeout(timer);
    $("#car-form").classList.add("is-busy");
    timer = setTimeout(analyze, immediate ? 0 : 220);
  }

  // ---------------------------------------------------------------- fetch
  async function analyze() {
    controller?.abort();
    controller = new AbortController();
    const results = $("#results");
    results.classList.add("is-refreshing");
    results.setAttribute("aria-busy", "true");
    try {
      const body = {
        Car_Name: state.car,
        Variant: state.variant || null,
        Year: state.year,
        Kms_Driven: state.kms,
        Fuel_Type: state.fuel,
        Transmission: state.transmission,
        Owner: state.owner,
        Platform: state.platform,
      };
      data = await api("/analyze", { method: "POST", body, signal: controller.signal });
      setStatus(true);
      render();
    } catch (error) {
      if (error.name === "AbortError") return;
      showError(error);
    } finally {
      results.classList.remove("is-refreshing");
      results.setAttribute("aria-busy", "false");
      $("#car-form").classList.remove("is-busy");
    }
  }

  function showError(error) {
    const offline = !(error instanceof ApiError) || error.status === 0;
    if (offline) setStatus(false);
    let action;
    if (error.suggestions?.length) {
      action = h(
        "div",
        { class: "chips", style: "margin-top:10px" },
        h("span", { class: "field__hint", style: "align-self:center" }, "Did you mean"),
        error.suggestions.map((name) => h("button", { type: "button", class: "chip", onClick: () => update({ car: name }, { immediate: true }) }, name)),
      );
    } else if (error.status === 422) {
      action = h("button", { type: "button", class: "btn btn--ghost btn--sm", style: "margin-top:10px", onClick: () => $("#picker-input").focus() }, icon("search", "icon-sm"), "Choose a car from the list");
    } else {
      action = h("button", { type: "button", class: "btn btn--ghost btn--sm", style: "margin-top:10px", onClick: () => update({}, { immediate: true }) }, icon("refresh", "icon-sm"), "Try again");
    }
    const message = error.status === 422 ? error.message.replace(/ Did you mean: \[.*?\]\?/, "") : error.message;
    $("#results-error").replaceChildren(
      h("div", { class: "callout callout--error", role: "alert" }, icon("alert"), h("div", {}, h("strong", {}, offline ? "The server isn't responding. " : "Couldn't estimate this car. "), message, h("div", {}, action))),
    );
    $("#results-skeleton").hidden = true;
    $("#results-content").hidden = !data;
    $("#results-content").classList.add("is-stale");
  }

  // --------------------------------------------------------------- render
  function render() {
    $("#results-skeleton").hidden = true;
    $("#results-error").replaceChildren();
    $("#results-content").hidden = false;
    $("#results-content").classList.remove("is-stale");
    renderEstimate();
    renderAlerts();
    renderForecast();
    renderDrivers();
    renderCurve();
    renderSimilar();
    requestAnimationFrame(() => {
      const box = resultCard.getBoundingClientRect();
      resultInView = box.bottom > 0 && box.top < window.innerHeight;
      refreshMobileBar();
    });
  }

  function renderEstimate() {
    const { estimate, car, accuracy, forecast } = data;
    $("#matched-avatar").textContent = initials(car.brand);
    $("#matched-name").textContent = car.model_known ? car.matched_name : `${car.brand} (any model)`;
    const crore = estimate.price >= 100;
    $("#price-unit").textContent = crore ? "crore" : "lakh";
    countTo($("#price-value"), estimate.price, (value) => `₹${(crore ? value / 100 : value).toFixed(2)}`);
    $("#price-full").textContent = `≈ ${rupees(estimate.price)}`;

    const spread = Math.max(estimate.upper - estimate.lower, 0.01);
    const low = Math.max(0, estimate.lower - spread * 0.45);
    const high = estimate.upper + spread * 0.45;
    const position = (value) => ((value - low) / (high - low)) * 100;
    $("#gauge-fill").style.left = `${position(estimate.lower)}%`;
    $("#gauge-fill").style.width = `${position(estimate.upper) - position(estimate.lower)}%`;
    $("#gauge-marker").style.left = `${position(estimate.price)}%`;
    $("#gauge-low").textContent = lakhShort(estimate.lower);
    $("#gauge-high").textContent = lakhShort(estimate.upper);
    $("#gauge-caption").textContent = `${estimate.confidence_percent}% likely range`;

    const age = Math.max(0, THIS_YEAR - state.year);
    $("#stat-age").textContent = age === 0 ? "New" : `${age} ${age === 1 ? "yr" : "yrs"}`;
    $("#stat-annual").textContent = km(forecast.annual_kms);
    $("#stat-accuracy").textContent = accuracy ? `±${accuracy.median_ape.toFixed(0)}%` : "n/a";
    $("#stat-accuracy-label").textContent = accuracy ? `Typical error, ${BAND_TEXT[accuracy.band] || accuracy.band} cars` : "Typical error";

    const saved = garage.has({ ...state });
    $("#save-btn-label").textContent = saved ? "Saved" : "Save to garage";

    $("#mobile-bar-label").textContent = `${car.model_known ? car.matched_name : car.brand} · ${state.year}`;
    $("#mobile-bar-price").textContent = lakh(estimate.price);
  }

  function renderAlerts() {
    const notes = data.estimate.warnings;
    $("#alerts").replaceChildren(
      ...(notes.length
        ? [h("div", { class: "callout", role: "note" }, icon("alert"), notes.length === 1 ? h("div", {}, notes[0]) : h("ul", {}, notes.map((note) => h("li", {}, note))))]
        : []),
    );
  }

  function renderForecast() {
    const { points, annual_kms } = data.forecast;
    const now = points[0];
    const nextYear = points[1];
    const threeYears = points[3];
    forecastCard.setSubtitle(`Estimated value as the car ages, at about ${int(annual_kms)} km a year`);
    const loss = now.price - nextYear.price;
    forecastHeadline.replaceChildren(
      ...(loss > 0.005
        ? ["Waiting a year could cost about ", h("strong", {}, lakh(loss)), ` (${signedPct(nextYear.percent)}). `]
        : ["The model expects the value to hold for about a year. "]),
      "In 3 years it may be worth ",
      h("strong", {}, lakh(threeYears.price)),
      ".",
    );
    const rows = points.map((point) => ({
      label: point.years ? `In ${point.years} ${point.years === 1 ? "year" : "years"}` : "Today",
      tick: point.years ? `+${point.years} yr` : "Now",
      value: point.price,
      color: point.years ? "var(--series-1-soft)" : "var(--series-1)",
      point,
    }));
    columnChart(forecastCard.chartEl, {
      rows,
      height: 220,
      maxWidth: 30,
      format: (value) => `₹${value.toFixed(2)}`,
      ariaLabel: `Estimated value today and for the next ${points.length - 1} years`,
      tipFor: (row) => ({
        title: row.label,
        rows: [{ value: lakh(row.value) }, ...(row.point.years ? [{ value: signedPct(row.point.percent), label: "vs today" }] : [])],
        note: `about ${km(row.point.kms)} on the clock`,
      }),
    });
    forecastCard.setTable(
      [
        { key: "label", label: "When" },
        { key: "value", label: "Estimate", align: "right", format: lakh },
        { key: "percent", label: "Change", align: "right", format: (_, row) => (row.point.years ? signedPct(row.point.percent) : "–") },
        { key: "kms", label: "Kilometres", align: "right", format: (_, row) => int(row.point.kms) },
      ],
      rows,
    );
  }

  function renderDrivers() {
    const shown = data.drivers.filter((driver) => Math.abs(driver.percent) >= MINOR_EFFECT).slice(0, 7);
    const minor = data.drivers.filter((driver) => Math.abs(driver.percent) < MINOR_EFFECT);
    if (shown.length) {
      divergingBars(driversCard.chartEl, {
        rows: shown.map((driver) => ({ label: driver.label, value: driver.delta, driver })),
        format: signedLakh,
        ariaLabel: "How the estimate changes when one detail is different",
        tipFor: (row) => ({
          title: row.label,
          rows: [
            { value: lakh(row.driver.price), label: "new estimate" },
            { value: signedPct(row.driver.percent), label: "change" },
          ],
        }),
      });
    } else {
      driversCard.chartEl.replaceChildren(h("p", { class: "card__subtitle" }, "No single detail changes this estimate by much."));
    }
    driversCard.setFoot(minor.length ? `Little effect for this car: ${minor.map((driver) => driver.label).join("; ")}.` : null);
    driversCard.setTable(
      [
        { key: "label", label: "If the car had…" },
        { key: "price", label: "Estimate", align: "right", format: lakh },
        { key: "delta", label: "Difference", align: "right", format: signedLakh },
        { key: "percent", label: "%", align: "right", format: (value) => signedPct(value) },
      ],
      data.drivers,
    );
  }

  function renderCurve() {
    const { estimate, reference_year: snapshot } = data;
    const byYear = curveMode === "year";
    const curve = byYear ? data.year_curve : data.kms_curve;
    const markerX = byYear ? Math.min(state.year, snapshot) : Math.min(state.kms, 200_000);
    const markerPoint = curve.find((point) => point.x === markerX);
    const markerY = byYear || state.kms <= 200_000 ? estimate.price : markerPoint?.price ?? estimate.price;
    curveCard.setSubtitle(
      byYear
        ? `${data.car.matched_name} with ${km(state.kms)}, everything else as you entered it`
        : `${data.car.matched_name} registered in ${state.year}, everything else as you entered it`,
    );
    lineChart(curveCard.chartEl, {
      height: 300,
      series: [
        {
          name: "Estimate",
          color: "var(--series-1)",
          points: curve.map((point) => ({ x: point.x, y: point.price })),
          band: curve.map((point) => ({ x: point.x, lo: point.lower, hi: point.upper })),
          bandLabel: "likely range",
        },
      ],
      marker: { x: markerX, y: markerY, label: byYear && state.year > snapshot ? `Your car (as ${snapshot})` : "Your car", color: "var(--ink)" },
      legend: [
        { label: "Estimated price", color: "var(--series-1)", shape: "line" },
        { label: "Likely range", color: "var(--series-1)", shape: "band" },
        { label: "Your car", color: "var(--ink)", shape: "dot" },
      ],
      xFormat: byYear ? String : (value) => (value ? `${value / 1000}k` : "0"),
      tipTitle: byYear ? (value) => `Registered in ${value}` : (value) => km(value),
      yFormat: (value) => `₹${value} L`,
      valueFormat: lakh,
      xLabel: byYear ? "Registration year" : "Kilometres driven",
      ariaLabel: byYear ? "Estimated price by registration year" : "Estimated price by kilometres driven",
    });
    curveCard.setTable(
      [
        { key: "x", label: byYear ? "Year" : "Kilometres", format: byYear ? String : int },
        { key: "price", label: "Estimate", align: "right", format: lakh },
        { key: "lower", label: "Likely range", align: "right", format: (_, row) => `${lakhShort(row.lower)} – ${lakhShort(row.upper)}` },
      ],
      curve,
    );
  }

  function renderSimilar() {
    const { similar, estimate, car } = data;
    const sameVariant = similar.filter((row) => row.same_variant).length;
    similarSubtitle.textContent = similar.length
      ? `The ${similar.length} ${car.model_known ? `${car.brand} ${car.model}` : car.brand} listings closest to yours` +
        (sameVariant ? `, ${sameVariant} of the same variant` : "") +
        ". Asking prices, 2025–2026."
      : "";
    if (!similar.length) {
      similarBody.replaceChildren(h("p", { class: "card__subtitle" }, "There are no listings of this car in the data."));
      return;
    }
    const table = renderTable(
      [
        {
          key: "name",
          label: "Listing",
          render: (row) =>
            h(
              "div",
              {},
              h("span", { class: "cell-strong" }, row.name),
              row.same_variant ? h("span", { class: "badge-inline" }, "same variant") : null,
              h("span", { class: "cell-sub" }, `${row.platform}${row.city ? ` · ${row.city}` : ""} · ${row.owner}`),
            ),
        },
        { key: "year", label: "Year" },
        { key: "kms", label: "Km", align: "right", format: int },
        { key: "fuel", label: "Fuel" },
        { key: "transmission", label: "Gearbox" },
        { key: "price", label: "Price", align: "right", format: lakhShort },
        {
          key: "diff",
          label: "vs estimate",
          align: "right",
          render: (row) => {
            const change = ((row.price - estimate.price) / estimate.price) * 100;
            return h("span", { class: `delta ${change >= 0 ? "delta--up" : "delta--down"}` }, signedPct(change, 0));
          },
        },
      ],
      similar,
    );
    table.classList.add("data--wide");
    similarBody.replaceChildren(table);
  }

  // On phones the result sits below the form: keep the price in a bar at the
  // bottom of the screen whenever the result card itself is out of sight.
  const mobileBar = $("#mobile-bar");
  const resultCard = $(".result-card");
  let resultInView = true;
  function refreshMobileBar() {
    mobileBar.classList.toggle("is-visible", !resultInView && Boolean(data) && !$('[data-view="estimate"]').hidden);
  }
  new IntersectionObserver(([entry]) => {
    resultInView = entry.isIntersecting;
    refreshMobileBar();
  }).observe(resultCard);
  window.addEventListener("hashchange", () => setTimeout(refreshMobileBar));
  $("#mobile-bar-btn").addEventListener("click", () => resultCard.scrollIntoView({ behavior: "smooth", block: "start" }));

  // ------------------------------------------------------------ public
  syncControls();

  return {
    start() {
      update({}, { immediate: true });
    },
    /** Apply ?car=...&year=... from the address bar. */
    applyQuery(params) {
      if (![...params.keys()].length) return;
      update(
        {
          car: params.get("car") ?? state.car,
          year: params.get("year") ?? state.year,
          kms: params.get("kms") ?? state.kms,
          fuel: params.get("fuel") ?? state.fuel,
          transmission: params.get("gearbox") ?? state.transmission,
          variant: params.get("variant") ?? (params.get("car") ? "" : state.variant),
          platform: params.get("platform") ?? state.platform,
          owner: params.get("owner") ?? state.owner,
        },
        { immediate: true },
      );
    },
    load(inputs) {
      update(inputs, { immediate: true });
    },
    redraw() {
      if (data) render();
    },
  };
}
