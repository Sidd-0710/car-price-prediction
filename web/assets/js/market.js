// The Market page: what the used-car listings look like.
import { cached } from "./api.js";
import { barChart, columnChart, lineChart } from "./charts.js";
import { int, km, lakh, lakhShort } from "./format.js";
import { icon } from "./icons.js";
import { $, chartCard, h, kpi, renderTable } from "./ui.js";

const BRAND_COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export async function renderMarket(root, { onEstimate }) {
  const data = await cached("/insights/market");
  const { kpis } = data;

  const tiles = h(
    "div",
    { class: "kpis" },
    kpi({ label: "Listings analysed", value: int(kpis.listings), sub: "unique cars after cleaning" }),
    kpi({ label: "Brands / models / variants", value: `${kpis.brands} / ${kpis.models}`, sub: `and ${int(kpis.variants)} variants` }),
    kpi({ label: "Median asking price", value: lakhShort(kpis.median_price), sub: `half the cars cost less than ${lakh(kpis.median_price)}` }),
    kpi({ label: "Registration years", value: `${kpis.year_min}–${kpis.year_max}`, sub: `${int(kpis.cars_2024_on)} cars from 2024 or newer` }),
  );

  // price distribution
  const histogram = chartCard({ title: "How much do used cars cost?", subtitle: "Number of listings in each ₹1 lakh price band" });
  const bins = data.histogram.bins;
  columnChart(histogram.chartEl, {
    rows: bins.map((bin) => ({ label: `₹${bin.from}–${bin.to} lakh`, value: bin.count, tick: bin.from % 5 === 0 ? `₹${bin.from}L` : "" })),
    height: 250,
    capLabels: false,
    yAxis: true,
    format: int,
    maxWidth: 40,
    tickAt: "start",
    ariaLabel: "Histogram of asking prices",
    tipFor: (row) => ({ title: row.label, rows: [{ value: int(row.value), label: "listings" }] }),
  });
  histogram.setFoot(`${int(data.histogram.above)} listings above ₹${data.histogram.cap} lakh are not shown.`);
  histogram.setTable(
    [
      { key: "label", label: "Price band" },
      { key: "value", label: "Listings", align: "right", format: int },
    ],
    bins.map((bin) => ({ label: `₹${bin.from}–${bin.to} lakh`, value: bin.count })),
  );

  // price by year
  const years = chartCard({ title: "Newer cars are worth more", subtitle: "Median asking price by registration year" });
  lineChart(years.chartEl, {
    series: [{ name: "Median price", color: "var(--series-1)", points: data.by_year.map((row) => ({ x: row.year, y: row.median, count: row.count })) }],
    height: 250,
    yFormat: (value) => `₹${value} L`,
    valueFormat: lakh,
    tipTitle: (value) => `Registered in ${value}`,
    tipNote: (value) => `${int(data.by_year.find((row) => row.year === value)?.count || 0)} listings`,
    ariaLabel: "Median price by registration year",
  });
  years.setTable(
    [
      { key: "year", label: "Year" },
      { key: "median", label: "Median price", align: "right", format: lakh },
      { key: "count", label: "Listings", align: "right", format: int },
    ],
    data.by_year,
  );

  // brands
  const brands = chartCard({ title: "Price by brand", subtitle: "Median asking price, brands with 30 or more listings" });
  barChart(brands.chartEl, {
    rows: data.brands.map((row) => ({ label: row.brand, value: row.median, count: row.count })),
    format: (value) => lakhShort(value),
    ariaLabel: "Median price by brand",
    tipFor: (row) => ({ title: row.label, rows: [{ value: lakh(row.value), label: "median" }], note: `${int(row.count)} listings` }),
  });
  brands.setTable(
    [
      { key: "brand", label: "Brand" },
      { key: "median", label: "Median price", align: "right", format: lakh },
      { key: "count", label: "Listings", align: "right", format: int },
    ],
    data.brands,
  );

  // depreciation
  const depreciation = chartCard({ title: "How fast the big four lose value", subtitle: "Median asking price by age, for the four most-listed brands" });
  const brandNames = Object.keys(data.depreciation);
  lineChart(depreciation.chartEl, {
    series: brandNames.map((brand, i) => ({ name: brand, color: BRAND_COLORS[i], points: data.depreciation[brand].map((row) => ({ x: row.age, y: row.median })) })),
    legend: brandNames.map((brand, i) => ({ label: brand, color: BRAND_COLORS[i], shape: "line" })),
    height: 270,
    xFormat: (value) => `${value}`,
    xLabel: "Age in years when listed",
    yFormat: (value) => `₹${value} L`,
    valueFormat: lakh,
    tipTitle: (value) => `${value} ${value === 1 ? "year" : "years"} old`,
    ariaLabel: "Median price by age for the four most listed brands",
  });
  depreciation.setTable(
    [{ key: "age", label: "Age" }, ...brandNames.map((brand) => ({ key: brand, label: brand, align: "right", format: (value) => (value === undefined ? "–" : lakhShort(value)) }))],
    [...new Set(brandNames.flatMap((brand) => data.depreciation[brand].map((row) => row.age)))]
      .sort((a, b) => a - b)
      .map((age) => Object.fromEntries([["age", age], ...brandNames.map((brand) => [brand, data.depreciation[brand].find((row) => row.age === age)?.median])])),
  );

  // small category cards
  const small = (title, subtitle, rows) => {
    const card = chartCard({ title, subtitle });
    barChart(card.chartEl, {
      rows: rows.map((row) => ({ label: row.label, value: row.median, count: row.count })),
      format: (value) => lakhShort(value),
      labelShare: 0.46,
      ariaLabel: title,
      tipFor: (row) => ({ title: row.label, rows: [{ value: lakh(row.value), label: "median" }], note: `${int(row.count)} listings` }),
    });
    card.setTable(
      [
        { key: "label", label: "Group" },
        { key: "median", label: "Median price", align: "right", format: lakh },
        { key: "count", label: "Listings", align: "right", format: int },
      ],
      rows,
    );
    return card.card;
  };

  // popular models table, searchable and sortable, with a shortcut to estimate
  let sortKey = "count";
  let filter = "";
  const tableHolder = h("div", { class: "table-wrap" });
  const search = h("input", { class: "search-input", type: "search", placeholder: "Filter models", "aria-label": "Filter popular models" });
  search.addEventListener("input", () => {
    filter = search.value.toLowerCase().trim();
    drawModels();
  });
  function drawModels() {
    const rows = data.popular_models
      .filter((row) => `${row.brand} ${row.model}`.toLowerCase().includes(filter))
      .sort((a, b) => (sortKey === "median" ? b.median - a.median : b.count - a.count));
    const sortButton = (key, text) =>
      h("button", { type: "button", "aria-label": `Sort by ${text}`, onClick: () => ((sortKey = key), drawModels()) }, text, sortKey === key ? " ↓" : "");
    const table = renderTable(
      [
        { key: "model", label: "Model", render: (row) => h("div", {}, h("span", { class: "cell-strong" }, `${row.brand} ${row.model}`)) },
        { key: "count", label: "Listings", align: "right", format: int },
        { key: "median", label: "Median price", align: "right", format: lakhShort },
        { key: "typical_year", label: "Typical year", align: "right" },
        { key: "typical_kms", label: "Typical km", align: "right", format: int },
        {
          key: "go",
          label: "",
          align: "right",
          render: (row) =>
            h(
              "button",
              {
                type: "button",
                class: "btn btn--ghost btn--sm",
                "aria-label": `Estimate a typical ${row.brand} ${row.model}`,
                onClick: () =>
                  onEstimate({
                    car: `${row.brand} ${row.model}`,
                    year: row.typical_year,
                    kms: row.typical_kms,
                    fuel: row.typical_fuel,
                    transmission: row.typical_transmission,
                    variant: "",
                    platform: "CarDekho",
                    owner: 0,
                  }),
              },
              "Estimate",
              icon("arrowRight", "icon-sm"),
            ),
        },
      ],
      rows,
    );
    table.querySelectorAll("th")[1].replaceChildren(sortButton("count", "Listings"));
    table.querySelectorAll("th")[2].replaceChildren(sortButton("median", "Median price"));
    tableHolder.replaceChildren(rows.length ? table : h("p", { class: "card__subtitle", style: "padding:12px 0" }, "No model matches that filter."));
  }
  drawModels();
  const models = h(
    "article",
    { class: "card" },
    h(
      "header",
      { class: "card__head" },
      h("div", {}, h("h3", { class: "card__title" }, "Most listed models"), h("p", { class: "card__subtitle" }, "Click Estimate to price a typical example")),
      h("div", { class: "search-field" }, icon("search", "icon-sm"), search),
    ),
    h("div", { class: "card__body" }, tableHolder),
  );

  root.replaceChildren(
    tiles,
    h(
      "div",
      { class: "stack" },
      h("div", { class: "grid-2" }, histogram.card, years.card),
      h("div", { class: "grid-2" }, brands.card, depreciation.card),
      h(
        "div",
        { class: "grid-4" },
        small("Fuel type", "Median price by fuel", data.by_fuel),
        small("Gearbox", "Median price by transmission", data.by_transmission),
        small("Ownership", "Median price by number of owners", data.by_owner),
        small("Platform", "Median price by where it is listed", data.by_platform),
      ),
      models,
    ),
  );
  $("#market-note").textContent = `Asking prices from ${int(kpis.listings)} listings on CarDekho, Cars24 and Spinny, collected 2025–${data.reference_year}. Median ${km(kpis.median_kms)} driven.`;
}
