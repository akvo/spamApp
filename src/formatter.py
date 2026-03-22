"""Output formatting: Rich tables, CSV/JSON export.

No side effects except printing to stdout or writing to specified output files.
Never modifies data structures passed to it (see CONTRACTS.md).
"""

import json
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from src.analyzer import AnalysisResult
from src.crops import VARIABLES

console = Console()


def print_summary(result: AnalysisResult) -> None:
    """Print a Rich-formatted summary of an AnalysisResult."""
    var_info = VARIABLES.get(result.variable[0].upper(), {})
    unit = var_info.get("unit", "")

    console.print()
    console.print(
        f"[bold]Location:[/bold] {result.location_name} (admin level {result.admin_level})"
    )
    console.print(f"[bold]Variable:[/bold] {result.variable} ({unit})")
    console.print(f"[bold]Total:[/bold] {result.total:,.0f} {unit}")
    console.print()

    # Top crops table
    table = Table(title=f"Top {len(result.top_crops)} Crops")
    table.add_column("Rank", style="dim", width=4)
    table.add_column("Crop", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("% of Total", justify="right")

    for i, (name, value) in enumerate(result.top_crops, 1):
        pct = (value / result.total * 100) if result.total > 0 else 0
        table.add_row(str(i), name, f"{value:,.0f}", f"{pct:.1f}%")

    console.print(table)


def print_ranking(df: pd.DataFrame, crop_name: str) -> None:
    """Print a Rich table for crop rankings across regions."""
    console.print()
    table = Table(title=f"Top {len(df)} Regions — {crop_name} Production")
    table.add_column("Rank", style="dim", width=4)
    table.add_column("Region", style="bold")
    table.add_column("Country")
    table.add_column("Production (mt)", justify="right")

    for i, (_, row) in enumerate(df.iterrows(), 1):
        table.add_row(
            str(i),
            row["admin_name"],
            row.get("country_name", ""),
            f"{row['production_mt']:,.0f}",
        )

    console.print(table)


def print_crop_list(crops_dict: dict) -> None:
    """Print all available crop codes as a Rich table."""
    table = Table(title="Available Crop Codes")
    table.add_column("Code", style="bold", width=6)
    table.add_column("Name")
    table.add_column("Category")

    # Group by category
    by_category = {}
    for code, info in sorted(crops_dict.items()):
        cat = info["category"]
        by_category.setdefault(cat, []).append((code, info))

    for category in sorted(by_category.keys()):
        for code, info in by_category[category]:
            table.add_row(code, info["name"], category)

    console.print(table)


def to_csv(result: AnalysisResult, path: Path) -> None:
    """Export AnalysisResult crop_data to CSV."""
    result.crop_data.to_csv(path, index=False)
    console.print(f"Exported to {path}")


def to_json(result: AnalysisResult, path: Path) -> None:
    """Export AnalysisResult to JSON."""
    data = {
        "location": result.location_name,
        "admin_level": result.admin_level,
        "variable": result.variable,
        "total": result.total,
        "top_crops": [{"name": n, "value": v} for n, v in result.top_crops],
        "crop_data": result.crop_data.to_dict(orient="records"),
    }
    Path(path).write_text(json.dumps(data, indent=2))
    console.print(f"Exported to {path}")
