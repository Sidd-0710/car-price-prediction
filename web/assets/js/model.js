// The Model page: how the model was chosen and how accurate it is.
import { cached } from "./api.js";
import { barChart, columnChart, scatterChart } from "./charts.js";
import { int, lakh, lakhShort, pct, signedPct } from "./format.js";
import { chartCard, h, kpi } from "./ui.js";

const FEATURE_NAMES = {
  Model: "Car model",
  Age: "Age",
  Brand: "Brand",
  Transmission: "Gearbox",
  Fuel_Type: "Fuel",
  Kms_Driven: "Kilometres",
  Log_Kms: "Kilometres (log)",
  Seller_Type: "Seller type",
  Owner: "Previous owners",
  Kms_Per_Year: "Km per year",
  Trim: "Exact variant",
  Variant_Key: "Variant words",
  Platform: "Platform",
};

const BAND_TEXT = { "under 2 L": "< ₹2 L", "2 to 5 L": "₹2–5 L", "5 to 10 L": "₹5–10 L", "10 to 20 L": "₹10–20 L", "over 20 L": "> ₹20 L" };

export async function renderModel(root) {
  const data = await cached("/insights/performance");
  const scores = data.test_metrics;

  const tiles = h(
    "div",
    { class: "kpis" },
    kpi({ label: "Typical error", value: pct(scores.median_ape), sub: "half the test cars were closer than this" }),
    kpi({ label: "Average error", value: lakhShort(scores.mae), sub: "mean absolute error" }),
    kpi({ label: "R² score", value: scores.r2.toFixed(2), sub: "share of price differences explained" }),
    kpi({ label: "Within ±20%", value: pct(scores.within_20pct, 0), sub: "of unseen test cars" }),
    kpi({ label: "Honest range", value: pct(data.interval.test_coverage_percent, 0), sub: `of prices fell inside the ${data.interval.confidence_percent}% range` }),
  );

  const steps = [
    ["Clean", `${int(data.data.raw_rows)} → ${int(data.data.clean_rows)} rows`],
    ["Features", "brand, model, variant, age…"],
    ["Split", `${int(data.data.test_rows)} cars locked away`],
    ["Compare", "9 algorithms, 5-fold CV"],
    ["Tune", "random search, top 3"],
    ["Test", "one final exam"],
    ["Serve", "FastAPI + this site"],
  ];
  const pipeline = h(
    "article",
    { class: "card" },
    h("header", { class: "card__head" }, h("div", {}, h("h3", { class: "card__title" }, "How the model was built"), h("p", { class: "card__subtitle" }, "Every step runs with one command: python train.py"))),
    h("ol", { class: "pipeline" }, steps.map(([title, text]) => h("li", {}, h("strong", {}, title), h("span", {}, text)))),
  );

  // algorithm comparison - emphasis: the winner in colour, the rest muted
  const comparison = chartCard({ title: "Nine algorithms, compared fairly", subtitle: "Cross-validated average error in lakhs (lower is better). Winner highlighted." });
  const winner = data.comparison[0].model;
  barChart(comparison.chartEl, {
    rows: data.comparison.map((row) => ({ label: row.model, value: row.cv_mae, color: row.model === winner ? "var(--series-1)" : "var(--mark-muted)", row })),
    format: (value) => `₹${value.toFixed(2)}`,
    rowHeight: 30,
    thickness: 14,
    labelShare: 0.5,
    ariaLabel: "Cross-validated error for each algorithm",
    tipFor: (item) => ({
      title: item.label,
      rows: [
        { value: lakh(item.row.cv_mae), label: "average error" },
        { value: item.row.cv_r2.toFixed(3), label: "R²" },
        { value: pct(item.row.cv_medape), label: "typical error" },
      ],
      note: item.row.tuned ? "Hyper-parameters tuned" : "Default settings",
    }),
  });
  comparison.setTable(
    [
      { key: "model", label: "Algorithm" },
      { key: "cv_mae", label: "CV error", align: "right", format: (value) => value.toFixed(3) },
      { key: "cv_r2", label: "CV R²", align: "right", format: (value) => value.toFixed(3) },
      { key: "train_r2", label: "Train R²", align: "right", format: (value) => value.toFixed(3) },
      { key: "test_mae", label: "Test error", align: "right", format: (value) => value.toFixed(3) },
      { key: "test_r2", label: "Test R²", align: "right", format: (value) => value.toFixed(3) },
    ],
    data.comparison,
  );

  // actual vs predicted
  const scatter = chartCard({ title: "Predictions on cars it never saw", subtitle: `${int(data.test_points.length)} test cars. Dots on the line are perfect; log scale.` });
  scatterChart(scatter.chartEl, {
    points: data.test_points.map((point) => ({ x: point.actual, y: point.predicted, ...point })),
    format: String,
    xLabel: "Actual price (₹ lakh)",
    yLabel: "Predicted (₹ lakh)",
    ariaLabel: "Actual versus predicted price for the test cars",
    tipFor: (point) => ({
      title: `${point.name} (${point.year}, ${point.platform})`,
      rows: [
        { value: lakh(point.actual), label: "actual" },
        { value: lakh(point.predicted), label: "predicted" },
        { value: signedPct(((point.predicted - point.actual) / point.actual) * 100, 0), label: "error" },
      ],
    }),
  });
  scatter.setTable(
    [
      { key: "name", label: "Car" },
      { key: "year", label: "Year" },
      { key: "actual", label: "Actual", align: "right", format: lakhShort },
      { key: "predicted", label: "Predicted", align: "right", format: lakhShort },
    ],
    data.test_points,
  );

  // feature importance
  const importance = chartCard({ title: "What the model pays attention to", subtitle: "How much worse it gets (in lakhs) when one input is scrambled" });
  const features = [...data.feature_importance].sort((a, b) => b.mean - a.mean);
  barChart(importance.chartEl, {
    rows: features.map((row) => ({ label: FEATURE_NAMES[row.feature] || row.feature, value: Math.max(0, row.mean), raw: row })),
    format: (value) => value.toFixed(2),
    rowHeight: 30,
    thickness: 14,
    ariaLabel: "Permutation feature importance",
    tipFor: (item) => ({ title: item.label, rows: [{ value: `+${lakh(Math.max(0, item.raw.mean))}`, label: "error when scrambled" }], note: `± ${item.raw.std.toFixed(3)} between repeats` }),
  });
  importance.setTable(
    [
      { key: "feature", label: "Input", format: (value) => FEATURE_NAMES[value] || value },
      { key: "mean", label: "Error increase (lakh)", align: "right", format: (value) => value.toFixed(3) },
    ],
    features,
  );

  // accuracy by price band
  const bands = chartCard({ title: "Accuracy by price", subtitle: "Typical error (%) for test cars in each price band" });
  columnChart(bands.chartEl, {
    rows: data.error_by_price_band.map((band) => ({ label: BAND_TEXT[band.band] || band.band, tick: BAND_TEXT[band.band] || band.band, value: band.median_ape, cars: band.cars })),
    height: 250,
    maxWidth: 28,
    format: (value) => `${value.toFixed(0)}%`,
    ariaLabel: "Typical error by price band",
    tipFor: (row) => ({ title: row.label, rows: [{ value: pct(row.value), label: "typical error" }], note: `${int(row.cars)} test cars` }),
  });
  bands.setTable(
    [
      { key: "band", label: "Price band", format: (value) => BAND_TEXT[value] || value },
      { key: "cars", label: "Test cars", align: "right", format: int },
      { key: "median_ape", label: "Typical error", align: "right", format: (value) => pct(value) },
    ],
    data.error_by_price_band,
  );

  const faq = [
    ["What is cross-validation?", "The training cars are split into 5 parts. The model learns from 4 parts and is graded on the 5th, five times over, so every algorithm gets several exams instead of one lucky one. That is how the nine algorithms were compared fairly."],
    ["What is the test set?", `${int(data.data.test_rows)} cars (20%) were locked away before any training and used exactly once, at the very end. Their scores are the honest measure of how the model does on cars it has never seen.`],
    ["What does R² mean?", "How much of the variation in prices the model explains: 0 means nothing, 1 means everything. It is sensitive to a few very expensive cars, which is why the typical percentage error is shown too."],
    ["How is the price range made?", `The model's past mistakes were measured, and the range covers the middle ${data.interval.confidence_percent}% of them. On the test cars, ${pct(data.interval.test_coverage_percent, 0)} of real prices fell inside it, so the range is honest.`],
    ["Why does plain linear regression do so well?", "The model works on the logarithm of the price, where depreciation is roughly a fixed percentage per year. A straight line captures that well; boosted trees add the remaining detail."],
  ];
  const explainer = h(
    "article",
    { class: "card" },
    h("header", { class: "card__head" }, h("div", {}, h("h3", { class: "card__title" }, "Reading these numbers"))),
    h("div", { class: "faq" }, faq.map(([question, answer]) => h("details", {}, h("summary", {}, question), h("p", {}, answer)))),
  );

  root.replaceChildren(
    tiles,
    h(
      "div",
      { class: "stack" },
      pipeline,
      h("div", { class: "grid-2" }, comparison.card, scatter.card),
      h("div", { class: "grid-2" }, importance.card, bands.card),
      explainer,
    ),
  );
}
