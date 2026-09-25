"""Interactive Plotly charts for the Streamlit app (dark theme)."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

BLUE = "#4ea1ff"
MINT = "#9de9cf"
AMBER = "#f2c46d"
CORAL = "#ff8a80"
TEXT = "#c7d5e8"
GRID = "#263852"
PRICE_TICKS = dict(tickvals=[0.5, 1, 2, 5, 10, 20, 50, 100], ticktext=["0.5", "1", "2", "5", "10", "20", "50", "100"])
FUEL_COLORS = {"Petrol": BLUE, "Diesel": MINT, "CNG": AMBER, "Electric": CORAL}


def _style(fig, height=340, title=None, legend=True):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans, sans-serif", color=TEXT, size=13),
        margin=dict(l=8, r=8, t=46 if title else 12, b=8),
        height=height,
        title=dict(text=title, x=0, font=dict(size=15, family="Space Grotesk, sans-serif")) if title else None,
        showlegend=legend,
        legend=dict(orientation="h", y=-0.3, x=0, title=None),
        hoverlabel=dict(bgcolor="#0f2949", font_color="#edf5ff"),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID)
    return fig


# ---------------------------------------------------------------- what-if
def whatif_curve(xs, rows, x_title, marker_x=None, marker_y=None, title=None):
    """Predicted price (with its likely range) as one input changes."""
    xs = list(xs)
    prices = [row["price"] for row in rows]
    lows = [row["lower"] for row in rows]
    highs = [row["upper"] for row in rows]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=xs + xs[::-1],
            y=highs + lows[::-1],
            fill="toself",
            fillcolor="rgba(78,161,255,0.16)",
            line=dict(width=0),
            hoverinfo="skip",
            name="Likely range",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=prices,
            mode="lines",
            line=dict(color=BLUE, width=3),
            name="Estimated price",
            hovertemplate="%{x:,}: ₹%{y:.2f} lakh<extra></extra>",
        )
    )
    if marker_x is not None:
        fig.add_trace(
            go.Scatter(
                x=[marker_x],
                y=[marker_y],
                mode="markers",
                marker=dict(size=14, color=MINT, line=dict(color="white", width=2)),
                name="Your car",
                hovertemplate="Your car: ₹%{y:.2f} lakh<extra></extra>",
            )
        )
    fig.update_xaxes(title=x_title)
    fig.update_yaxes(title="Price (₹ lakh)", rangemode="tozero")
    return _style(fig, height=320, title=title)


def market_scatter(similar: pd.DataFrame, year: int, estimate: float, label: str, title=None):
    """Real listings of similar cars, with this estimate marked as a star."""
    fig = px.scatter(
        similar,
        x="Year",
        y="Selling_Price",
        color="Fuel_Type",
        color_discrete_map=FUEL_COLORS,
        hover_name="Name",
        hover_data={"Kms_Driven": ":,", "Year": True, "Selling_Price": ":.2f", "Fuel_Type": False},
        labels={"Selling_Price": "Price (₹ lakh)", "Kms_Driven": "Km driven"},
        opacity=0.65,
    )
    fig.update_traces(marker=dict(size=9, line=dict(width=0)))
    fig.add_trace(
        go.Scatter(
            x=[year],
            y=[estimate],
            mode="markers",
            marker=dict(size=18, symbol="star", color=AMBER, line=dict(color="white", width=1.5)),
            name=f"Your estimate ({label})",
            hovertemplate=f"Your estimate: ₹{estimate:.2f} lakh<extra></extra>",
        )
    )
    fig.update_yaxes(title="Price (₹ lakh)", rangemode="tozero")
    return _style(fig, height=320, title=title)


# --------------------------------------------------------- market insights
def price_histogram(df: pd.DataFrame, cap: float = 30.0):
    shown = df[df["Selling_Price"] <= cap]
    hidden = len(df) - len(shown)
    fig = px.histogram(shown, x="Selling_Price", nbins=60, color_discrete_sequence=[BLUE])
    fig.update_xaxes(title="Selling price (₹ lakh)")
    fig.update_yaxes(title="Cars")
    fig.update_traces(hovertemplate="₹%{x} lakh: %{y} cars<extra></extra>")
    return _style(fig, title=f"Most cars sell for under ₹10 lakh ({hidden} above ₹{cap:.0f} lakh not shown)", legend=False)


def price_vs_year(df: pd.DataFrame):
    fig = px.scatter(
        df,
        x="Year",
        y="Selling_Price",
        color="Fuel_Type",
        color_discrete_map=FUEL_COLORS,
        log_y=True,
        opacity=0.4,
        hover_name="Name",
        hover_data={"Kms_Driven": ":,", "Year": True, "Selling_Price": ":.2f", "Fuel_Type": False},
        labels={"Selling_Price": "Price (₹ lakh, log scale)"},
    )
    fig.update_traces(marker=dict(size=6))
    fig.update_yaxes(**PRICE_TICKS)
    median = df.groupby("Year")["Selling_Price"].median()
    fig.add_trace(
        go.Scatter(x=median.index, y=median.values, mode="lines", line=dict(color="white", width=2.5), name="Median")
    )
    return _style(fig, title="Newer cars are worth more (each dot is a listing)")


def brand_medians(df: pd.DataFrame, min_listings: int = 30):
    stats = df.groupby("Brand")["Selling_Price"].agg(median="median", cars="size")
    stats = stats[stats["cars"] >= min_listings].sort_values("median")
    fig = go.Figure(
        go.Bar(
            x=stats["median"],
            y=stats.index,
            orientation="h",
            marker_color=BLUE,
            customdata=stats["cars"],
            hovertemplate="%{y}: median ₹%{x:.2f} lakh (%{customdata} listings)<extra></extra>",
        )
    )
    fig.update_xaxes(title="Median selling price (₹ lakh)")
    return _style(fig, height=440, title=f"Median price by brand (brands with {min_listings}+ listings)", legend=False)


def price_by_category(df: pd.DataFrame):
    fig = px.box(
        df,
        x="Fuel_Type",
        y="Selling_Price",
        color="Transmission",
        color_discrete_sequence=[BLUE, MINT],
        log_y=True,
        points=False,
        labels={"Selling_Price": "Price (₹ lakh, log scale)", "Fuel_Type": "Fuel type"},
    )
    fig.update_yaxes(**PRICE_TICKS)
    return _style(fig, height=440, title="Diesel and automatic cars fetch more")


def depreciation_by_brand(df: pd.DataFrame, top: int = 6):
    frame = df.assign(Age=(df["Listing_Year"] - df["Year"]).clip(lower=0))
    frame = frame[frame["Age"] <= 14]
    brands = frame["Brand"].value_counts().head(top).index
    grouped = frame[frame["Brand"].isin(brands)].groupby(["Brand", "Age"])["Selling_Price"].agg(["median", "size"]).reset_index()
    grouped = grouped[grouped["size"] >= 5]
    fig = px.line(
        grouped,
        x="Age",
        y="median",
        color="Brand",
        markers=True,
        labels={"median": "Median price (₹ lakh)", "Age": "Age (years)"},
        color_discrete_sequence=[BLUE, MINT, AMBER, CORAL, "#c39bff", "#7dd3fc"],
    )
    return _style(fig, title="How quickly the big brands lose value")


# ------------------------------------------------------ model performance
def comparison_bars(comparison: list[dict]):
    rows = sorted(comparison, key=lambda row: row["cv_mae"])
    best = rows[0]["model"]
    fig = go.Figure(
        go.Bar(
            x=[row["cv_mae"] for row in rows],
            y=[row["model"] for row in rows],
            orientation="h",
            marker_color=[MINT if row["model"] == best else BLUE for row in rows],
            error_x=dict(type="data", array=[row["cv_mae_std"] for row in rows], color="#8fa3bd"),
            customdata=[[row["cv_r2"], row["cv_medape"]] for row in rows],
            hovertemplate="%{y}<br>MAE ₹%{x:.2f} lakh<br>R² %{customdata[0]:.3f}<br>typical error %{customdata[1]:.1f}%<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(title="Cross-validated error (₹ lakh), lower is better")
    return _style(fig, height=420, title="9 algorithms compared (winner in green)", legend=False)


def actual_vs_predicted(test: pd.DataFrame):
    fig = px.scatter(
        test,
        x="actual",
        y="predicted",
        log_x=True,
        log_y=True,
        opacity=0.5,
        hover_name="Name",
        hover_data={"Year": True, "actual": ":.2f", "predicted": ":.2f"},
        color_discrete_sequence=[BLUE],
        labels={"actual": "Actual price (₹ lakh)", "predicted": "Predicted price (₹ lakh)"},
    )
    top = float(max(test["actual"].max(), test["predicted"].max())) * 1.1
    fig.add_trace(go.Scatter(x=[0.15, top], y=[0.15, top], mode="lines", line=dict(color=CORAL, dash="dash"), name="Perfect prediction"))
    fig.update_xaxes(**PRICE_TICKS)
    fig.update_yaxes(**PRICE_TICKS)
    return _style(fig, height=420, title="Unseen test cars: the closer to the line, the better")


def error_by_band(bands: list[dict]):
    fig = go.Figure(
        go.Bar(
            x=[band["band"] for band in bands],
            y=[band["median_ape"] for band in bands],
            marker_color=BLUE,
            text=[f"{band['cars']} cars" for band in bands],
            textposition="outside",
            hovertemplate="%{x}: typical error %{y:.1f}%<extra></extra>",
        )
    )
    fig.update_yaxes(title="Typical error (% of price)", rangemode="tozero")
    return _style(fig, title="Accuracy by price band", legend=False)


def importance_bars(importance: list[dict]):
    rows = sorted(importance, key=lambda row: row["mean"])
    fig = go.Figure(
        go.Bar(
            x=[row["mean"] for row in rows],
            y=[row["feature"] for row in rows],
            orientation="h",
            marker_color=MINT,
            error_x=dict(type="data", array=[row["std"] for row in rows], color="#8fa3bd"),
            hovertemplate="%{y}: error rises ₹%{x:.2f} lakh if shuffled<extra></extra>",
        )
    )
    fig.update_xaxes(title="Rise in error when the input is scrambled (₹ lakh)")
    return _style(fig, height=420, title="What the model pays attention to", legend=False)
