"""AutoValue - used-car price estimator (Streamlit UI).

    streamlit run streamlit_app.py

Uses the FastAPI server when it is running (set API_URL to change the address,
default http://127.0.0.1:8000). If the server is not running the app loads the
same model directly, so it also works with a single command.
"""

import json
import os
from datetime import date

import pandas as pd
import streamlit as st

from carprice import charts
from carprice.backend import BackendError, choose_backend
from carprice.config import METADATA_PATH, TEST_PREDICTIONS_PATH
from carprice.data import FUEL_TYPES, OWNER_LABELS, PLATFORMS, TRANSMISSIONS, load_clean
from carprice.theme import CSS, format_lakh, format_rupees

st.set_page_config(
    page_title="AutoValue | Used car price estimator",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(CSS, unsafe_allow_html=True)

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
CURRENT_YEAR = date.today().year
NOT_LISTED = "Not listed / other"
NOT_SURE = "Not sure / any variant"


# ------------------------------------------------------------------ loading
@st.cache_data(show_spinner=False)
def load_metadata():
    return json.loads(METADATA_PATH.read_text()) if METADATA_PATH.exists() else None


@st.cache_data(show_spinner=False)
def load_dataset():
    try:
        return load_clean()[0]
    except FileNotFoundError:
        return None


@st.cache_data(show_spinner=False)
def load_test_predictions():
    return pd.read_csv(TEST_PREDICTIONS_PATH) if TEST_PREDICTIONS_PATH.exists() else None


@st.cache_resource(ttl=20, show_spinner=False)
def get_backend():
    # Re-checked every 20 seconds, so starting the API later switches the app over.
    return choose_backend(API_URL)


@st.cache_data(show_spinner=False)
def insight_figures():
    df = load_dataset()
    return {
        "hist": charts.price_histogram(df),
        "year": charts.price_vs_year(df),
        "brand": charts.brand_medians(df),
        "category": charts.price_by_category(df),
        "depreciation": charts.depreciation_by_brand(df),
    }


@st.cache_data(show_spinner=False)
def performance_figures():
    meta = load_metadata()
    test = load_test_predictions()
    figures = {
        "comparison": charts.comparison_bars(meta["comparison"]),
        "bands": charts.error_by_band(meta["error_by_price_band"]),
        "importance": charts.importance_bars(meta["feature_importance"]),
    }
    if test is not None:
        figures["scatter"] = charts.actual_vs_predicted(test)
    return figures


def kpi(label, value, sub=""):
    return f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div><div class="sub">{sub}</div></div>'


metadata = load_metadata()
backend = get_backend()
if metadata is None or backend is None:
    st.error("No trained model was found. Train one first, then reload this page.")
    st.code("python train.py", language="bash")
    st.stop()

data_info = metadata["data"]
test_scores = metadata["test_metrics"]
interval = metadata["interval"]
snapshot_year = metadata["reference_year"]

# --------------------------------------------------------------------- hero
st.markdown(
    f"""
    <div class="hero">
        <div class="eyebrow">AutoValue · Used-car price estimator</div>
        <h1>Know what your car is worth.</h1>
        <p>A machine-learning model that estimates the resale price of a used car in India,
        and tells you how sure it is.</p>
        <div class="badges">
            <span class="badge">✦ Learned from {data_info['clean_rows']:,} real listings</span>
            <span class="badge">◎ Typical error about {test_scores['median_ape']:.0f}%</span>
            <span class="badge">▣ {metadata['model_name']}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_estimate, tab_insights, tab_performance, tab_about = st.tabs(
    ["Estimate", "Market insights", "Model performance", "About the project"]
)

# ------------------------------------------------------------- estimate tab
with tab_estimate:
    try:
        catalog = backend.catalog()
    except BackendError as error:
        st.error(str(error))
        st.stop()
    brands = list(catalog)

    left, right = st.columns([1.05, 1], gap="large")

    with left:
        st.markdown('<div class="section-label">Your car</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### Tell us about the car")
            col_a, col_b = st.columns(2)
            brand = col_a.selectbox(
                "Brand", brands, index=brands.index("Maruti Suzuki") if "Maruti Suzuki" in brands else 0, key="brand"
            )
            model = col_b.selectbox(
                "Model",
                catalog[brand] + [NOT_LISTED],
                key="model",
                help="Most common models first. Pick 'Not listed' if yours is missing.",
            )
            variants = backend.variants(f"{brand} {model}") if model != NOT_LISTED else []
            variant = st.selectbox(
                "Variant",
                [NOT_SURE] + [item["name"] for item in variants],
                key=f"variant_{brand}_{model}",
                help="Most listed first. Leave 'Not sure' if you don't know it.",
            )
            col_c, col_d = st.columns(2)
            year = col_c.number_input("Registration year", min_value=1990, max_value=CURRENT_YEAR, value=2019, step=1, key="year")
            kms = col_d.number_input("Kilometres driven", min_value=0, max_value=1_000_000, value=50_000, step=5_000, key="kms")
            col_e, col_f = st.columns(2)
            fuel = col_e.selectbox("Fuel type", FUEL_TYPES, key="fuel")
            transmission = col_f.selectbox("Transmission", TRANSMISSIONS, key="transmission")
            col_g, col_h = st.columns(2)
            platform = col_g.selectbox("Listed on", PLATFORMS, key="platform", help="CarDekho is an open marketplace; Cars24 and Spinny are online dealers. Each has its own price level.")
            owner_label = col_h.selectbox("Ownership", list(OWNER_LABELS.values()), key="owner")

    payload = {
        "Car_Name": brand if model == NOT_LISTED else f"{brand} {model}",
        "Variant": None if variant == NOT_SURE else variant,
        "Year": int(year),
        "Kms_Driven": int(kms),
        "Fuel_Type": fuel,
        "Transmission": transmission,
        "Owner": list(OWNER_LABELS.values()).index(owner_label),
        "Platform": platform,
    }

    result, problem = None, None
    try:
        result = backend.predict(payload)
    except BackendError as error:
        problem = str(error)

    with right:
        st.markdown('<div class="section-label">Your estimate</div>', unsafe_allow_html=True)
        with st.container(border=True):
            if result is None:
                st.error(problem)
            else:
                low, price, high = result["lower"], result["price"], result["upper"]
                window_low, window_high = low * 0.8, high * 1.2
                place = lambda value: (value - window_low) / (window_high - window_low) * 100
                st.markdown(
                    f"""
                    <div class="result-card">
                        <div class="label">ESTIMATED RESALE VALUE</div>
                        <div class="price">{format_lakh(price)}</div>
                        <div class="rupees">≈ {format_rupees(price)}</div>
                        <div class="range">
                            <div class="range-track">
                                <div class="range-fill" style="left:{place(low):.1f}%; width:{place(high) - place(low):.1f}%"></div>
                                <div class="range-dot" style="left:{place(price):.1f}%"></div>
                            </div>
                            <div class="range-labels"><span>{format_lakh(low)}</span><span>likely range ({interval['confidence_percent']}%)</span><span>{format_lakh(high)}</span></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                stat_a, stat_b, stat_c = st.columns(3)
                stat_a.markdown(f'<div class="stat"><strong>{max(0, CURRENT_YEAR - year)} yrs</strong><span>age today</span></div>', unsafe_allow_html=True)
                stat_b.markdown(f'<div class="stat"><strong>{kms:,}</strong><span>km driven</span></div>', unsafe_allow_html=True)
                stat_c.markdown(f'<div class="stat"><strong>±{test_scores["median_ape"]:.0f}%</strong><span>typical error</span></div>', unsafe_allow_html=True)
                for note in result["warnings"]:
                    st.markdown(f'<div class="warn">⚠ {note}</div>', unsafe_allow_html=True)
                st.caption(
                    f"Understood as **{result['matched_car']}**. Based on 2025–{snapshot_year} listings: "
                    "a guide for negotiating, not a valuation certificate."
                )
                if st.button("Add this car to the comparison", key="add_compare"):
                    st.session_state.setdefault("compare", []).append(
                        {
                            "Car": result["matched_car"],
                            "Year": int(year),
                            "Km": f"{kms:,}",
                            "Fuel": fuel,
                            "Gearbox": transmission,
                            "Estimate (₹ lakh)": price,
                            "Likely range (₹ lakh)": f"{low:.2f} to {high:.2f}",
                        }
                    )

    if result is not None:
        st.markdown('<div class="section-label">What if...?</div>', unsafe_allow_html=True)
        what_year, what_km = st.columns(2, gap="large")
        try:
            years = list(range(max(1995, snapshot_year - 24), snapshot_year + 1))
            year_rows = backend.predict_many([{**payload, "Year": value} for value in years])
            kms_points = list(range(0, 200_001, 10_000))
            km_rows = backend.predict_many([{**payload, "Kms_Driven": value} for value in kms_points])
            with what_year:
                with st.container(border=True):
                    st.plotly_chart(
                        charts.whatif_curve(
                            years, year_rows, "Registration year", min(year, snapshot_year), price,
                            title="Price by registration year",
                        ),
                        width="stretch",
                    )
            with what_km:
                with st.container(border=True):
                    st.plotly_chart(
                        charts.whatif_curve(
                            kms_points, km_rows, "Kilometres driven", min(kms, 200_000), price,
                            title="Price by kilometres driven",
                        ),
                        width="stretch",
                    )
        except BackendError as error:
            st.error(str(error))

        dataset = load_dataset()
        if dataset is not None:
            similar = dataset[dataset["Brand"] == brand]
            scope = f"all {brand} cars"
            if model != NOT_LISTED and ((dataset["Brand"] == brand) & (dataset["Model"] == model)).sum() >= 8:
                similar = dataset[(dataset["Brand"] == brand) & (dataset["Model"] == model)]
                scope = f"{brand} {model}"
            with st.container(border=True):
                st.plotly_chart(
                    charts.market_scatter(similar, int(year), price, result["matched_car"], title=f"Your estimate against real listings of {scope}"),
                    width="stretch",
                )

    if st.session_state.get("compare"):
        st.markdown('<div class="section-label">Your comparison list</div>', unsafe_allow_html=True)
        with st.container(border=True):
            table = pd.DataFrame(st.session_state["compare"])
            st.dataframe(table, hide_index=True, width="stretch")
            if st.button("Clear comparison", key="clear_compare"):
                st.session_state["compare"] = []
                st.rerun()

# ----------------------------------------------------------- insights tab
with tab_insights:
    dataset = load_dataset()
    if dataset is None:
        st.info("The dataset file (data/car_dataset_expanded.csv) was not found, so the charts are unavailable.")
    else:
        cols = st.columns(4)
        cols[0].markdown(kpi("Listings analysed", f"{data_info['clean_rows']:,}", f"after removing {data_info['duplicate_rows_removed']:,} duplicates"), unsafe_allow_html=True)
        cols[1].markdown(kpi("Brands / models", f"{data_info['brands']} / {data_info['models']}", "found in the data"), unsafe_allow_html=True)
        cols[2].markdown(kpi("Median price", format_lakh(data_info["price_median_lakh"]), f"from ₹{data_info['price_min_lakh']:.1f} to ₹{data_info['price_max_lakh']:.0f} lakh"), unsafe_allow_html=True)
        cols[3].markdown(kpi("Registration years", f"{data_info['year_min']}–{data_info['year_max']}", "no newer cars in the data"), unsafe_allow_html=True)
        st.write("")

        figures = insight_figures()
        row1_a, row1_b = st.columns(2, gap="large")
        with row1_a, st.container(border=True):
            st.plotly_chart(figures["hist"], width="stretch")
        with row1_b, st.container(border=True):
            st.plotly_chart(figures["year"], width="stretch")
        row2_a, row2_b = st.columns(2, gap="large")
        with row2_a, st.container(border=True):
            st.plotly_chart(figures["brand"], width="stretch")
        with row2_b, st.container(border=True):
            st.plotly_chart(figures["category"], width="stretch")
        with st.container(border=True):
            st.plotly_chart(figures["depreciation"], width="stretch")

        with st.expander("How the data was cleaned"):
            st.markdown(
                f"""
                | Step | Result |
                |---|---|
                | Listings read (CarDekho, Cars24, Spinny) | {data_info['raw_rows']:,} |
                | Duplicate listings removed | {data_info['duplicate_rows_removed']:,} |
                | Other rows removed (unknown car, missing values, LPG, outliers) | {data_info['other_rows_removed']:,} |
                | Missing values left | {data_info['missing_values']} |
                | Clean rows used | {data_info['clean_rows']:,} |

                **Why remove duplicates?** The same listing appearing twice can land in both the
                training and the test set, which would let the model "remember" answers and
                make its accuracy look better than it really is.
                """
            )

# --------------------------------------------------------- performance tab
with tab_performance:
    st.markdown(
        f"How well does the model do on cars it has **never seen**? {data_info['test_rows']:,} cars "
        "were locked away before training and used only once, for this final exam."
    )
    cols = st.columns(5)
    cols[0].markdown(kpi("Typical error", f"{test_scores['median_ape']:.1f}%", "half the cars are closer than this"), unsafe_allow_html=True)
    cols[1].markdown(kpi("Average error", f"₹{test_scores['mae']:.2f} L", "mean absolute error"), unsafe_allow_html=True)
    cols[2].markdown(kpi("R² score", f"{test_scores['r2']:.2f}", "1.00 would be perfect"), unsafe_allow_html=True)
    cols[3].markdown(kpi("Within ±20%", f"{test_scores['within_20pct']:.0f}%", "of test cars"), unsafe_allow_html=True)
    cols[4].markdown(kpi("Range reliability", f"{interval['test_coverage_percent']:.0f}%", f"of prices fell in the {interval['confidence_percent']}% range"), unsafe_allow_html=True)
    st.write("")

    figures = performance_figures()
    perf_a, perf_b = st.columns(2, gap="large")
    with perf_a, st.container(border=True):
        st.plotly_chart(figures["comparison"], width="stretch")
    with perf_b, st.container(border=True):
        if "scatter" in figures:
            st.plotly_chart(figures["scatter"], width="stretch")
    perf_c, perf_d = st.columns(2, gap="large")
    with perf_c, st.container(border=True):
        st.plotly_chart(figures["importance"], width="stretch")
    with perf_d, st.container(border=True):
        st.plotly_chart(figures["bands"], width="stretch")

    st.markdown('<div class="section-label">All results</div>', unsafe_allow_html=True)
    table = pd.DataFrame(metadata["comparison"]).sort_values("cv_mae")
    table = table.assign(tuned=table["tuned"].map({True: "yes", False: ""}))[
        ["model", "cv_mae", "cv_r2", "cv_medape", "train_r2", "test_mae", "test_r2", "tuned"]
    ]
    table.columns = ["Algorithm", "CV error (₹ L)", "CV R²", "CV typical error %", "Train R²", "Test error (₹ L)", "Test R²", "Tuned"]
    st.dataframe(table.round(3), hide_index=True, width="stretch", height=(len(table) + 1) * 35 + 3)

    with st.expander("How to read these numbers"):
        st.markdown(
            """
            - **CV (cross-validation)**: the training cars are split into 5 parts; the model learns from 4
              and is graded on the 5th, five times over. This is how the algorithms are compared fairly.
            - **Test**: a separate 20% of cars kept hidden until the very end. One honest final grade.
            - **Error (MAE)**: on average, how many lakhs the estimate is away from the real price.
            - **Typical error %**: the median gap as a share of the price. Cheap and expensive cars are
              treated equally, unlike MAE which is dominated by luxury cars.
            - **R²**: how much of the price variation the model explains (0 = nothing, 1 = everything).
              It is sensitive to a few very expensive cars, so the test R² can differ from the CV R².
            - **Train R² much higher than CV R²** would mean the model memorised its training data.
            - **Likely range**: built from the size of the model's past mistakes, then checked on the test
              set. It really did capture about the promised share of prices.
            """
        )

# --------------------------------------------------------------- about tab
with tab_about:
    about_left, about_right = st.columns(2, gap="large")
    with about_left, st.container(border=True):
        st.markdown(
            f"""
            ### The problem
            Sellers and buyers of used cars in India rarely know what a fair price is. This project
            predicts the **resale price (in lakhs of rupees)** from a car's brand, model, age, kilometres,
            fuel, gearbox, variant, ownership and where it is listed. This is a *regression* problem.

            ### The data
            {data_info['raw_rows']:,} listings from CarDekho, Cars24 and Spinny, collected 2025–{snapshot_year}
            (see `DATA_SOURCES.md`). After cleaning: **{data_info['clean_rows']:,} unique cars**,
            {data_info['brands']} brands, registered {data_info['year_min']}–{data_info['year_max']}.

            ### Method
            1. **Clean**: remove duplicates, fix names, convert rupees to lakhs.
            2. **Engineer features**: age when listed, log of the kilometres, kilometres per year,
               the variant's words.
            3. **Encode**: one-hot and *target encoding* of brand, model and exact variant.
            4. **Compare** 9 algorithms with 5-fold cross-validation.
            5. **Tune** the best ones with randomised search.
            6. **Test** once on 20% of cars the model never saw.
            7. **Calibrate** a likely price range from the model's past errors.
            8. **Serve** through a FastAPI API and this Streamlit app.
            """
        )
    with about_right, st.container(border=True):
        st.markdown(
            f"""
            ### Limitations (please read)
            - **Snapshots from 2025–{snapshot_year}.** Prices move over time, so estimates slowly go out of date.
            - **Listing prices are asking prices**, not what the car finally sold for; each platform
              prices a little differently.
            - **No condition information**: accident history or servicing can change the price a lot.
            - **Few very new or luxury cars**, so their range is wider.
            - The model learns patterns in the past; it cannot see supply shocks, new taxes or fashion.

            ### Tech stack
            Python, pandas, scikit-learn, FastAPI, Pydantic, Streamlit, Plotly, pytest.

            ### Model card
            | | |
            |---|---|
            | Algorithm | {metadata['model_name']} |
            | Trained | {metadata['trained_at'][:10]} |
            | Scikit-learn | {metadata['versions']['scikit_learn']} |
            | Size | {metadata['model_size_mb']} MB |
            """
        )

# -------------------------------------------------------------------- footer
if backend.mode == "api":
    status = f'<span class="dot-ok">●</span> Connected to {backend.label()}'
else:
    status = (
        f'<span class="dot-warn">●</span> Running standalone: {backend.label()}. '
        "Start the API with <code>uvicorn main:app --reload</code> to use it."
    )
st.markdown(f'<p class="footer-note">{status}</p>', unsafe_allow_html=True)
