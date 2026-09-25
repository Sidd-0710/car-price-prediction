// A small SVG chart library: line, column, bar, diverging bar and scatter.
// Charts redraw on resize, show a tooltip on hover, and can be explored with
// the arrow keys once focused. Colours come from CSS variables, so they follow the theme.

const NS = "http://www.w3.org/2000/svg";
const LOG_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200];

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  if (parent) parent.appendChild(node);
  return node;
}

function label(parent, x, y, content, attrs = {}) {
  const node = el("text", { x, y, ...attrs }, parent);
  node.textContent = content;
  return node;
}

export function niceTicks(min, max, count = 5) {
  if (max === min) max = min + 1;
  const raw = (max - min) / Math.max(count, 1);
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  const step = (fraction < 1.5 ? 1 : fraction < 3 ? 2 : fraction < 7 ? 5 : 10) * power;
  const ticks = [];
  for (let value = Math.floor(min / step) * step; value <= Math.ceil(max / step) * step + step / 2; value += step) {
    ticks.push(Number(value.toFixed(10)));
  }
  return ticks;
}

function linear(d0, d1, r0, r1) {
  const span = d1 - d0 || 1;
  const scale = (value) => r0 + ((value - d0) / span) * (r1 - r0);
  scale.invert = (pixel) => d0 + ((pixel - r0) / (r1 - r0)) * span;
  return scale;
}

function logarithmic(d0, d1, r0, r1) {
  const a = Math.log(d0);
  const b = Math.log(d1);
  return (value) => r0 + ((Math.log(Math.max(value, d0 / 2)) - a) / (b - a)) * (r1 - r0);
}

let measureContext;
function textWidth(text, font = "500 13px Inter, system-ui, sans-serif") {
  measureContext ??= document.createElement("canvas").getContext("2d");
  measureContext.font = font;
  return measureContext.measureText(text).width;
}

function fitText(text, maxWidth, font) {
  if (textWidth(text, font) <= maxWidth) return text;
  let cut = text;
  while (cut.length > 1 && textWidth(`${cut}…`, font) > maxWidth) cut = cut.slice(0, -1);
  return `${cut}…`;
}

/** Bar path with a 4px rounded end at x1 and a square end at the baseline x0. */
function horizontalBar(x0, x1, y, height, radius = 4) {
  const length = Math.abs(x1 - x0);
  if (length < 0.5) return "";
  const dir = x1 >= x0 ? 1 : -1;
  const r = Math.min(radius, length, height / 2);
  const xe = x1 - dir * r;
  return `M${x0},${y}H${xe}Q${x1},${y} ${x1},${y + r}V${y + height - r}Q${x1},${y + height} ${xe},${y + height}H${x0}Z`;
}

/** Column path with a rounded top and a square base at y0. */
function verticalBar(x, width, y0, y1, radius = 4) {
  const length = y0 - y1;
  if (length < 0.5) return "";
  const r = Math.min(radius, length, width / 2);
  return `M${x},${y0}V${y1 + r}Q${x},${y1} ${x + r},${y1}H${x + width - r}Q${x + width},${y1} ${x + width},${y1 + r}V${y0}Z`;
}

// ------------------------------------------------------------------ frame
function legendElement(items) {
  const wrap = document.createElement("div");
  wrap.className = "chart-legend";
  for (const item of items) {
    const entry = document.createElement("span");
    const key = document.createElement("i");
    key.className = `key-${item.shape || "rect"}`;
    key.style.background = item.color;
    entry.append(key, document.createTextNode(item.label));
    wrap.append(entry);
  }
  return wrap;
}

function tooltip(tipNode, holder) {
  return {
    show(x, y, { title, rows = [], note }) {
      tipNode.replaceChildren();
      if (title) {
        const head = document.createElement("div");
        head.className = "chart-tip__title";
        head.textContent = title;
        tipNode.append(head);
      }
      for (const row of rows) {
        const line = document.createElement("div");
        line.className = "chart-tip__row";
        if (row.color) {
          const key = document.createElement("i");
          key.className = row.shape === "rect" ? "key-rect" : "key-line";
          key.style.background = row.color;
          line.append(key);
        }
        const value = document.createElement("strong");
        value.textContent = row.value;
        line.append(value);
        if (row.label) {
          const text = document.createElement("span");
          text.textContent = row.label;
          line.append(text);
        }
        tipNode.append(line);
      }
      if (note) {
        const foot = document.createElement("div");
        foot.className = "chart-tip__note";
        foot.textContent = note;
        tipNode.append(foot);
      }
      tipNode.hidden = false;
      const width = tipNode.offsetWidth;
      const height = tipNode.offsetHeight;
      const room = holder.clientWidth;
      let left = x + 14;
      if (left + width > room) left = x - width - 14;
      if (left < 0) left = Math.max(0, Math.min(room - width, x - width / 2));
      let top = y - height - 12;
      if (top < -6) top = y + 16;
      tipNode.style.left = `${left}px`;
      tipNode.style.top = `${top}px`;
    },
    hide() {
      tipNode.hidden = true;
    },
  };
}

/** Mount a responsive SVG into `container`; `draw(svg, width, height, tip)` does the rest. */
function mount(container, height, draw, { legend, ariaLabel } = {}) {
  container._chart?.disconnect();
  container.classList.add("chart");
  container.replaceChildren();
  if (legend?.length) container.append(legendElement(legend));
  const holder = document.createElement("div");
  holder.style.position = "relative";
  container.append(holder);
  const tipNode = document.createElement("div");
  tipNode.className = "chart-tip";
  tipNode.hidden = true;

  let drawnWidth = 0;
  const render = () => {
    const width = Math.floor(holder.clientWidth);
    if (!width || width === drawnWidth) return;
    drawnWidth = width;
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": ariaLabel || "" });
    holder.replaceChildren(svg, tipNode);
    tipNode.hidden = true;
    draw(svg, width, height, tooltip(tipNode, holder));
  };
  const observer = new ResizeObserver(render);
  observer.observe(holder);
  container._chart = observer;
  render();
}

/** Arrow-key exploration: focus the chart, then Left/Right (or Up/Down) walk the marks. */
function keyboard(svg, count, showAt, hide, { vertical = false } = {}) {
  let index = -1;
  svg.setAttribute("tabindex", "0");
  const go = (next) => {
    index = Math.max(0, Math.min(count - 1, next));
    showAt(index);
  };
  svg.addEventListener("keydown", (event) => {
    const forward = vertical ? "ArrowDown" : "ArrowRight";
    const back = vertical ? "ArrowUp" : "ArrowLeft";
    if (event.key === forward) go(index + 1);
    else if (event.key === back) go(index < 0 ? count - 1 : index - 1);
    else if (event.key === "Home") go(0);
    else if (event.key === "End") go(count - 1);
    else if (event.key === "Escape") return hide();
    else return;
    event.preventDefault();
  });
  svg.addEventListener("focus", () => go(index < 0 ? 0 : index));
  svg.addEventListener("blur", hide);
  return { set: (next) => (index = next) };
}

// ------------------------------------------------------------ line chart
/**
 * series: [{ name, color, points: [{x, y}], band?: [{x, lo, hi}], bandLabel? }]
 * marker: { x, y, label, color }
 */
export function lineChart(container, options) {
  const {
    series,
    height = 280,
    xFormat = String,
    yFormat = String,
    tipTitle = xFormat,
    valueFormat = yFormat,
    xLabel,
    marker,
    legend,
    yZero = true,
    ariaLabel,
    tipNote,
  } = options;

  mount(
    container,
    height,
    (svg, width, H, tip) => {
      const m = { top: 16, right: 18, bottom: xLabel ? 50 : 30, left: 54 };
      const points = series.flatMap((line) => line.points);
      const xs = [...new Set(points.map((point) => point.x))].sort((a, b) => a - b);
      const highs = series.flatMap((line) => (line.band || []).map((point) => point.hi));
      const lows = series.flatMap((line) => (line.band || []).map((point) => point.lo));
      const yMax = Math.max(...points.map((point) => point.y), ...highs, marker ? marker.y : -Infinity);
      const yMin = yZero ? 0 : Math.min(...points.map((point) => point.y), ...lows);
      const yTicks = niceTicks(yMin, yMax, 5);
      const x = linear(xs[0], xs.at(-1), m.left, width - m.right);
      const y = linear(yTicks[0], yTicks.at(-1), H - m.bottom, m.top);

      const axes = el("g", {}, svg);
      yTicks.forEach((tick, i) => {
        el("line", { class: i === 0 ? "axis" : "grid", x1: m.left, x2: width - m.right, y1: y(tick), y2: y(tick) }, axes);
        label(axes, m.left - 10, y(tick) + 4, yFormat(tick), { "text-anchor": "end" });
      });
      const room = Math.max(2, Math.floor((width - m.left - m.right) / 84));
      niceTicks(xs[0], xs.at(-1), room)
        .filter((tick) => tick >= xs[0] && tick <= xs.at(-1))
        .forEach((tick) => label(axes, x(tick), H - m.bottom + 19, xFormat(tick), { "text-anchor": "middle" }));
      if (xLabel) label(axes, (m.left + width - m.right) / 2, H - 8, xLabel, { "text-anchor": "middle", class: "t-label" });

      for (const line of series) {
        if (line.band?.length) {
          const upper = line.band.map((point) => `${x(point.x)},${y(point.hi)}`);
          const lower = [...line.band].reverse().map((point) => `${x(point.x)},${y(point.lo)}`);
          el("path", { d: `M${upper.join("L")}L${lower.join("L")}Z`, fill: line.color, "fill-opacity": 0.13 }, svg);
        }
        const d = line.points.map((point, i) => `${i ? "L" : "M"}${x(point.x)},${y(point.y)}`).join("");
        el("path", { d, fill: "none", stroke: line.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round", class: "mark" }, svg);
      }

      if (marker) {
        const cx = x(marker.x);
        const cy = y(marker.y);
        el("circle", { cx, cy, r: 6.5, fill: marker.color || "var(--ink)", stroke: "var(--surface)", "stroke-width": 2.5 }, svg);
        if (marker.label) {
          const anchor = cx > width - m.right - 50 ? "end" : cx < m.left + 50 ? "start" : "middle";
          label(svg, cx, cy - 15, marker.label, { "text-anchor": anchor, class: "t-strong" });
        }
      }

      const cross = el("line", { class: "crosshair", y1: m.top, y2: H - m.bottom, visibility: "hidden" }, svg);
      const dots = series.map((line) => el("circle", { r: 4.5, fill: line.color, stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg));
      const hit = el("rect", { x: m.left, y: 0, width: Math.max(0, width - m.left - m.right), height: H - m.bottom, fill: "transparent" }, svg);

      const hide = () => {
        cross.setAttribute("visibility", "hidden");
        dots.forEach((dot) => dot.setAttribute("visibility", "hidden"));
        tip.hide();
      };
      const showAt = (index) => {
        const value = xs[index];
        const px = x(value);
        cross.setAttribute("x1", px);
        cross.setAttribute("x2", px);
        cross.setAttribute("visibility", "visible");
        const rows = [];
        let top = H;
        series.forEach((line, k) => {
          const point = line.points.find((p) => p.x === value);
          if (!point) return dots[k].setAttribute("visibility", "hidden");
          dots[k].setAttribute("cx", px);
          dots[k].setAttribute("cy", y(point.y));
          dots[k].setAttribute("visibility", "visible");
          top = Math.min(top, y(point.y));
          rows.push({ color: line.color, value: valueFormat(point.y), label: line.name });
          const band = line.band?.find((p) => p.x === value);
          if (band) rows.push({ value: `${valueFormat(band.lo)} – ${valueFormat(band.hi)}`, label: line.bandLabel || "range" });
        });
        tip.show(px, top, { title: tipTitle(value), rows, note: tipNote?.(value) });
      };
      const keys = keyboard(svg, xs.length, showAt, hide);
      const nearest = (event) => {
        const px = event.clientX - svg.getBoundingClientRect().left;
        const value = x.invert(px);
        let best = 0;
        xs.forEach((candidate, i) => {
          if (Math.abs(candidate - value) < Math.abs(xs[best] - value)) best = i;
        });
        keys.set(best);
        showAt(best);
      };
      hit.addEventListener("pointermove", nearest);
      hit.addEventListener("pointerdown", nearest);
      hit.addEventListener("pointerleave", hide);
    },
    { legend, ariaLabel },
  );
}

// ---------------------------------------------------------- column chart
/** rows: [{ label, value, color?, tick? }]  (tick = text under the column; omit for none) */
export function columnChart(container, options) {
  const { rows, height = 240, format = String, capLabels = true, yAxis = false, yFormat = format, tipFor, tickAt = "center", gap = 2, maxWidth = 24, ariaLabel, legend } = options;
  mount(
    container,
    height,
    (svg, width, H, tip) => {
      const m = { top: capLabels ? 24 : 12, right: 6, bottom: 30, left: yAxis ? 46 : 6 };
      const max = Math.max(0, ...rows.map((row) => row.value));
      const ticks = niceTicks(0, max || 1, 4);
      const top = yAxis ? ticks.at(-1) : max || 1;
      const y = linear(0, top, H - m.bottom, m.top);
      const band = (width - m.left - m.right) / rows.length;
      const barWidth = Math.max(2, Math.min(maxWidth, band - gap));

      if (yAxis) {
        ticks.forEach((tick, i) => {
          el("line", { class: i === 0 ? "axis" : "grid", x1: m.left, x2: width - m.right, y1: y(tick), y2: y(tick) }, svg);
          label(svg, m.left - 10, y(tick) + 4, yFormat(tick), { "text-anchor": "end" });
        });
      } else {
        el("line", { class: "axis", x1: m.left, x2: width - m.right, y1: y(0), y2: y(0) }, svg);
      }

      const bars = rows.map((row, i) => {
        const cx = m.left + band * i + band / 2;
        const bar = el("path", { d: verticalBar(cx - barWidth / 2, barWidth, y(0), y(row.value)), fill: row.color || "var(--series-1)", class: "mark" }, svg);
        if (capLabels) label(svg, cx, y(row.value) - 8, format(row.value), { "text-anchor": "middle", class: "t-value" });
        if (row.tick) {
          const tx = tickAt === "start" ? m.left + band * i : cx;
          label(svg, tx, H - m.bottom + 19, row.tick, { "text-anchor": "middle" });
        }
        return { bar, cx, row };
      });

      const hide = () => {
        bars.forEach(({ bar }) => bar.classList.remove("is-dim"));
        tip.hide();
      };
      const showAt = (index) => {
        bars.forEach(({ bar }, i) => bar.classList.toggle("is-dim", i !== index));
        const { cx, row } = bars[index];
        tip.show(cx, y(row.value), tipFor ? tipFor(row) : { title: row.label, rows: [{ value: format(row.value) }] });
      };
      const keys = keyboard(svg, rows.length, showAt, hide);
      rows.forEach((row, i) => {
        const hit = el("rect", { x: m.left + band * i, y: m.top - 16, width: band, height: H - m.top - m.bottom + 16, fill: "transparent" }, svg);
        const enter = () => {
          keys.set(i);
          showAt(i);
        };
        hit.addEventListener("pointerenter", enter);
        hit.addEventListener("pointerdown", enter);
        hit.addEventListener("pointerleave", hide);
      });
    },
    { ariaLabel, legend },
  );
}

// ---------------------------------------------------- horizontal bar chart
/** rows: [{ label, value, color? }] - one series; values printed at the bar tips. */
export function barChart(container, options) {
  const { rows, format = String, rowHeight = 34, thickness = 16, tipFor, ariaLabel, labelShare = 0.42, legend } = options;
  const H = rows.length * rowHeight + 6;
  mount(
    container,
    H,
    (svg, width, _H, tip) => {
      const labelFont = "400 13px Inter, system-ui, sans-serif";
      const valueFont = "650 12.5px Inter, system-ui, sans-serif";
      const labelWidth = Math.min(width * labelShare, Math.max(...rows.map((row) => textWidth(row.label, labelFont))) + 16);
      const valueWidth = Math.max(...rows.map((row) => textWidth(format(row.value), valueFont))) + 12;
      const max = Math.max(0, ...rows.map((row) => row.value)) || 1;
      const x = linear(0, max, labelWidth, width - valueWidth);
      el("line", { class: "axis", x1: labelWidth, x2: labelWidth, y1: 2, y2: H - 2 }, svg);

      const marks = rows.map((row, i) => {
        const yc = 3 + i * rowHeight + rowHeight / 2;
        label(svg, labelWidth - 10, yc + 4.5, fitText(row.label, labelWidth - 14, labelFont), { "text-anchor": "end", class: "t-label" });
        const end = x(Math.max(0, row.value));
        const bar = el("path", { d: horizontalBar(labelWidth, end, yc - thickness / 2, thickness), fill: row.color || "var(--series-1)", class: "mark" }, svg);
        label(svg, end + 7, yc + 4.5, format(row.value), { class: "t-value" });
        return { bar, yc, end, row };
      });

      const hide = () => {
        marks.forEach(({ bar }) => bar.classList.remove("is-dim"));
        tip.hide();
      };
      const showAt = (index) => {
        marks.forEach(({ bar }, i) => bar.classList.toggle("is-dim", i !== index));
        const { end, yc, row } = marks[index];
        tip.show(Math.min(end, width - 160), yc - thickness / 2, tipFor ? tipFor(row) : { title: row.label, rows: [{ value: format(row.value) }] });
      };
      const keys = keyboard(svg, rows.length, showAt, hide, { vertical: true });
      rows.forEach((_, i) => {
        const hit = el("rect", { x: 0, y: 3 + i * rowHeight, width, height: rowHeight, fill: "transparent" }, svg);
        const enter = () => {
          keys.set(i);
          showAt(i);
        };
        hit.addEventListener("pointerenter", enter);
        hit.addEventListener("pointerdown", enter);
        hit.addEventListener("pointerleave", hide);
      });
    },
    { ariaLabel, legend },
  );
}

// ------------------------------------------------------ diverging bars
/**
 * rows: [{ label, value }] - positive values grow right from a centre line, negative grow left.
 * Each label sits on its own line above its bar, so long labels are never cut off.
 */
export function divergingBars(container, options) {
  const { rows, format = String, rowHeight = 46, thickness = 14, tipFor, ariaLabel, positiveLabel = "Raises the price", negativeLabel = "Lowers the price" } = options;
  const H = rows.length * rowHeight + 4;
  mount(
    container,
    H,
    (svg, width, _H, tip) => {
      const labelFont = "400 13px Inter, system-ui, sans-serif";
      const valueFont = "650 12.5px Inter, system-ui, sans-serif";
      const valueWidth = Math.max(...rows.map((row) => textWidth(format(row.value), valueFont))) + 12;
      const limit = Math.max(...rows.map((row) => Math.abs(row.value))) || 1;
      const x = linear(-limit, limit, valueWidth, width - valueWidth);
      const zero = x(0);

      const marks = rows.map((row, i) => {
        const top = 2 + i * rowHeight;
        const barY = top + 20;
        const yc = barY + thickness / 2;
        label(svg, 0, top + 13, fitText(row.label, width, labelFont), { class: "t-label" });
        el("line", { class: "axis", x1: zero, x2: zero, y1: barY - 3, y2: barY + thickness + 3 }, svg);
        const end = x(row.value);
        const bar = el("path", { d: horizontalBar(zero, end, barY, thickness), fill: row.value >= 0 ? "var(--pos)" : "var(--neg)", class: "mark" }, svg);
        const positive = row.value >= 0;
        label(svg, positive ? end + 7 : end - 7, yc + 4.5, format(row.value), { "text-anchor": positive ? "start" : "end", class: "t-value" });
        return { bar, yc, end, row };
      });

      const hide = () => {
        marks.forEach(({ bar }) => bar.classList.remove("is-dim"));
        tip.hide();
      };
      const showAt = (index) => {
        marks.forEach(({ bar }, i) => bar.classList.toggle("is-dim", i !== index));
        const { end, yc, row } = marks[index];
        tip.show(Math.min(end, width - 160), yc - thickness / 2, tipFor ? tipFor(row) : { title: row.label, rows: [{ value: format(row.value) }] });
      };
      const keys = keyboard(svg, rows.length, showAt, hide, { vertical: true });
      rows.forEach((_, i) => {
        const hit = el("rect", { x: 0, y: 3 + i * rowHeight, width, height: rowHeight, fill: "transparent" }, svg);
        const enter = () => {
          keys.set(i);
          showAt(i);
        };
        hit.addEventListener("pointerenter", enter);
        hit.addEventListener("pointerdown", enter);
        hit.addEventListener("pointerleave", hide);
      });
    },
    {
      ariaLabel,
      legend: [
        { label: positiveLabel, color: "var(--pos)" },
        { label: negativeLabel, color: "var(--neg)" },
      ],
    },
  );
}

// ------------------------------------------------------------- scatter
/** points: [{ x, y, name, sub }] on log-log axes, with the y = x "perfect" line. */
export function scatterChart(container, options) {
  const { points, height = 380, format = String, xLabel, yLabel, tipFor, ariaLabel } = options;
  mount(
    container,
    height,
    (svg, width, H, tip) => {
      const m = { top: 14, right: 16, bottom: 48, left: 58 };
      const values = points.flatMap((point) => [point.x, point.y]);
      const lo = LOG_STEPS.filter((step) => step <= Math.min(...values)).at(-1) ?? LOG_STEPS[0];
      const hi = LOG_STEPS.find((step) => step >= Math.max(...values)) ?? LOG_STEPS.at(-1);
      const x = logarithmic(lo, hi, m.left, width - m.right);
      const y = logarithmic(lo, hi, H - m.bottom, m.top);
      const ticks = LOG_STEPS.filter((step) => step >= lo && step <= hi);

      ticks.forEach((tick, i) => {
        el("line", { class: i === 0 ? "axis" : "grid", x1: m.left, x2: width - m.right, y1: y(tick), y2: y(tick) }, svg);
        el("line", { class: i === 0 ? "axis" : "grid", x1: x(tick), x2: x(tick), y1: m.top, y2: H - m.bottom }, svg);
        label(svg, m.left - 10, y(tick) + 4, format(tick), { "text-anchor": "end" });
        label(svg, x(tick), H - m.bottom + 19, format(tick), { "text-anchor": "middle" });
      });
      if (xLabel) label(svg, (m.left + width - m.right) / 2, H - 8, xLabel, { "text-anchor": "middle", class: "t-label" });
      if (yLabel) {
        const t = label(svg, 0, 0, yLabel, { "text-anchor": "middle", class: "t-label" });
        t.setAttribute("transform", `translate(14 ${(m.top + H - m.bottom) / 2}) rotate(-90)`);
      }

      el("line", { x1: x(lo), y1: y(lo), x2: x(hi), y2: y(hi), stroke: "var(--ink-2)", "stroke-width": 1.25, opacity: 0.55 }, svg);

      const layer = el("g", {}, svg);
      const placed = points.map((point) => {
        const px = x(point.x);
        const py = y(point.y);
        el("circle", { cx: px, cy: py, r: 4, fill: "var(--series-1)", "fill-opacity": 0.5, stroke: "var(--surface)", "stroke-width": 1 }, layer);
        return { px, py, point };
      });
      const focus = el("circle", { r: 6.5, fill: "var(--series-1)", stroke: "var(--surface)", "stroke-width": 2.5, visibility: "hidden" }, svg);
      const hit = el("rect", { x: m.left, y: m.top, width: Math.max(0, width - m.left - m.right), height: H - m.top - m.bottom, fill: "transparent" }, svg);

      const hide = () => {
        focus.setAttribute("visibility", "hidden");
        tip.hide();
      };
      const showAt = (index) => {
        const { px, py, point } = placed[index];
        focus.setAttribute("cx", px);
        focus.setAttribute("cy", py);
        focus.setAttribute("visibility", "visible");
        tip.show(px, py, tipFor ? tipFor(point) : { title: point.name, rows: [{ value: format(point.y) }] });
      };
      const order = placed.map((_, i) => i).sort((a, b) => placed[a].px - placed[b].px);
      const keys = keyboard(svg, placed.length, (k) => showAt(order[k]), hide);
      const nearest = (event) => {
        const box = svg.getBoundingClientRect();
        const mx = event.clientX - box.left;
        const my = event.clientY - box.top;
        let best = -1;
        let bestDistance = 24 * 24; // anything within 24px counts
        placed.forEach(({ px, py }, i) => {
          const distance = (px - mx) ** 2 + (py - my) ** 2;
          if (distance < bestDistance) {
            best = i;
            bestDistance = distance;
          }
        });
        if (best < 0) return hide();
        keys.set(order.indexOf(best));
        showAt(best);
      };
      hit.addEventListener("pointermove", nearest);
      hit.addEventListener("pointerdown", nearest);
      hit.addEventListener("pointerleave", hide);
    },
    {
      ariaLabel,
      legend: [
        { label: "One test car", color: "var(--series-1)", shape: "dot" },
        { label: "Perfect prediction (predicted = actual)", color: "var(--ink-2)", shape: "line" },
      ],
    },
  );
}
