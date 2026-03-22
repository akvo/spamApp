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


# --- Check cache ---
countries = get_cached_country_names()
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

    states = get_cached_states(country_code)
    state_options = ["(All)"] + states
    state_name = st.selectbox("State / Province", options=state_options)

    district_name = None
    if state_name != "(All)" and states:
        districts = get_cached_districts(country_code, state_name)
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


# --- Header ---
st.title("SPAM 2020 Crop Analyzer")

# --- Tabs ---
tab1, tab2 = st.tabs(["Location Analysis", "Crop Rankings"])


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

    result = st.session_state.get("analysis_result")
    if result is None:
        st.info("Select a location in the sidebar and click **Analyze**.")
    else:
        is_yield = result.variable == "yield"
        var_info = VARIABLES.get(result.variable[0].upper(), {})
        unit = var_info.get("unit", "")

        # Header metrics
        level_label = {0: "Country", 1: "State", 2: "District"}[
            result.admin_level
        ]
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
                st.subheader(
                    f"Top {top_n_display} Crops — {var_title} ({unit})"
                )

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
                st.caption(
                    "Category breakdown not applicable for yield."
                )

        # Full data table
        st.markdown("---")
        st.subheader("All Crops Data")

        display_df = result.crop_data.copy()
        display_df = display_df[display_df["value"] > 0]
        display_df = display_df.sort_values("value", ascending=False)
        display_df = display_df.reset_index(drop=True)
        display_df.index += 1

        if is_yield:
            display_df["value"] = display_df["value"].round(2)
        else:
            display_df["value"] = display_df["value"].round(0).astype(int)

        if not is_yield:
            total = display_df["value"].sum()
            if total > 0:
                display_df["% of Total"] = (
                    display_df["value"] / total * 100
                ).round(1)

        show_cols = ["crop_name", "category", "value"]
        if "% of Total" in display_df.columns:
            show_cols.append("% of Total")

        rename_map = {
            "crop_name": "Crop",
            "category": "Category",
            "value": unit,
        }
        styled_df = display_df[show_cols].rename(columns=rename_map)

        col_config = {}
        if not is_yield:
            col_config[unit] = st.column_config.NumberColumn(format="%,.0f")
        else:
            col_config[unit] = st.column_config.NumberColumn(format="%,.2f")

        st.dataframe(
            styled_df,
            use_container_width=True,
            height=400,
            column_config=col_config,
        )

        # Downloads
        dl1, dl2, _ = st.columns([1, 1, 4])
        csv_data = (
            display_df[show_cols]
            .rename(columns=rename_map)
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
            df = rank_by_crop(
                crop_code,
                admin_level=rank_level,
                index_dir=INDEX_DIR,
                top_n=top_n,
                country_code=country_code,
            )
            # If a state is selected, filter districts to that state
            # by looking up which districts belong to it from GADM cache
            if selected_level == 1 and rank_level == 2 and not df.empty:
                boundary_gdf = _read_cache(country_code, 2)
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

        # Header
        h1, h2, h3 = st.columns(3)
        h1.metric("Crop", ranking_crop_name)
        h2.metric("Level", level_desc)
        h3.metric("Regions", len(ranking_df))

        st.markdown("---")

        # Bar chart — highlight selected region if at deepest level
        st.subheader(ranking_title)

        if highlight:
            # Add a color column to highlight the selected region
            ranking_df = ranking_df.copy()
            ranking_df["_highlight"] = ranking_df["admin_name"].apply(
                lambda x: "Selected" if x == highlight else "Other"
            )
            chart = (
                alt.Chart(ranking_df)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("production_mt:Q", title="Production (mt)"),
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
                            "production_mt:Q",
                            title="Production (mt)",
                            format=",.0f",
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
                    x=alt.X("production_mt:Q", title="Production (mt)"),
                    y=alt.Y("admin_name:N", sort="-x", title=""),
                    tooltip=[
                        alt.Tooltip("admin_name:N", title="Region"),
                        alt.Tooltip("country_name:N", title="Country"),
                        alt.Tooltip(
                            "production_mt:Q",
                            title="Production (mt)",
                            format=",.0f",
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
            boundary_gdf = _read_cache(country_code, rank_level)

            if boundary_gdf is not None and name_col in boundary_gdf.columns:
                merge_df = ranking_df[["admin_name", "production_mt"]].copy()
                map_gdf = boundary_gdf.merge(
                    merge_df,
                    left_on=name_col,
                    right_on="admin_name",
                    how="left",
                )
                map_gdf["production_mt"] = map_gdf["production_mt"].fillna(0)

                # Build a simple linear colormap
                vmin = 0
                vmax = map_gdf["production_mt"].max()
                if vmax == 0:
                    vmax = 1
                colormap = cm.LinearColormap(
                    colors=["#f7fcf5", "#74c476", "#005a32"],
                    vmin=vmin,
                    vmax=vmax,
                )

                # Style each feature by its production value
                def style_fn(feature):
                    val = feature["properties"].get("production_mt", 0)
                    return {
                        "fillColor": colormap(val if val else 0),
                        "fillOpacity": 0.75,
                        "color": "#333",
                        "weight": 0.5,
                    }

                # Fit to data bounds
                bounds = map_gdf.total_bounds
                m = folium.Map(tiles="cartodbpositron")

                folium.GeoJson(
                    map_gdf.__geo_interface__,
                    style_function=style_fn,
                    tooltip=folium.GeoJsonTooltip(
                        fields=[name_col, "production_mt"],
                        aliases=["Region", "Production (mt)"],
                        localize=True,
                    ),
                ).add_to(m)

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
        show_df = ranking_df[
            ["admin_name", "country_name", "production_mt"]
        ].copy()
        show_df.index = range(1, len(show_df) + 1)
        show_df.columns = ["Region", "Country", "Production (mt)"]
        st.dataframe(
            show_df,
            use_container_width=True,
            column_config={
                "Production (mt)": st.column_config.NumberColumn(
                    format="%,.0f"
                )
            },
        )

        csv_data = show_df.to_csv(index_label="Rank")
        st.download_button(
            "Download CSV",
            csv_data,
            f"{ranking_crop_name}_rankings.csv",
            "text/csv",
        )
