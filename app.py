"""SPAM 2020 Crop Production Analyzer — Streamlit Dashboard."""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.analyzer import AnalysisResult, analyze_location, rank_by_crop
from src.crops import CROPS, VARIABLES

# --- Page config ---
st.set_page_config(
    page_title="SPAM 2020 Crop Analyzer",
    page_icon="\U0001f33e",
    layout="wide",
)

# --- Constants ---
DATA_DIR = Path("data")
INDEX_DIR = DATA_DIR / "index"
VARIABLE_OPTIONS = {
    "Production (mt)": "production",
    "Harvested Area (ha)": "harvested_area",
    "Physical Area (ha)": "physical_area",
    "Yield (t/ha)": "yield",
}
CROP_NAMES = {
    code: info["name"] for code, info in sorted(CROPS.items(), key=lambda x: x[1]["name"])
}


# --- Helper: get indexed crops/countries ---
@st.cache_data(ttl=60)
def get_index_info(level: int) -> dict:
    """Return available countries and crops from the index."""
    path = INDEX_DIR / f"level_{level}.parquet"
    if not path.exists():
        return {"countries": [], "crops": [], "df": pd.DataFrame()}
    df = pd.read_parquet(path)
    return {
        "countries": sorted(df["country_name"].unique()),
        "crops": sorted(df["crop_code"].unique()),
        "df": df,
    }


# --- Sidebar ---
with st.sidebar:
    st.markdown("## SPAM 2020")
    st.caption("Crop Production Analyzer")

    st.markdown("---")
    st.markdown("#### Location Analysis")

    location = st.text_input("Location", value="India", help="Country, state, or district name")

    admin_level = st.selectbox(
        "Admin Level",
        options=[0, 1, 2],
        format_func=lambda x: {0: "Country", 1: "State / Province", 2: "District"}[x],
    )

    variable_label = st.selectbox("Variable", options=list(VARIABLE_OPTIONS.keys()))
    variable = VARIABLE_OPTIONS[variable_label]

    analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

    st.markdown("---")
    st.markdown("#### Crop Rankings")

    crop_name = st.selectbox("Crop", options=list(CROP_NAMES.values()))
    # Reverse lookup code from name
    crop_code = next(code for code, name in CROP_NAMES.items() if name == crop_name)

    rank_level = st.selectbox(
        "Ranking Level",
        options=[0, 1, 2],
        format_func=lambda x: {0: "Countries", 1: "States", 2: "Districts"}[x],
        key="rank_level",
    )

    top_n = st.number_input("Top N", min_value=1, max_value=50, value=10)

    rank_btn = st.button("Show Rankings", use_container_width=True)


# --- Session state ---
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "ranking_result" not in st.session_state:
    st.session_state.ranking_result = None
if "ranking_crop" not in st.session_state:
    st.session_state.ranking_crop = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "Location Analysis"


# --- Run analysis ---
if analyze_btn:
    with st.spinner(f"Analyzing {location}..."):
        try:
            result = analyze_location(
                location=location,
                admin_level=admin_level,
                data_dir=DATA_DIR,
                year=2020,
                variable=variable,
                top_n=50,
            )
            st.session_state.analysis_result = result
            st.session_state.active_tab = "Location Analysis"
        except (ValueError, FileNotFoundError) as e:
            st.error(str(e))

if rank_btn:
    try:
        df = rank_by_crop(crop_code, admin_level=rank_level, index_dir=INDEX_DIR, top_n=top_n)
        st.session_state.ranking_result = df
        st.session_state.ranking_crop = crop_name
        st.session_state.active_tab = "Crop Rankings"
    except FileNotFoundError as e:
        st.error(str(e))


# --- Breadcrumb ---
def show_breadcrumb(result: AnalysisResult):
    parts = [f"**{result.location_name}**"]
    st.caption(" / ".join(parts))


# --- Tabs ---
tab1, tab2 = st.tabs(["Location Analysis", "Crop Rankings"])


# --- Tab 1: Location Analysis ---
with tab1:
    result = st.session_state.analysis_result
    if result is None:
        st.info("Enter a location in the sidebar and click **Analyze** to see crop statistics.")
    else:
        is_yield = result.variable == "yield"
        var_info = VARIABLES.get(result.variable[0].upper(), {})
        unit = var_info.get("unit", "")

        # Header metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Location", result.location_name)
        col2.metric("Variable", result.variable.replace("_", " ").title())
        if is_yield:
            col3.metric("Weighted Avg", f"{result.total:,.2f} {unit}")
        else:
            col3.metric("Total", f"{result.total:,.0f}")
        col4.metric("Crops with Data", len(result.crop_data[result.crop_data["value"] > 0]))

        st.markdown("---")

        # Chart + Summary row
        chart_col, summary_col = st.columns([3, 2])

        with chart_col:
            top_n_display = min(10, len(result.crop_data))
            chart_df = result.crop_data.nlargest(top_n_display, "value").copy()

            if is_yield:
                st.subheader(f"Top {top_n_display} Crops — Avg Yield ({unit})")
            else:
                var_title = result.variable.replace("_", " ").title()
                st.subheader(f"Top {top_n_display} Crops — {var_title} ({unit})")

            chart = (
                alt.Chart(chart_df)
                .mark_bar(cornerRadiusEnd=4, color="#2e8b2e")
                .encode(
                    x=alt.X("value:Q", title=unit),
                    y=alt.Y("crop_name:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("crop_name:N", title="Crop"),
                        alt.Tooltip(
                            "value:Q", title=unit, format=",.0f" if not is_yield else ",.2f"
                        ),
                        alt.Tooltip("category:N", title="Category"),
                    ],
                )
                .properties(height=max(300, top_n_display * 35))
            )
            st.altair_chart(chart, use_container_width=True)

        with summary_col:
            st.subheader("Summary")
            nonzero = len(result.crop_data[result.crop_data["value"] > 0])
            top_crop_name = result.top_crops[0][0] if result.top_crops else "—"
            top_crop_val = result.top_crops[0][1] if result.top_crops else 0

            m1, m2 = st.columns(2)
            if is_yield:
                m1.metric("Weighted Avg", f"{result.total:,.2f}")
            else:
                m1.metric("Total", f"{result.total:,.0f}")
            m2.metric("Crops", str(nonzero))

            m3, m4 = st.columns(2)
            m3.metric("Top Crop", top_crop_name)
            if not is_yield and result.total > 0:
                m4.metric("Top Share", f"{top_crop_val / result.total * 100:.1f}%")
            else:
                m4.metric(
                    "Top Value", f"{top_crop_val:,.2f}" if is_yield else f"{top_crop_val:,.0f}"
                )

            # Category breakdown
            st.markdown("**Category Breakdown**")
            cat_df = (
                result.crop_data.groupby("category")["value"]
                .sum()
                .reset_index()
                .sort_values("value", ascending=False)
            )
            if not is_yield:
                cat_df["pct"] = (cat_df["value"] / cat_df["value"].sum() * 100).round(1)
                cat_chart = (
                    alt.Chart(cat_df)
                    .mark_bar(cornerRadiusEnd=4)
                    .encode(
                        x=alt.X("pct:Q", title="% of Total"),
                        y=alt.Y("category:N", sort="-x", title=""),
                        color=alt.Color(
                            "category:N",
                            legend=None,
                            scale=alt.Scale(scheme="tableau10"),
                        ),
                        tooltip=[
                            alt.Tooltip("category:N", title="Category"),
                            alt.Tooltip("pct:Q", title="%", format=".1f"),
                        ],
                    )
                    .properties(height=max(150, len(cat_df) * 28))
                )
                st.altair_chart(cat_chart, use_container_width=True)

        # Full data table
        st.markdown("---")
        st.subheader("All Crops Data")

        display_df = result.crop_data.copy()
        display_df = display_df.sort_values("value", ascending=False).reset_index(drop=True)
        display_df.index += 1

        if not is_yield and result.total > 0:
            display_df["% of Total"] = (display_df["value"] / result.total * 100).round(1)

        # Clean up column names for display
        show_cols = ["crop_name", "category", "value"]
        if "% of Total" in display_df.columns:
            show_cols.append("% of Total")

        rename_map = {"crop_name": "Crop", "category": "Category", "value": unit}
        st.dataframe(
            display_df[show_cols].rename(columns=rename_map),
            use_container_width=True,
            height=400,
        )

        # Downloads
        dl1, dl2, _ = st.columns([1, 1, 4])
        csv_data = display_df[show_cols].rename(columns=rename_map).to_csv(index=False)
        dl1.download_button(
            "Download CSV", csv_data, f"{result.location_name}_crops.csv", "text/csv"
        )

        import json

        json_data = json.dumps(
            {
                "location": result.location_name,
                "variable": result.variable,
                "total": result.total,
                "crops": display_df[["crop_name", "category", "value"]].to_dict(orient="records"),
            },
            indent=2,
        )
        dl2.download_button(
            "Download JSON", json_data, f"{result.location_name}_crops.json", "application/json"
        )


# --- Tab 2: Crop Rankings ---
with tab2:
    ranking_df = st.session_state.ranking_result
    ranking_crop = st.session_state.ranking_crop

    if ranking_df is None:
        st.info(
            "Select a crop in the sidebar and click **Show Rankings** to see top producing regions."
        )

        # Show what's available in the index
        for lvl in [0, 1, 2]:
            info = get_index_info(lvl)
            if info["countries"]:
                level_name = {0: "Countries", 1: "States", 2: "Districts"}[lvl]
                crop_names = [CROPS[c]["name"] for c in info["crops"] if c in CROPS]
                st.caption(
                    f"**Level {lvl} ({level_name}):** "
                    f"{', '.join(info['countries'])} — "
                    f"Crops: {', '.join(crop_names)}"
                )
    else:
        if ranking_df.empty:
            st.warning("No data found. The index may not contain this crop/level combination.")
        else:
            # Header
            col1, col2, col3 = st.columns(3)
            col1.metric("Crop", ranking_crop)
            level_name = {0: "Countries", 1: "States", 2: "Districts"}[rank_level]
            col2.metric("Level", level_name)
            col3.metric("Regions", len(ranking_df))

            st.markdown("---")

            # Bar chart
            st.subheader(f"Top {len(ranking_df)} Regions — {ranking_crop} Production")

            chart = (
                alt.Chart(ranking_df)
                .mark_bar(cornerRadiusEnd=4, color="#2e8b2e")
                .encode(
                    x=alt.X("production_mt:Q", title="Production (mt)"),
                    y=alt.Y("admin_name:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("admin_name:N", title="Region"),
                        alt.Tooltip("country_name:N", title="Country"),
                        alt.Tooltip("production_mt:Q", title="Production (mt)", format=",.0f"),
                    ],
                )
                .properties(height=max(300, len(ranking_df) * 35))
            )
            st.altair_chart(chart, use_container_width=True)

            # Table
            st.subheader("Rankings Data")
            show_df = ranking_df[["admin_name", "country_name", "production_mt"]].copy()
            show_df.index = range(1, len(show_df) + 1)
            show_df.columns = ["Region", "Country", "Production (mt)"]
            st.dataframe(show_df, use_container_width=True)

            # Download
            csv_data = show_df.to_csv(index_label="Rank")
            st.download_button(
                "Download CSV",
                csv_data,
                f"{ranking_crop}_rankings.csv",
                "text/csv",
            )
