"""Conversational BI: natural language → SQL → visualization.

Orchestrates the pipeline: classify intent, generate SQL, validate,
execute against DuckDB, select visualization.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from src.crops import CROPS, VARIABLES

# --- Schema definition for the LLM prompt ---
SCHEMA_PROMPT = """You are a SQL expert for the MapSPAM 2020 crop production database.

## Tables

Three tables (DuckDB views over parquet files):

### countries (level 0 — country-level data)
### states (level 1 — state/province-level data)
### districts (level 2 — district-level data)

All three share the same schema:
- admin_name (TEXT) — region name (e.g., "India", "Maharashtra", "Nagpur")
- admin_code (TEXT) — unique code
- admin_level (INT) — 0=country, 1=state, 2=district
- country_code (TEXT) — ISO 3-letter code (e.g., "IND", "BRA")
- country_name (TEXT) — country name
- crop_code (TEXT) — 4-letter SPAM code
- crop_name (TEXT) — full crop name
- category (TEXT) — crop category
- tech_level (TEXT) — "A"=All systems, "I"=Irrigated, "R"=Rainfed
- variable (TEXT) — "P"=Production, "H"=Harvested Area, "A"=Physical Area, "Y"=Yield
- variable_name (TEXT) — full variable name
- unit (TEXT) — unit of measurement
- value (FLOAT) — the numeric value
- production_mt (FLOAT) — production in metric tonnes (backward compat)

## Crop Codes
"""

# Build the crop list for the prompt
_CROP_LIST = "\n".join(
    f"- {code} = {info['name']} ({info['category']})"
    for code, info in sorted(CROPS.items())
)

_VARIABLE_LIST = "\n".join(
    f"- {code} = {info['name']} ({info['unit']})" for code, info in VARIABLES.items()
)

SCHEMA_PROMPT += _CROP_LIST + "\n\n## Variables\n" + _VARIABLE_LIST

SCHEMA_PROMPT += """

## Critical Rules
1. For Production (P), Harvested Area (H), Physical Area (A): use SUM for aggregation
2. For Yield (Y): the value column already has weighted averages per location.
   - For single-location yield: just use the value directly
   - For ranking yield across locations: ORDER BY value DESC
   - For averaging yield across multiple locations: you MUST weight by harvested area:
     SUM(y.value * h.value) / NULLIF(SUM(h.value), 0)
     where y is the yield row and h is the harvested area row for the same crop/location
   - NEVER use AVG(value) or SUM(value) for yield
3. Default to variable='P' (Production) and tech_level='A' (All systems) unless specified
4. Use the appropriate table: countries for country-level, states for state-level, districts for district-level
5. Always include LIMIT (default 10 if not specified)
6. crop_name values are proper case: "Wheat", "Rice", "Maize" (not lowercase)
7. admin_name values may have no spaces (e.g., "MadhyaPradesh", "WestBengal")

## Response Format
Return ONLY a JSON object (no markdown, no explanation):
{
  "intent": "ranking|comparison|breakdown|single_value|general",
  "sql": "SELECT ...",
  "title": "Short descriptive title for the chart",
  "viz_hint": "bar|grouped_bar|stacked_bar|metric|table"
}
"""

# Few-shot examples
FEW_SHOT_EXAMPLES = [
    {
        "user": "Top 5 wheat producing countries",
        "assistant": '{"intent":"ranking","sql":"SELECT admin_name, value FROM countries WHERE crop_code=\'WHEA\' AND variable=\'P\' AND tech_level=\'A\' ORDER BY value DESC LIMIT 5","title":"Top 5 Wheat Producing Countries","viz_hint":"bar"}',
    },
    {
        "user": "Show me rice production in Indian states",
        "assistant": '{"intent":"ranking","sql":"SELECT admin_name, value FROM states WHERE crop_code=\'RICE\' AND variable=\'P\' AND tech_level=\'A\' AND country_code=\'IND\' ORDER BY value DESC LIMIT 10","title":"Rice Production by Indian State","viz_hint":"bar"}',
    },
    {
        "user": "Compare maize yield between India and Brazil",
        "assistant": '{"intent":"comparison","sql":"SELECT admin_name, value FROM countries WHERE crop_code=\'MAIZ\' AND variable=\'Y\' AND tech_level=\'A\' AND admin_name IN (\'India\', \'Brazil\')","title":"Maize Yield: India vs Brazil","viz_hint":"grouped_bar"}',
    },
    {
        "user": "What percentage of world rice does India produce?",
        "assistant": '{"intent":"single_value","sql":"SELECT admin_name, value, ROUND(value * 100.0 / SUM(value) OVER (), 1) as pct FROM countries WHERE crop_code=\'RICE\' AND variable=\'P\' AND tech_level=\'A\' ORDER BY value DESC LIMIT 10","title":"India Share of World Rice Production","viz_hint":"bar"}',
    },
    {
        "user": "Top crops in Kenya by production",
        "assistant": '{"intent":"breakdown","sql":"SELECT crop_name, category, value FROM countries WHERE admin_name=\'Kenya\' AND variable=\'P\' AND tech_level=\'A\' AND value > 0 ORDER BY value DESC LIMIT 15","title":"Top Crops in Kenya","viz_hint":"bar"}',
    },
    {
        "user": "Which countries have the highest wheat yield?",
        "assistant": '{"intent":"ranking","sql":"SELECT c.admin_name, c.value as yield_tha FROM countries c JOIN countries h ON c.admin_code = h.admin_code AND c.crop_code = h.crop_code WHERE c.crop_code=\'WHEA\' AND c.variable=\'Y\' AND c.tech_level=\'A\' AND h.variable=\'H\' AND h.tech_level=\'A\' AND h.value >= 5000 ORDER BY c.value DESC LIMIT 10","title":"Top Wheat Yield Countries (min 5000 ha)","viz_hint":"bar"}',
    },
    {
        "user": "Irrigated vs rainfed rice in India",
        "assistant": '{"intent":"comparison","sql":"SELECT tech_level, SUM(value) as total FROM states WHERE crop_code=\'RICE\' AND variable=\'P\' AND tech_level IN (\'I\', \'R\') AND country_code=\'IND\' GROUP BY tech_level","title":"Rice: Irrigated vs Rainfed in India","viz_hint":"bar"}',
    },
    {
        "user": "Total harvested area for cereals globally",
        "assistant": '{"intent":"breakdown","sql":"SELECT crop_name, SUM(value) as total_ha FROM countries WHERE category=\'Cereals\' AND variable=\'H\' AND tech_level=\'A\' GROUP BY crop_name ORDER BY total_ha DESC","title":"Cereal Crops by Harvested Area (Global)","viz_hint":"bar"}',
    },
]


@dataclass
class QueryResult:
    """Result of a conversational BI query."""

    success: bool
    intent: str = ""
    sql: str = ""
    title: str = ""
    viz_hint: str = "table"
    data: pd.DataFrame = field(default_factory=pd.DataFrame)
    error: str = ""
    message: str = ""


def _get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with views over parquet files."""
    conn = duckdb.connect()
    for level, name in [(0, "countries"), (1, "states"), (2, "districts")]:
        path = Path(f"data/index/level_{level}.parquet")
        if path.exists():
            conn.execute(
                f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')"
            )
    return conn


def _generate_sql(user_query: str, chat_history: list | None = None) -> dict:
    """Call Claude to classify intent and generate SQL."""
    import anthropic

    # Get API key
    try:
        import streamlit as st

        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        api_key = ""
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"error": "No API key configured."}

    # Build messages with few-shot examples
    messages = []
    for ex in FEW_SHOT_EXAMPLES:
        messages.append({"role": "user", "content": ex["user"]})
        messages.append({"role": "assistant", "content": ex["assistant"]})

    # Add recent chat history for context
    if chat_history:
        for msg in chat_history[-6:]:
            messages.append(msg)

    messages.append({"role": "user", "content": user_query})

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SCHEMA_PROMPT,
        messages=messages,
    )

    import json

    try:
        return json.loads(response.content[0].text)
    except (json.JSONDecodeError, IndexError):
        return {"error": f"Failed to parse LLM response: {response.content[0].text}"}


def _validate_sql(sql: str) -> tuple[bool, str]:
    """Validate SQL safety using sqlglot."""
    import sqlglot

    try:
        parsed = sqlglot.parse(sql, dialect="duckdb")
    except sqlglot.errors.ParseError as e:
        return False, f"SQL parse error: {e}"

    for statement in parsed:
        if statement is None:
            continue
        # Only allow SELECT
        if statement.key != "select":
            return False, f"Only SELECT statements allowed, got: {statement.key}"

        # Check table references
        allowed_tables = {"countries", "states", "districts"}
        for table in statement.find_all(sqlglot.exp.Table):
            if table.name.lower() not in allowed_tables:
                return False, f"Unknown table: {table.name}"

    return True, ""


def _execute_sql(sql: str) -> tuple[pd.DataFrame | None, str]:
    """Execute SQL against DuckDB and return results."""
    conn = _get_duckdb_conn()

    # Add LIMIT if not present
    if "limit" not in sql.lower():
        sql = sql.rstrip(";") + " LIMIT 1000"

    try:
        result = conn.execute(sql).fetchdf()
        return result, ""
    except Exception as e:
        return None, str(e)


def ask_data(
    user_query: str, chat_history: list | None = None
) -> QueryResult:
    """End-to-end: natural language → SQL → results.

    Returns QueryResult with data and visualization hints.
    """
    # Step 1: Generate SQL via LLM
    llm_result = _generate_sql(user_query, chat_history)

    if "error" in llm_result:
        return QueryResult(
            success=False,
            error=llm_result["error"],
        )

    sql = llm_result.get("sql", "")
    intent = llm_result.get("intent", "")
    title = llm_result.get("title", "")
    viz_hint = llm_result.get("viz_hint", "table")

    if not sql:
        return QueryResult(
            success=False,
            error="No SQL generated.",
        )

    # Step 2: Validate SQL
    valid, validation_error = _validate_sql(sql)
    if not valid:
        return QueryResult(
            success=False,
            sql=sql,
            error=f"SQL validation failed: {validation_error}",
        )

    # Step 3: Execute
    df, exec_error = _execute_sql(sql)

    if exec_error:
        # One retry: send error back to LLM
        retry_result = _generate_sql(
            f"The previous SQL failed with error: {exec_error}\n"
            f"Original query: {user_query}\n"
            f"Failed SQL: {sql}\n"
            f"Please fix the SQL.",
            chat_history,
        )
        if "error" not in retry_result:
            retry_sql = retry_result.get("sql", "")
            valid2, _ = _validate_sql(retry_sql)
            if valid2:
                df, exec_error2 = _execute_sql(retry_sql)
                if not exec_error2:
                    sql = retry_sql
                    exec_error = ""

        if exec_error:
            return QueryResult(
                success=False,
                sql=sql,
                error=f"Query failed: {exec_error}",
            )

    if df is None or df.empty:
        return QueryResult(
            success=True,
            intent=intent,
            sql=sql,
            title=title,
            viz_hint=viz_hint,
            data=pd.DataFrame(),
            message="No data found. Try a different crop, location, or variable.",
        )

    return QueryResult(
        success=True,
        intent=intent,
        sql=sql,
        title=title,
        viz_hint=viz_hint,
        data=df,
    )
