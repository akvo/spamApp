"""Rule-based visualization selection for conversational BI.

Takes query intent + DataFrame shape → Altair chart specification.
No LLM calls — deterministic and fast.
"""

import altair as alt
import pandas as pd
import streamlit as st


def render_result(title: str, viz_hint: str, df: pd.DataFrame):
    """Render a QueryResult as an appropriate visualization."""
    if df.empty:
        st.info("No data to display.")
        return

    st.subheader(title)

    # Determine numeric and text columns
    num_cols = df.select_dtypes(include="number").columns.tolist()
    text_cols = df.select_dtypes(include="object").columns.tolist()

    if (len(df) == 1 and len(num_cols) <= 2) and not text_cols:
        _render_metric(df, num_cols)
    elif text_cols and num_cols:
        _render_bar(df, text_cols, num_cols, viz_hint)
    elif viz_hint == "stacked_bar" and text_cols and num_cols:
        _render_bar(df, text_cols, num_cols, "stacked_bar")
    else:
        _render_table(df)


def _render_metric(df: pd.DataFrame, num_cols: list[str]):
    """Render a single value as a metric card."""
    cols = st.columns(len(num_cols))
    for i, col_name in enumerate(num_cols):
        val = df.iloc[0][col_name]
        if isinstance(val, float):
            if val >= 1_000_000:
                display = f"{val / 1_000_000:,.1f}M"
            elif val >= 1_000:
                display = f"{val / 1_000:,.0f}K"
            else:
                display = f"{val:,.2f}"
        else:
            display = str(val)
        cols[i].metric(col_name, display)


def _render_bar(
    df: pd.DataFrame,
    text_cols: list[str],
    num_cols: list[str],
    viz_type: str,
):
    """Render a horizontal bar chart."""
    y_col = text_cols[0]
    x_col = num_cols[0]

    # Format axis label with unit
    _AXIS_LABELS = {
        "value": "Value",
        "production_mt": "Production (metric tonnes)",
        "harvested_area_ha": "Harvested Area (hectares)",
        "physical_area_ha": "Physical Area (hectares)",
        "yield_tha": "Yield (t/ha)",
        "total_ha": "Harvested Area (hectares)",
        "total": "Total",
        "pct": "Share (%)",
        "weighted_avg_yield": "Yield (t/ha)",
    }
    x_title = _AXIS_LABELS.get(
        x_col.lower(), x_col.replace("_", " ").title()
    )

    # Determine if we need color encoding
    color_col = text_cols[1] if len(text_cols) > 1 and viz_type == "grouped_bar" else None

    if color_col:
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusEnd=3)
            .encode(
                x=alt.X(f"{x_col}:Q", title=x_title),
                y=alt.Y(f"{y_col}:N", sort="-x", title=""),
                color=alt.Color(
                    f"{color_col}:N",
                    title=color_col.replace("_", " ").title(),
                ),
                tooltip=[
                    alt.Tooltip(f"{y_col}:N"),
                    alt.Tooltip(f"{x_col}:Q", format=",.0f"),
                    alt.Tooltip(f"{color_col}:N"),
                ],
            )
            .properties(height=max(300, len(df) * 25))
        )
    else:
        # Format values for tooltip
        fmt = ",.0f"
        if df[x_col].max() < 100:
            fmt = ",.2f"

        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusEnd=3, color="#2e8b2e")
            .encode(
                x=alt.X(f"{x_col}:Q", title=x_title),
                y=alt.Y(f"{y_col}:N", sort="-x", title=""),
                tooltip=[
                    alt.Tooltip(f"{y_col}:N"),
                    alt.Tooltip(f"{x_col}:Q", format=fmt),
                ],
            )
            .properties(height=max(300, len(df) * 30))
        )

    st.altair_chart(chart, use_container_width=True)


def _render_table(df: pd.DataFrame):
    """Render as a formatted table."""
    # Format numeric columns
    display_df = df.copy()
    for col in display_df.select_dtypes(include="number").columns:
        if display_df[col].max() > 1000:
            display_df[col] = display_df[col].apply(lambda v: f"{v:,.0f}")
        elif display_df[col].max() < 100:
            display_df[col] = display_df[col].apply(lambda v: f"{v:,.2f}")

    st.dataframe(display_df, use_container_width=True)
