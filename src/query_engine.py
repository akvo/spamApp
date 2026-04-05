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

### district_lookup (maps districts to their parent state)
- code (TEXT) — country ISO3 code
- state (TEXT) — state/province name (matches admin_name in states table)
- district (TEXT) — district name (matches admin_name in districts table)

To query districts within a state, JOIN with district_lookup:
  SELECT d.admin_name, d.value AS production_mt
  FROM districts d
  JOIN district_lookup dl ON d.admin_name = dl.district AND d.country_code = dl.code
  WHERE dl.state = 'Bali' AND dl.code = 'IDN'
  AND d.crop_code = 'RICE' AND d.variable = 'P'

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
   - CRITICAL: For ranking yield across locations, you MUST filter to meaningful producers:
     JOIN with harvested area (variable='H') and require h.value >= 5000 (hectares).
     This prevents tiny regions with inflated yields from dominating.
     Always use this pattern for yield rankings:
     SELECT y.admin_name, y.value AS yield_tha
     FROM [table] y JOIN [table] h ON y.admin_code = h.admin_code AND y.crop_code = h.crop_code
     WHERE y.crop_code='...' AND y.variable='Y' AND h.variable='H' AND h.value >= 5000
     ORDER BY y.value DESC LIMIT 10
   - For averaging yield across multiple locations: weight by harvested area:
     SUM(y.value * h.value) / NULLIF(SUM(h.value), 0)
   - NEVER use AVG(value) or SUM(value) for yield
   - NEVER rank yield without the harvested area >= 5000 filter
3. Default to variable='P' (Production) and tech_level='A' (All systems) unless specified
4. The database has state-level data for ALL countries including the US, India, Brazil, etc.
   ALL countries have states/provinces AND districts. Do NOT assume any country is missing.
   Use the appropriate table: countries for country-level, states for state-level, districts for district-level
5. If the user misspells a location, use LIKE with the closest match. Do NOT return an error
   saying the location doesn't exist — try a fuzzy search with LIKE first.
6. Always include LIMIT (default 10 if not specified, minimum 5 for rankings)
7. Even for "which is the highest/largest" questions, return top 10 with ORDER BY DESC
   so the user sees context. Use viz_hint "bar", not "metric"
7. crop_name values are proper case: "Wheat", "Rice", "Maize" (not lowercase)
8. admin_name values may have no spaces (e.g., "MadhyaPradesh", "WestBengal")
   and may contain special characters (e.g., "Murang'a").
   For location name matching, use LOWER(admin_name) LIKE '%keyword%' instead of exact match.
   Example: WHERE LOWER(admin_name) LIKE '%murang%' instead of admin_name = "Murang'a"
9. A "county" or "province" is typically a state (level 1). Search states first.
   If not found, try districts. Use the district_lookup table to check.
10. Always include admin_name or crop_name in SELECT so the chart shows labels
11. For "where in [country]" questions, default to the states table (level 1),
    not districts. Only use districts if the user specifically mentions districts
    or asks about a specific state's sub-regions.
11. Always alias the value column with the unit. Examples:
    - value AS production_mt (for production)
    - value AS harvested_area_ha (for harvested area)
    - value AS yield_tha (for yield)
    - value AS physical_area_ha (for physical area)

## Unclear or Invalid Queries
If the user's input is gibberish, unrelated to crop data, or too vague to generate SQL,
return: {"intent":"error","sql":"","title":"","viz_hint":"","error":"I couldn't understand that question. Try asking about crop production, harvested area, or yield for specific countries or regions."}

## Response Format
Return ONLY a JSON object (no markdown, no explanation):
{
  "intent": "ranking|comparison|breakdown|single_value|error",
  "sql": "SELECT ...",
  "title": "Short descriptive title for the chart",
  "description": "One sentence explaining what the data shows, including variable, unit, level, and any filters applied. Example: 'Showing top 10 states in India by rice production in metric tonnes, all farming systems combined.'",
  "viz_hint": "bar|grouped_bar|stacked_bar|metric|table",
  "error": "" (only for intent=error)
}
"""

# Few-shot examples
FEW_SHOT_EXAMPLES = [
    {
        "user": "Top 5 wheat producing countries",
        "assistant": '{"intent":"ranking","sql":"SELECT admin_name, value AS production_mt FROM countries WHERE crop_code=\'WHEA\' AND variable=\'P\' ORDER BY value DESC LIMIT 5","title":"Top 5 Wheat Producing Countries","viz_hint":"bar"}',
    },
    {
        "user": "Show me rice production in Indian states",
        "assistant": '{"intent":"ranking","sql":"SELECT admin_name, value AS production_mt FROM states WHERE crop_code=\'RICE\' AND variable=\'P\' AND country_code=\'IND\' ORDER BY value DESC LIMIT 10","title":"Rice Production by Indian State","viz_hint":"bar"}',
    },
    {
        "user": "Compare maize yield between India and Brazil",
        "assistant": '{"intent":"comparison","sql":"SELECT admin_name, value AS yield_tha FROM countries WHERE crop_code=\'MAIZ\' AND variable=\'Y\' AND admin_name IN (\'India\', \'Brazil\')","title":"Maize Yield: India vs Brazil","viz_hint":"grouped_bar"}',
    },
    {
        "user": "What percentage of world rice does India produce?",
        "assistant": '{"intent":"single_value","sql":"SELECT admin_name, value AS production_mt, ROUND(value * 100.0 / SUM(value) OVER (), 1) AS pct FROM countries WHERE crop_code=\'RICE\' AND variable=\'P\' ORDER BY value DESC LIMIT 10","title":"India Share of World Rice Production","viz_hint":"bar"}',
    },
    {
        "user": "Top crops in Kenya by production",
        "assistant": '{"intent":"breakdown","sql":"SELECT crop_name, category, value AS production_mt FROM countries WHERE admin_name=\'Kenya\' AND variable=\'P\' AND value > 0 ORDER BY value DESC LIMIT 15","title":"Top Crops in Kenya","viz_hint":"bar"}',
    },
    {
        "user": "Which countries have the highest wheat yield?",
        "assistant": '{"intent":"ranking","sql":"SELECT c.admin_name, c.value AS yield_tha FROM countries c JOIN countries h ON c.admin_code = h.admin_code AND c.crop_code = h.crop_code WHERE c.crop_code=\'WHEA\' AND c.variable=\'Y\' AND h.variable=\'H\' AND h.value >= 5000 ORDER BY c.value DESC LIMIT 10","title":"Top Wheat Yield Countries (min 5000 ha)","viz_hint":"bar"}',
    },
    {
        "user": "Irrigated vs rainfed rice in India",
        "assistant": '{"intent":"comparison","sql":"SELECT tech_level, SUM(value) AS production_mt FROM states WHERE crop_code=\'RICE\' AND variable=\'P\' AND tech_level IN (\'I\', \'R\') AND country_code=\'IND\' GROUP BY tech_level","title":"Rice: Irrigated vs Rainfed in India","viz_hint":"bar"}',
    },
    {
        "user": "Total harvested area for cereals globally",
        "assistant": '{"intent":"breakdown","sql":"SELECT crop_name, SUM(value) AS harvested_area_ha FROM countries WHERE category=\'Cereals\' AND variable=\'H\' GROUP BY crop_name ORDER BY harvested_area_ha DESC","title":"Cereal Crops by Harvested Area (Global)","viz_hint":"bar"}',
    },
]


@dataclass
class QueryResult:
    """Result of a conversational BI query."""

    success: bool
    intent: str = ""
    sql: str = ""
    title: str = ""
    description: str = ""
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
    # District-to-state lookup for filtering districts by state
    lookup_path = Path("data/boundaries/districts_lookup.parquet")
    if lookup_path.exists():
        conn.execute(
            f"CREATE VIEW district_lookup AS SELECT * FROM read_parquet('{lookup_path}')"
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
        temperature=0,
        system=SCHEMA_PROMPT,
        messages=messages,
    )

    import json

    try:
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)
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
        allowed_tables = {"countries", "states", "districts", "district_lookup"}
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

    if "error" in llm_result and llm_result.get("intent") != "error":
        return QueryResult(
            success=False,
            error=llm_result["error"],
        )

    sql = llm_result.get("sql", "")
    intent = llm_result.get("intent", "")
    title = llm_result.get("title", "")
    description = llm_result.get("description", "")
    viz_hint = llm_result.get("viz_hint", "table")

    # Handle error intent (gibberish, unrelated, too vague)
    if intent == "error" or not sql:
        return QueryResult(
            success=False,
            error=llm_result.get("error", "I couldn't understand that question. Try asking about crop production, area, or yield for specific countries or regions."),
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
            description=description,
            viz_hint=viz_hint,
            data=pd.DataFrame(),
            message="No data found. Try a different crop, location, or variable.",
        )

    return QueryResult(
        success=True,
        intent=intent,
        sql=sql,
        title=title,
        description=description,
        viz_hint=viz_hint,
        data=df,
    )
