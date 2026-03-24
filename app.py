"""SPAM 2020 Crop Production Analyzer — Streamlit Dashboard."""

import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from src.analyzer import analyze_location, rank_by_crop
from src.boundaries import (
    _read_cache,
    get_cached_country_names,
    get_cached_districts,
    get_cached_states,
)
from src.crops import CROPS, VARIABLES

# --- Cached wrappers for performance ---
# Bump _CACHE_VERSION when the analysis output format changes to invalidate stale cache
_CACHE_VERSION = 2


@st.cache_data(show_spinner=False)
def _cached_analyze(location, admin_level, variable, year=2020, _v=_CACHE_VERSION):
    """Cache analysis results — same inputs return instantly."""
    return analyze_location(
        location=location,
        admin_level=admin_level,
        data_dir=DATA_DIR,
        year=year,
        variable=variable,
        top_n=50,
    )


@st.cache_data(show_spinner=False)
def _cached_rank(crop_code, admin_level, top_n, country_code=None, variable="P"):
    """Cache ranking results."""
    return rank_by_crop(
        crop_code,
        admin_level=admin_level,
        index_dir=INDEX_DIR,
        top_n=top_n,
        country_code=country_code,
        variable=variable,
    )


@st.cache_resource
def _cached_countries():
    return get_cached_country_names()


@st.cache_resource
def _cached_states(country_code):
    return get_cached_states(country_code)


@st.cache_resource
def _cached_districts(country_code, state_name):
    return get_cached_districts(country_code, state_name)


@st.cache_resource
def _cached_boundary_gdf(country_code, level):
    return _read_cache(country_code, level)

# --- Page config ---
st.set_page_config(
    page_title="SPAM 2020 Crop Analyzer",
    page_icon="\U0001f33e",
    layout="wide",
)

# --- Custom theme CSS ---
st.markdown(
    """
    <style>
    /* Sidebar: dark green background */
    [data-testid="stSidebar"] {
        background-color: #1a3a1a;
    }
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown span,
    [data-testid="stSidebar"] label {
        color: #e8f0e8 !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: #2a5a2a;
    }

    /* Primary button: green */
    .stButton > button[kind="primary"] {
        background-color: #2e8b2e;
        border-color: #2e8b2e;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #3aa53a;
        border-color: #3aa53a;
    }

    /* Tab underline: green */
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: #2e8b2e;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #1a6a1a;
    }

    /* Metric cards: light green background */
    [data-testid="stMetric"] {
        background: #f0f8f0;
        padding: 12px 16px;
        border-radius: 8px;
    }
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #1a6a1a;
    }

    /* Page background */
    .stApp {
        background-color: #f8faf8;
    }

    /* Title color */
    .stApp h1 {
        color: #1a3a1a;
    }
    </style>
    """,
    unsafe_allow_html=True,
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


# --- Check cache ---
countries = _cached_countries()
if not countries:
    st.error(
        "No boundaries cached. Run `python -m src.cli init-boundaries` first."
    )
    st.stop()


# --- Sidebar: shared location selector ---
with st.sidebar:
    st.markdown("## SPAM 2020")
    st.caption("Crop Production Analyzer")
    st.markdown("---")

    country_name = st.selectbox("Country", options=list(countries.keys()))
    country_code = countries[country_name]

    states = _cached_states(country_code)
    state_options = ["(All)"] + states
    state_name = st.selectbox("State / Province", options=state_options)

    district_name = None
    if state_name != "(All)" and states:
        districts = _cached_districts(country_code, state_name)
        district_options = ["(All)"] + districts
        district_name = st.selectbox("District", options=district_options)
        if district_name == "(All)":
            district_name = None

    st.markdown("---")
    variable_label = st.selectbox(
        "Variable", options=list(VARIABLE_OPTIONS.keys())
    )
    variable = VARIABLE_OPTIONS[variable_label]

# Derive location, level, and whether we're at the deepest level
if district_name:
    selected_location = district_name
    selected_level = 2
    is_deepest = True
elif state_name != "(All)":
    selected_location = state_name
    selected_level = 1
    is_deepest = False
else:
    selected_location = country_name
    selected_level = 0
    is_deepest = False

# The ranking level is always one below the selected level (child breakdown)
# Unless we're at the deepest level — then we rank among siblings
rank_level = min(selected_level + 1, 2) if not is_deepest else selected_level

# Map variable name to code for index queries
_VAR_NAME_TO_CODE = {
    "production": "P",
    "harvested_area": "H",
    "physical_area": "A",
    "yield": "Y",
}
var_code = _VAR_NAME_TO_CODE.get(variable, "P")


# --- Header ---
st.title("SPAM 2020 Crop Analyzer")

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(
    ["Location Analysis", "Crop Rankings", "Global Comparisons"]
)


# --- Tab 1: Location Analysis ---
with tab1:
    # Variable + Analyze button row
    c1, c2 = st.columns([4, 1])
    with c2:
        analyze_btn = st.button(
            "Analyze", type="primary", use_container_width=True
        )

    if analyze_btn:
        with st.spinner(f"Analyzing {selected_location}..."):
            try:
                result = _cached_analyze(
                    selected_location, selected_level, variable
                )
                st.session_state.analysis_result = result
            except (ValueError, FileNotFoundError) as e:
                st.error(str(e))

    result = st.session_state.get("analysis_result")
    if result is None:
        st.info("Select a location in the sidebar and click **Analyze**.")
    else:
        is_yield = result.variable == "yield"
        var_info = VARIABLES.get(result.variable[0].upper(), {})
        unit = var_info.get("unit", "")

        # For charts: scale large values to millions
        if result.variable in ("production", "harvested_area", "physical_area"):
            chart_divisor = 1_000_000
            chart_unit = "M mt" if result.variable == "production" else "M ha"
        else:
            chart_divisor = 1
            chart_unit = unit

        # Split data by tech level
        all_data = result.crop_data
        a_data = all_data[all_data["tech_level"] == "A"]
        ir_data = all_data[all_data["tech_level"].isin(["I", "R"])]
        has_ir = len(ir_data) > 0 and not is_yield

        # Header metrics
        level_label = {0: "Country", 1: "State", 2: "District"}[
            result.admin_level
        ]
        m1, m2, m3 = st.columns(3)
        m1.metric("Location", f"{result.location_name} ({level_label})")
        m2.metric("Variable", result.variable.replace("_", " ").title())
        nonzero_count = len(a_data[a_data["value"] > 0])
        m3.metric("Crops with Data", nonzero_count)

        st.markdown("---")

        # Chart + Category breakdown
        chart_col, cat_col = st.columns([3, 2])

        with chart_col:
            top_n_display = min(10, len(a_data))
            top_crops_list = (
                a_data.nlargest(top_n_display, "value")["crop_name"].tolist()
            )

            if is_yield:
                st.subheader(f"Top {top_n_display} Crops — Avg Yield ({unit})")
            else:
                var_title = result.variable.replace("_", " ").title()
                st.subheader(
                    f"Top {top_n_display} Crops — {var_title} ({chart_unit})"
                )

            chart_fmt = ",.2f" if is_yield else ",.1f"

            if has_ir:
                # Stacked bar: Irrigated + Rainfed
                stack_df = ir_data[
                    ir_data["crop_name"].isin(top_crops_list)
                ].copy()
                stack_df["tech_label"] = stack_df["tech_level"].map(
                    {"I": "Irrigated", "R": "Rainfed"}
                )
                stack_df["chart_value"] = stack_df["value"] / chart_divisor
                chart = (
                    alt.Chart(stack_df)
                    .mark_bar(cornerRadiusEnd=2)
                    .encode(
                        x=alt.X(
                            "chart_value:Q",
                            title=chart_unit,
                            stack="zero",
                        ),
                        y=alt.Y(
                            "crop_name:N",
                            sort=top_crops_list,
                            title="",
                        ),
                        color=alt.Color(
                            "tech_label:N",
                            title="System",
                            scale=alt.Scale(
                                domain=["Irrigated", "Rainfed"],
                                range=["#2171b5", "#2e8b2e"],
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("crop_name:N", title="Crop"),
                            alt.Tooltip(
                                "tech_label:N", title="System"
                            ),
                            alt.Tooltip(
                                "chart_value:Q",
                                title=chart_unit,
                                format=chart_fmt,
                            ),
                        ],
                    )
                    .properties(
                        height=max(300, top_n_display * 35)
                    )
                )
            else:
                # Simple bar (yield or no I/R data)
                chart_df = a_data.nlargest(
                    top_n_display, "value"
                ).copy()
                chart_df["chart_value"] = chart_df["value"] / chart_divisor
                chart = (
                    alt.Chart(chart_df)
                    .mark_bar(cornerRadiusEnd=4, color="#2e8b2e")
                    .encode(
                        x=alt.X("chart_value:Q", title=chart_unit),
                        y=alt.Y("crop_name:N", sort="-x", title=""),
                        tooltip=[
                            alt.Tooltip("crop_name:N", title="Crop"),
                            alt.Tooltip(
                                "chart_value:Q",
                                title=chart_unit,
                                format=chart_fmt,
                            ),
                            alt.Tooltip("category:N", title="Category"),
                        ],
                    )
                    .properties(
                        height=max(300, top_n_display * 35)
                    )
                )
            st.altair_chart(chart, use_container_width=True)

        with cat_col:
            st.subheader("Category Breakdown")
            cat_df = (
                a_data.groupby("category")["value"]
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
                st.caption(
                    "Category breakdown not applicable for yield."
                )

        # Full data table
        st.markdown("---")
        st.subheader("All Crops Data")

        # Build table from "A" rows with optional I/R columns
        display_df = a_data[a_data["value"] > 0].copy()
        display_df = display_df.sort_values("value", ascending=False)
        display_df = display_df.reset_index(drop=True)
        display_df.index += 1

        if has_ir:
            # Pivot I/R data and merge
            ir_pivot = ir_data.pivot_table(
                index="crop_name",
                columns="tech_level",
                values="value",
                aggfunc="sum",
            ).reset_index()
            ir_pivot.columns.name = None
            if "I" in ir_pivot.columns:
                ir_pivot = ir_pivot.rename(columns={"I": "irrigated"})
            if "R" in ir_pivot.columns:
                ir_pivot = ir_pivot.rename(columns={"R": "rainfed"})
            display_df = display_df.merge(
                ir_pivot, on="crop_name", how="left"
            )
            for col in ["irrigated", "rainfed"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].fillna(0)

        if is_yield:
            display_df["value"] = display_df["value"].round(2)
        else:
            display_df["value"] = display_df["value"].round(0).astype(int)
            for col in ["irrigated", "rainfed"]:
                if col in display_df.columns:
                    display_df[col] = display_df[col].round(0).astype(int)

        if not is_yield:
            total = display_df["value"].sum()
            if total > 0:
                display_df["% of Total"] = (
                    display_df["value"] / total * 100
                ).round(1)

        # Format numbers
        def _fmt_val(v, is_y=is_yield):
            return f"{v:,.2f}" if is_y else f"{v:,.0f}"

        display_df["value_fmt"] = display_df["value"].apply(_fmt_val)
        for col in ["irrigated", "rainfed"]:
            if col in display_df.columns:
                display_df[f"{col}_fmt"] = display_df[col].apply(_fmt_val)

        fmt_cols = ["crop_name", "category", "value_fmt"]
        if has_ir:
            if "irrigated_fmt" in display_df.columns:
                fmt_cols.append("irrigated_fmt")
            if "rainfed_fmt" in display_df.columns:
                fmt_cols.append("rainfed_fmt")
        if "% of Total" in display_df.columns:
            fmt_cols.append("% of Total")

        rename_map = {
            "crop_name": "Crop",
            "category": "Category",
            "value_fmt": f"Total ({unit})",
            "irrigated_fmt": f"Irrigated ({unit})",
            "rainfed_fmt": f"Rainfed ({unit})",
        }

        st.dataframe(
            display_df[fmt_cols].rename(columns=rename_map),
            use_container_width=True,
            height=400,
        )

        # Downloads
        dl1, dl2, _ = st.columns([1, 1, 4])
        csv_cols = ["crop_name", "category", "value"]
        for col in ["irrigated", "rainfed"]:
            if col in display_df.columns:
                csv_cols.append(col)
        if "% of Total" in display_df.columns:
            csv_cols.append("% of Total")
        csv_rename = {
            "crop_name": "Crop",
            "category": "Category",
            "value": f"Total ({unit})",
            "irrigated": f"Irrigated ({unit})",
            "rainfed": f"Rainfed ({unit})",
        }
        csv_data = (
            display_df[csv_cols]
            .rename(columns=csv_rename)
            .to_csv(index=False)
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
                "crops": display_df[
                    ["crop_name", "category", "value"]
                ].to_dict(orient="records"),
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
    # Controls: just crop selector + top N + button
    r1, r2, r3 = st.columns([3, 1, 1])

    with r1:
        crop_name = st.selectbox(
            "Crop", options=list(CROP_NAMES.values()), key="rank_crop"
        )
        crop_code = next(
            code for code, name in CROP_NAMES.items() if name == crop_name
        )

    with r2:
        top_n = st.number_input(
            "Top N", min_value=1, max_value=50, value=10, key="rank_n"
        )

    with r3:
        st.markdown("<br>", unsafe_allow_html=True)
        rank_btn = st.button(
            "Show Rankings", type="primary", use_container_width=True
        )

    # Determine what to show based on sidebar selection
    if is_deepest:
        # At district level: show comparison among sibling districts
        level_desc = "Districts"
        rank_title = (
            f"{crop_name} — {selected_location} vs other districts"
        )
    else:
        child_name = {0: "States", 1: "Districts"}[selected_level]
        level_desc = child_name
        rank_title = f"{crop_name} — Top {child_name} in {selected_location}"

    if rank_btn:
        try:
            df = _cached_rank(
                crop_code, rank_level, top_n, country_code, var_code
            )
            # If a state is selected, filter districts to that state
            # by looking up which districts belong to it from GADM cache
            if selected_level == 1 and rank_level == 2 and not df.empty:
                boundary_gdf = _cached_boundary_gdf(country_code, 2)
                if boundary_gdf is not None and "NAME_1" in boundary_gdf.columns:
                    state_districts = set(
                        boundary_gdf[boundary_gdf["NAME_1"] == state_name][
                            "NAME_2"
                        ]
                    )
                    df = df[df["admin_name"].isin(state_districts)]
                    df = df.reset_index(drop=True)
            st.session_state.ranking_result = df
            st.session_state.ranking_crop = crop_name
            st.session_state.ranking_title = rank_title
            st.session_state.ranking_highlight = (
                selected_location if is_deepest else None
            )
        except FileNotFoundError as e:
            st.error(str(e))

    # Display results
    ranking_df = st.session_state.get("ranking_result")
    ranking_crop_name = st.session_state.get("ranking_crop")
    ranking_title = st.session_state.get("ranking_title", "")
    highlight = st.session_state.get("ranking_highlight")

    if ranking_df is None:
        lvl_desc = {0: "states", 1: "districts"}.get(
            selected_level, "regions"
        )
        if is_deepest:
            st.info(
                f"Select a crop and click **Show Rankings** to see how "
                f"**{selected_location}** compares to other districts."
            )
        else:
            st.info(
                f"Select a crop and click **Show Rankings** to see "
                f"top {lvl_desc} in **{selected_location}**."
            )

        # Show index availability
        for lvl in [0, 1, 2]:
            info = get_index_info(lvl)
            if info["countries"]:
                lvl_name = {0: "Countries", 1: "States", 2: "Districts"}[lvl]
                crop_list = [
                    CROPS[c]["name"] for c in info["crops"] if c in CROPS
                ]
                st.caption(
                    f"**{lvl_name}:** "
                    f"{', '.join(info['countries'])} — "
                    f"Crops: {', '.join(crop_list)}"
                )
    elif ranking_df.empty:
        st.warning(
            "No data found. The index may not contain "
            "this crop/level combination."
        )
    else:
        st.markdown("---")

        # Ensure rank_value column exists (backward compat with cached data)
        if "rank_value" not in ranking_df.columns:
            ranking_df = ranking_df.copy()
            if "production_mt" in ranking_df.columns:
                ranking_df["rank_value"] = ranking_df["production_mt"]
            elif "value" in ranking_df.columns:
                ranking_df["rank_value"] = ranking_df["value"]

        # Determine unit label for the selected variable
        var_info = VARIABLES.get(var_code, {})
        rank_unit = var_info.get("unit", "mt")
        rank_var_name = var_info.get("name", "Production")
        is_rank_yield = var_code == "Y"
        rank_fmt = ",.2f" if is_rank_yield else ",.0f"
        rank_col_label = f"{rank_var_name} ({rank_unit})"

        # Header
        h1, h2, h3 = st.columns(3)
        h1.metric("Crop", ranking_crop_name)
        h2.metric("Level", level_desc)
        h3.metric("Regions", len(ranking_df))

        st.markdown("---")

        # Bar chart — highlight selected region if at deepest level
        st.subheader(ranking_title)

        if highlight:
            ranking_df = ranking_df.copy()
            ranking_df["_highlight"] = ranking_df["admin_name"].apply(
                lambda x: "Selected" if x == highlight else "Other"
            )
            chart = (
                alt.Chart(ranking_df)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("rank_value:Q", title=rank_col_label),
                    y=alt.Y("admin_name:N", sort="-x", title=""),
                    color=alt.Color(
                        "_highlight:N",
                        scale=alt.Scale(
                            domain=["Selected", "Other"],
                            range=["#d4380d", "#2e8b2e"],
                        ),
                        legend=None,
                    ),
                    tooltip=[
                        alt.Tooltip("admin_name:N", title="Region"),
                        alt.Tooltip("country_name:N", title="Country"),
                        alt.Tooltip(
                            "rank_value:Q",
                            title=rank_col_label,
                            format=rank_fmt,
                        ),
                    ],
                )
                .properties(height=max(300, len(ranking_df) * 35))
            )
        else:
            chart = (
                alt.Chart(ranking_df)
                .mark_bar(cornerRadiusEnd=4, color="#2e8b2e")
                .encode(
                    x=alt.X("rank_value:Q", title=rank_col_label),
                    y=alt.Y("admin_name:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("admin_name:N", title="Region"),
                        alt.Tooltip("country_name:N", title="Country"),
                        alt.Tooltip(
                            "rank_value:Q",
                            title=rank_col_label,
                            format=rank_fmt,
                        ),
                    ],
                )
                .properties(height=max(300, len(ranking_df) * 35))
            )
        st.altair_chart(chart, use_container_width=True)

        # Choropleth map
        st.subheader("Map")
        try:
            import branca.colormap as cm
            import folium
            from streamlit_folium import st_folium

            name_col = f"NAME_{rank_level}"
            boundary_gdf = _cached_boundary_gdf(country_code, rank_level)

            if boundary_gdf is not None and name_col in boundary_gdf.columns:
                # Filter boundaries to children of selected region
                if rank_level == 1:
                    # Showing states — use all states in country
                    pass
                elif rank_level == 2 and state_name != "(All)":
                    # Showing districts — filter to selected state
                    boundary_gdf = boundary_gdf[
                        boundary_gdf["NAME_1"] == state_name
                    ].copy()

                # Get ALL data for these regions (not just top N)
                try:
                    all_ranked = _cached_rank(
                        crop_code, rank_level, 9999, country_code, var_code
                    )
                    if rank_level == 2 and state_name != "(All)":
                        state_districts = set(boundary_gdf[name_col])
                        all_ranked = all_ranked[
                            all_ranked["admin_name"].isin(state_districts)
                        ]
                    merge_df = all_ranked[
                        ["admin_name", "rank_value"]
                    ].copy()
                except Exception:
                    merge_df = ranking_df[
                        ["admin_name", "rank_value"]
                    ].copy()

                map_gdf = boundary_gdf.merge(
                    merge_df,
                    left_on=name_col,
                    right_on="admin_name",
                    how="left",
                )
                map_gdf["rank_value"] = map_gdf["rank_value"].fillna(0)

                import numpy as np

                # Use quantile-based coloring to handle skewed distributions
                values = map_gdf["rank_value"]
                nonzero = values[values > 0]
                if len(nonzero) > 2:
                    # Quantile thresholds for better color spread
                    q33 = float(np.percentile(nonzero, 33))
                    q66 = float(np.percentile(nonzero, 66))
                    vmax = float(nonzero.max())

                    def _color_for(v):
                        if v <= 0:
                            return "#f7fcf5"
                        if v <= q33:
                            return "#c7e9c0"
                        if v <= q66:
                            return "#74c476"
                        return "#005a32"
                else:
                    vmax = float(values.max()) if values.max() > 0 else 1
                    colormap = cm.LinearColormap(
                        colors=["#f7fcf5", "#74c476", "#005a32"],
                        vmin=0,
                        vmax=vmax,
                    )
                    _color_for = lambda v: colormap(v if v else 0)  # noqa: E731

                def style_fn(feature):
                    val = feature["properties"].get("rank_value", 0)
                    return {
                        "fillColor": _color_for(val),
                        "fillOpacity": 0.75,
                        "color": "#333",
                        "weight": 0.5,
                    }

                bounds = map_gdf.total_bounds
                m = folium.Map(tiles="cartodbpositron")

                folium.GeoJson(
                    map_gdf.__geo_interface__,
                    style_function=style_fn,
                    tooltip=folium.GeoJsonTooltip(
                        fields=[name_col, "rank_value"],
                        aliases=["Region", rank_col_label],
                        localize=True,
                    ),
                ).add_to(m)

                # Clean HTML legend
                def _fmt(v):
                    if is_rank_yield:
                        return f"{v:.1f}"
                    if v >= 1_000_000:
                        return f"{v / 1_000_000:.1f}M"
                    if v >= 1_000:
                        return f"{v / 1_000:.0f}K"
                    return f"{v:.0f}"

                legend_html = f"""
                <div style="position:fixed; bottom:30px; left:50px; z-index:1000;
                     background:white; padding:10px 14px; border-radius:6px;
                     box-shadow:0 1px 4px rgba(0,0,0,0.2); font-size:12px;
                     font-family:sans-serif;">
                  <div style="margin-bottom:4px; font-weight:600;">
                    {ranking_crop_name} {rank_var_name} ({rank_unit})
                  </div>
                  <div style="display:flex; align-items:center; gap:6px;">
                    <span>{_fmt(0)}</span>
                    <div style="width:120px; height:12px; border-radius:3px;
                         background:linear-gradient(to right,
                         #f7fcf5, #c7e9c0, #74c476, #005a32);"></div>
                    <span>{_fmt(vmax)}</span>
                  </div>
                </div>
                """
                m.get_root().html.add_child(folium.Element(legend_html))

                m.fit_bounds(
                    [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                    padding=(20, 20),
                )

                st_folium(m, use_container_width=True, height=500)
            else:
                st.caption("Map not available — boundaries not cached.")
        except Exception as e:
            st.caption(f"Map could not be rendered: {e}")

        # Table
        st.subheader("Rankings Data")
        val_col = "rank_value" if "rank_value" in ranking_df.columns else "production_mt"
        show_df = ranking_df[
            ["admin_name", "country_name", val_col]
        ].copy()
        if is_rank_yield:
            show_df["value_fmt"] = show_df[val_col].apply(
                lambda v: f"{v:,.2f}"
            )
        else:
            show_df["value_fmt"] = show_df[val_col].apply(
                lambda v: f"{v:,.0f}"
            )
        show_df = show_df[["admin_name", "country_name", "value_fmt"]]
        show_df.index = range(1, len(show_df) + 1)
        show_df.columns = ["Region", "Country", rank_col_label]
        st.dataframe(show_df, use_container_width=True)

        csv_data = show_df.to_csv(index_label="Rank")
        st.download_button(
            "Download CSV",
            csv_data,
            f"{ranking_crop_name}_rankings.csv",
            "text/csv",
        )


# --- Tab 3: Global Comparisons ---
with tab3:
    g1, g2, g3 = st.columns([3, 2, 1])

    with g1:
        gc_crop_name = st.selectbox(
            "Crop", options=list(CROP_NAMES.values()), key="gc_crop"
        )
        gc_crop_code = next(
            code for code, name in CROP_NAMES.items() if name == gc_crop_name
        )

    with g2:
        gc_level = st.selectbox(
            "Level",
            options=[0, 1],
            format_func=lambda x: {0: "Countries", 1: "States"}[x],
            key="gc_level",
        )

    with g3:
        st.markdown("<br>", unsafe_allow_html=True)
        gc_btn = st.button("Compare", type="primary", use_container_width=True)

    if gc_btn:
        index_path = INDEX_DIR / f"level_{gc_level}.parquet"
        if not index_path.exists():
            st.error(f"No index found for level {gc_level}.")
        else:
            idx = pd.read_parquet(index_path)
            crop_idx = idx[idx["crop_code"] == gc_crop_code].copy()

            if "variable" not in crop_idx.columns:
                crop_idx["variable"] = "P"
                crop_idx["value"] = crop_idx["production_mt"]

            # Level 1: filter to selected country's states
            if gc_level == 1:
                crop_idx = crop_idx[crop_idx["country_code"] == country_code]

            if crop_idx.empty:
                st.warning("No data found for this crop/level.")
            else:
                st.session_state.gc_result_data = crop_idx
                st.session_state.gc_result_crop = gc_crop_name
                st.session_state.gc_result_level = gc_level

    gc_data = st.session_state.get("gc_result_data")
    gc_crop = st.session_state.get("gc_result_crop")
    gc_lvl = st.session_state.get("gc_result_level")

    if gc_data is None:
        st.info(
            "Select a crop and click **Compare** to see "
            "global distribution across all variables."
        )
    elif gc_data.empty:
        st.warning("No data available.")
    else:
        st.markdown("---")
        level_name = {0: "Countries", 1: "States"}[gc_lvl]
        st.subheader(f"{gc_crop} — Global Comparison ({level_name})")

        # Pivot: one row per region, columns for each variable
        pivot = gc_data.pivot_table(
            index=["admin_name", "country_name"],
            columns="variable",
            values="value",
            aggfunc="sum",
        ).reset_index()
        pivot.columns.name = None

        var_rename = {
            "P": "Production (mt)",
            "H": "Harvested Area (ha)",
            "A": "Physical Area (ha)",
            "Y": "Yield (t/ha)",
        }
        pivot = pivot.rename(columns=var_rename)

        prod_col = "Production (mt)"
        yield_col = "Yield (t/ha)"
        if prod_col in pivot.columns:
            pivot = pivot.sort_values(prod_col, ascending=False)
        pivot = pivot.reset_index(drop=True)
        pivot.index += 1

        # For yield chart: only show top 20 producers
        top_producers = set()
        if prod_col in pivot.columns:
            top_producers = set(
                pivot.nlargest(20, prod_col)["admin_name"]
            )

        # --- Three charts side by side ---
        chart_vars = [
            ("Production (mt)", "M mt", 1_000_000),
            ("Harvested Area (ha)", "M ha", 1_000_000),
            ("Yield (t/ha)", "t/ha", 1),
        ]

        cols = st.columns(len(chart_vars))
        for col_st, (col_name, col_unit, divisor) in zip(cols, chart_vars):
            with col_st:
                if col_name in pivot.columns:
                    # For yield: filter to top 20 producers first
                    if col_name == yield_col and top_producers:
                        eligible = pivot[
                            pivot["admin_name"].isin(top_producers)
                        ]
                    else:
                        eligible = pivot
                    chart_df = eligible.nlargest(10, col_name)[
                        ["admin_name", col_name]
                    ].copy()
                    chart_df["chart_val"] = chart_df[col_name] / divisor
                    fmt = ",.2f" if "Yield" in col_name else ",.1f"

                    c = (
                        alt.Chart(chart_df)
                        .mark_bar(cornerRadiusEnd=3, color="#2e8b2e")
                        .encode(
                            x=alt.X("chart_val:Q", title=col_unit),
                            y=alt.Y("admin_name:N", sort="-x", title=""),
                            tooltip=[
                                alt.Tooltip("admin_name:N", title="Region"),
                                alt.Tooltip(
                                    "chart_val:Q", title=col_unit, format=fmt
                                ),
                            ],
                        )
                        .properties(
                            height=300, title=col_name.split(" (")[0]
                        )
                    )
                    st.altair_chart(c, use_container_width=True)

        # --- Choropleth map ---
        if prod_col in pivot.columns:
            st.markdown("---")
            st.subheader(f"{gc_crop} Production — Map")
            try:
                import branca.colormap as cm
                import folium
                import numpy as np
                from streamlit_folium import st_folium

                name_col = f"NAME_{gc_lvl}"
                map_cc = country_code if gc_lvl == 1 else None

                # For level 0, load all country boundaries
                if gc_lvl == 0:
                    # Merge all cached country boundaries
                    gdf_parts = []
                    for cname, ccode in countries.items():
                        g = _cached_boundary_gdf(ccode, 0)
                        if g is not None and "COUNTRY" in g.columns:
                            g = g.copy()
                            g["_name"] = g["COUNTRY"]
                            gdf_parts.append(g[["_name", "geometry"]])
                    if gdf_parts:
                        import geopandas as gpd

                        boundary_gdf = gpd.GeoDataFrame(
                            pd.concat(gdf_parts, ignore_index=True),
                            crs="EPSG:4326",
                        )
                        name_col = "_name"
                    else:
                        boundary_gdf = None
                else:
                    boundary_gdf = _cached_boundary_gdf(country_code, gc_lvl)

                if boundary_gdf is not None and name_col in boundary_gdf.columns:
                    map_merge = pivot[["admin_name", prod_col]].copy()
                    map_gdf = boundary_gdf.merge(
                        map_merge,
                        left_on=name_col,
                        right_on="admin_name",
                        how="left",
                    )
                    map_gdf[prod_col] = map_gdf[prod_col].fillna(0)

                    nonzero = map_gdf[prod_col][map_gdf[prod_col] > 0]
                    vmax = float(nonzero.max()) if len(nonzero) > 0 else 1

                    if len(nonzero) > 2:
                        q33 = float(np.percentile(nonzero, 33))
                        q66 = float(np.percentile(nonzero, 66))

                        def _gc_color(v):
                            if v <= 0:
                                return "#f7fcf5"
                            if v <= q33:
                                return "#c7e9c0"
                            if v <= q66:
                                return "#74c476"
                            return "#005a32"
                    else:
                        cmap = cm.LinearColormap(
                            ["#f7fcf5", "#74c476", "#005a32"], vmin=0, vmax=vmax
                        )
                        _gc_color = lambda v: cmap(v if v else 0)  # noqa: E731

                    def gc_style(feature):
                        val = feature["properties"].get(prod_col, 0)
                        return {
                            "fillColor": _gc_color(val),
                            "fillOpacity": 0.75,
                            "color": "#333",
                            "weight": 0.5,
                        }

                    bounds = map_gdf.total_bounds
                    m = folium.Map(tiles="cartodbpositron")
                    folium.GeoJson(
                        map_gdf.__geo_interface__,
                        style_function=gc_style,
                        tooltip=folium.GeoJsonTooltip(
                            fields=[name_col, prod_col],
                            aliases=["Region", prod_col],
                            localize=True,
                        ),
                    ).add_to(m)
                    m.fit_bounds(
                        [[bounds[1], bounds[0]], [bounds[3], bounds[2]]],
                        padding=(20, 20),
                    )
                    st_folium(m, use_container_width=True, height=450)
            except Exception as e:
                st.caption(f"Map could not be rendered: {e}")

        # --- Data table ---
        st.markdown("---")
        st.subheader("Full Comparison Data")

        show_pivot = pivot.copy()
        # Add global % to production column
        if prod_col in show_pivot.columns:
            global_total = show_pivot[prod_col].sum()
            if global_total > 0:
                show_pivot[prod_col] = show_pivot[prod_col].apply(
                    lambda v: f"{v:,.0f} ({v / global_total * 100:.1f}%)"
                )
            else:
                show_pivot[prod_col] = show_pivot[prod_col].apply(
                    lambda v: f"{v:,.0f}"
                )
        for c in ["Harvested Area (ha)", "Physical Area (ha)"]:
            if c in show_pivot.columns:
                show_pivot[c] = show_pivot[c].apply(lambda v: f"{v:,.0f}")
        if "Yield (t/ha)" in show_pivot.columns:
            show_pivot["Yield (t/ha)"] = show_pivot["Yield (t/ha)"].apply(
                lambda v: f"{v:,.2f}"
            )

        display_cols = ["admin_name", "country_name"]
        for c in [prod_col, "Harvested Area (ha)", "Physical Area (ha)", "Yield (t/ha)"]:
            if c in show_pivot.columns:
                display_cols.append(c)

        show_pivot = show_pivot[display_cols].rename(
            columns={"admin_name": "Region", "country_name": "Country"}
        )
        st.dataframe(show_pivot, use_container_width=True, height=400)

        csv_data = show_pivot.to_csv(index=False)
        st.download_button(
            "Download CSV",
            csv_data,
            f"{gc_crop}_global_comparison.csv",
            "text/csv",
        )
