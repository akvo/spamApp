"""SPAM 2020 Crop Production Analyzer — Streamlit Dashboard."""

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.analyzer import analyze_location, rank_by_crop
from src.boundaries import get_cached_country_names, get_cached_districts, get_cached_states
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
    code: info["name"]
    for code, info in sorted(CROPS.items(), key=lambda x: x[1]["name"])
}


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


# --- Header ---
st.title("SPAM 2020 Crop Analyzer")

# --- Check cache ---
countries = get_cached_country_names()
if not countries:
    st.error("No boundaries cached. Run `python -m src.cli init-boundaries` first.")
    st.stop()

# --- Tabs ---
tab1, tab2 = st.tabs(["Location Analysis", "Crop Rankings"])


# --- Tab 1: Location Analysis ---
with tab1:
    # Controls at top of tab
    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])

    with c1:
        country_name = st.selectbox("Country", options=list(countries.keys()), key="loc_country")
        country_code = countries[country_name]

    with c2:
        states = get_cached_states(country_code)
        state_options = ["(All — country level)"] + states
        state_name = st.selectbox("State / Province", options=state_options, key="loc_state")

    with c3:
        district_name = None
        if state_name != "(All — country level)" and states:
            districts = get_cached_districts(country_code, state_name)
            district_options = ["(All — state level)"] + districts
            district_name = st.selectbox("District", options=district_options, key="loc_dist")
            if district_name == "(All — state level)":
                district_name = None
        else:
            st.selectbox("District", options=["—"], disabled=True, key="loc_dist_disabled")

    with c4:
        variable_label = st.selectbox(
            "Variable", options=list(VARIABLE_OPTIONS.keys()), key="loc_var"
        )
        variable = VARIABLE_OPTIONS[variable_label]

    with c5:
        st.markdown("<br>", unsafe_allow_html=True)
        analyze_btn = st.button("Analyze", type="primary", use_container_width=True)

    # Determine location and level
    if district_name:
        selected_location = district_name
        selected_level = 2
    elif state_name != "(All — country level)":
        selected_location = state_name
        selected_level = 1
    else:
        selected_location = country_name
        selected_level = 0

    # Run analysis
    if analyze_btn:
        with st.spinner(f"Analyzing {selected_location}..."):
            try:
                result = analyze_location(
                    location=selected_location,
                    admin_level=selected_level,
                    data_dir=DATA_DIR,
                    year=2020,
                    variable=variable,
                    top_n=50,
                )
                st.session_state.analysis_result = result
            except (ValueError, FileNotFoundError) as e:
                st.error(str(e))

    # Display results
    result = st.session_state.get("analysis_result")
    if result is None:
        st.info("Select a location and click **Analyze**.")
    else:
        is_yield = result.variable == "yield"
        var_info = VARIABLES.get(result.variable[0].upper(), {})
        unit = var_info.get("unit", "")

        st.markdown("---")

        # Header metrics
        level_label = {0: "Country", 1: "State", 2: "District"}[result.admin_level]
        m1, m2, m3 = st.columns(3)
        m1.metric("Location", f"{result.location_name} ({level_label})")
        m2.metric("Variable", result.variable.replace("_", " ").title())
        nonzero_count = len(result.crop_data[result.crop_data["value"] > 0])
        m3.metric("Crops with Data", nonzero_count)

        st.markdown("---")

        # Chart + Category breakdown
        chart_col, cat_col = st.columns([3, 2])

        with chart_col:
            top_n_display = min(10, len(result.crop_data))
            chart_df = result.crop_data.nlargest(top_n_display, "value").copy()

            if is_yield:
                st.subheader(f"Top {top_n_display} Crops — Avg Yield ({unit})")
            else:
                var_title = result.variable.replace("_", " ").title()
                st.subheader(f"Top {top_n_display} Crops — {var_title} ({unit})")

            fmt = ",.2f" if is_yield else ",.0f"
            chart = (
                alt.Chart(chart_df)
                .mark_bar(cornerRadiusEnd=4, color="#2e8b2e")
                .encode(
                    x=alt.X("value:Q", title=unit),
                    y=alt.Y("crop_name:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("crop_name:N", title="Crop"),
                        alt.Tooltip("value:Q", title=unit, format=fmt),
                        alt.Tooltip("category:N", title="Category"),
                    ],
                )
                .properties(height=max(300, top_n_display * 35))
            )
            st.altair_chart(chart, use_container_width=True)

        with cat_col:
            st.subheader("Category Breakdown")
            cat_df = (
                result.crop_data.groupby("category")["value"]
                .sum()
                .reset_index()
                .sort_values("value", ascending=False)
            )
            if not is_yield:
                total_val = cat_df["value"].sum()
                cat_df["pct"] = (cat_df["value"] / total_val * 100).round(1)
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
                    .properties(height=max(200, len(cat_df) * 28))
                )
                st.altair_chart(cat_chart, use_container_width=True)
            else:
                st.caption("Category breakdown not applicable for yield.")

        # Full data table
        st.markdown("---")
        st.subheader("All Crops Data")

        display_df = result.crop_data.copy()
        display_df = display_df.sort_values("value", ascending=False)
        display_df = display_df.reset_index(drop=True)
        display_df.index += 1

        if not is_yield:
            total = result.crop_data["value"].sum()
            if total > 0:
                display_df["% of Total"] = (
                    display_df["value"] / total * 100
                ).round(1)

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
        csv_data = (
            display_df[show_cols].rename(columns=rename_map).to_csv(index=False)
        )
        dl1.download_button(
            "Download CSV",
            csv_data,
            f"{result.location_name}_crops.csv",
            "text/csv",
        )
        json_data = json.dumps(
            {
                "location": result.location_name,
                "variable": result.variable,
                "crops": display_df[["crop_name", "category", "value"]].to_dict(
                    orient="records"
                ),
            },
            indent=2,
        )
        dl2.download_button(
            "Download JSON",
            json_data,
            f"{result.location_name}_crops.json",
            "application/json",
        )


# --- Tab 2: Crop Rankings ---
with tab2:
    # Controls at top of tab
    r1, r2, r3, r4 = st.columns([2, 2, 1, 1])

    with r1:
        crop_name = st.selectbox("Crop", options=list(CROP_NAMES.values()), key="rank_crop")
        crop_code = next(code for code, name in CROP_NAMES.items() if name == crop_name)

    with r2:
        rank_level = st.selectbox(
            "Region Level",
            options=[0, 1, 2],
            format_func=lambda x: {0: "Countries", 1: "States", 2: "Districts"}[x],
            key="rank_level",
        )

    with r3:
        top_n = st.number_input("Top N", min_value=1, max_value=50, value=10, key="rank_n")

    with r4:
        st.markdown("<br>", unsafe_allow_html=True)
        rank_btn = st.button("Show Rankings", type="primary", use_container_width=True)

    # Run ranking
    if rank_btn:
        try:
            df = rank_by_crop(
                crop_code, admin_level=rank_level, index_dir=INDEX_DIR, top_n=top_n
            )
            st.session_state.ranking_result = df
            st.session_state.ranking_crop = crop_name
        except FileNotFoundError as e:
            st.error(str(e))

    # Display results
    ranking_df = st.session_state.get("ranking_result")
    ranking_crop = st.session_state.get("ranking_crop")

    if ranking_df is None:
        st.info("Select a crop and click **Show Rankings**.")

        # Show what's available in the index
        for lvl in [0, 1, 2]:
            info = get_index_info(lvl)
            if info["countries"]:
                lvl_name = {0: "Countries", 1: "States", 2: "Districts"}[lvl]
                crop_list = [CROPS[c]["name"] for c in info["crops"] if c in CROPS]
                st.caption(
                    f"**{lvl_name}:** "
                    f"{', '.join(info['countries'])} — "
                    f"Crops: {', '.join(crop_list)}"
                )
    elif ranking_df.empty:
        st.warning(
            "No data found. The index may not contain this crop/level combination."
        )
    else:
        st.markdown("---")

        # Header
        h1, h2, h3 = st.columns(3)
        h1.metric("Crop", ranking_crop)
        lvl_name = {0: "Countries", 1: "States", 2: "Districts"}[rank_level]
        h2.metric("Level", lvl_name)
        h3.metric("Regions", len(ranking_df))

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
                    alt.Tooltip(
                        "production_mt:Q", title="Production (mt)", format=",.0f"
                    ),
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

        csv_data = show_df.to_csv(index_label="Rank")
        st.download_button(
            "Download CSV",
            csv_data,
            f"{ranking_crop}_rankings.csv",
            "text/csv",
        )
