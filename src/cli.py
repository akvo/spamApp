"""Typer CLI entry point.

Thin wrapper over analyzer.py and formatter.py — no business logic here.
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from src.analyzer import analyze_location, rank_by_crop
from src.crops import CROPS
from src.formatter import print_crop_list, print_ranking, print_summary, to_csv, to_json

app = typer.Typer(
    name="spam-analyze",
    help="Analyze MapSPAM 2020 crop production data by administrative region.",
)
console = Console()


@app.command()
def location(
    name: Annotated[str, typer.Argument(help="Country or admin region name")],
    level: Annotated[
        int, typer.Option("--level", "-l", help="Admin level: 0=country, 1=state, 2=district")
    ] = 0,
    top: Annotated[int, typer.Option("--top", "-n", help="Number of top crops to display")] = 10,
    crop: Annotated[
        Optional[list[str]], typer.Option("--crop", "-c", help="Specific crop code(s)")
    ] = None,
    variable: Annotated[
        str,
        typer.Option(
            "--var", "-v", help="Variable: production, harvested_area, physical_area, yield"
        ),
    ] = "production",
    year: Annotated[int, typer.Option("--year", "-y", help="Data year")] = 2020,
    output: Annotated[
        Optional[str], typer.Option("--output", "-o", help="Output file (csv or json)")
    ] = None,
    data_dir: Annotated[str, typer.Option("--data", help="Path to data directory")] = "data",
) -> None:
    """Analyze crop production for a specific location."""
    try:
        result = analyze_location(
            location=name,
            admin_level=level,
            data_dir=Path(data_dir),
            year=year,
            variable=variable,
            top_n=top,
            crops=crop,
        )
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    print_summary(result)

    if output:
        out_path = Path(output)
        if out_path.suffix == ".json":
            to_json(result, out_path)
        else:
            to_csv(result, out_path)


@app.command()
def ranking(
    crop_code: Annotated[str, typer.Argument(help="4-letter crop code (e.g., MAIZ)")],
    level: Annotated[
        int, typer.Option("--level", "-l", help="Admin level: 0=country, 1=state")
    ] = 0,
    top: Annotated[int, typer.Option("--top", "-n", help="Number of top regions")] = 10,
    index_dir: Annotated[
        str, typer.Option("--index", help="Path to index directory")
    ] = "data/index",
) -> None:
    """Show top regions for a specific crop (requires pre-built index)."""
    crop_code = crop_code.upper()
    if crop_code not in CROPS:
        console.print(f"[red]Unknown crop code:[/red] {crop_code}")
        raise typer.Exit(1)

    try:
        df = rank_by_crop(crop_code, admin_level=level, index_dir=Path(index_dir), top_n=top)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    crop_name = CROPS[crop_code]["name"]
    print_ranking(df, crop_name)


@app.command()
def crops() -> None:
    """List all available crop codes and their names."""
    print_crop_list(CROPS)


@app.command(name="build-index")
def build_index_cmd(
    level: Annotated[
        int, typer.Option("--level", "-l", help="Admin level to index")
    ] = 0,
    crop: Annotated[
        Optional[list[str]],
        typer.Option("--crop", "-c", help="Specific crop code(s)"),
    ] = None,
    country: Annotated[
        Optional[list[str]],
        typer.Option("--country", help="ISO country code(s)"),
    ] = None,
    year: Annotated[
        int, typer.Option("--year", "-y", help="Data year")
    ] = 2020,
    data_dir: Annotated[
        str, typer.Option("--data", help="Path to data directory")
    ] = "data",
    output_dir: Annotated[
        str, typer.Option("--output", "-o", help="Index output directory")
    ] = "data/index",
    parallel: Annotated[
        int, typer.Option("--parallel", "-j", help="Parallel workers (0=sequential)")
    ] = 0,
) -> None:
    """Build the production index. Use --parallel for multi-country runs."""
    import time

    crops_list = [c.upper() for c in crop] if crop else None
    start = time.time()

    if parallel > 0 and (country is None or len(country) > 1):
        from src.index import build_index_parallel

        codes = [c.upper() for c in country] if country else None
        console.print(
            f"Building index level {level} "
            f"with {parallel} workers..."
        )
        try:
            result_path = build_index_parallel(
                data_dir=Path(data_dir),
                admin_level=level,
                output_dir=Path(output_dir),
                year=year,
                crops=crops_list,
                country_codes=codes,
                max_workers=parallel,
            )
            elapsed = time.time() - start
            console.print(
                f"[green]Index built:[/green] {result_path} "
                f"({elapsed:.0f}s)"
            )
        except (ValueError, FileNotFoundError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        from src.index import build_index

        cc = country[0].upper() if country else None
        console.print(
            f"Building index level {level}"
            f"{f' for {cc}' if cc else ''}..."
        )
        try:
            result_path = build_index(
                data_dir=Path(data_dir),
                admin_level=level,
                output_dir=Path(output_dir),
                year=year,
                crops=crops_list,
                country_code=cc,
            )
            elapsed = time.time() - start
            console.print(
                f"[green]Index built:[/green] {result_path} "
                f"({elapsed:.0f}s)"
            )
        except (ValueError, FileNotFoundError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)


@app.command(name="prep-boundary")
def prep_boundary_cmd(
    path: Annotated[str, typer.Argument(help="Path to boundary file (shapefile, geopackage)")],
    country: Annotated[str, typer.Option("--country", help="ISO country code (e.g., IND)")],
    level: Annotated[int, typer.Option("--level", "-l", help="Admin level")],
    name_col: Annotated[
        str, typer.Option("--name-col", help="Column containing region names")
    ] = "NAME",
    country_name: Annotated[
        Optional[str], typer.Option("--country-name", help="Country name")
    ] = None,
    output_dir: Annotated[
        str, typer.Option("--output", "-o", help="Output directory")
    ] = "data/boundaries",
) -> None:
    """Prepare a custom boundary file to the standard schema."""
    import geopandas as gpd

    from src.boundaries import standardize_boundary

    console.print(f"Loading {path}...")
    gdf = gpd.read_file(path)

    if name_col not in gdf.columns:
        console.print(f"[red]Column '{name_col}' not found.[/red] Available: {list(gdf.columns)}")
        raise typer.Exit(1)

    c_name = country_name or country
    result = standardize_boundary(
        gdf, name_col=name_col, admin_level=level, country_code=country, country_name=c_name
    )

    out_path = Path(output_dir) / f"{country}_{level}.gpkg"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_file(out_path, driver="GPKG")
    console.print(f"[green]Saved:[/green] {out_path} ({len(result)} regions)")


@app.command(name="init-boundaries")
def init_boundaries_cmd(
    countries: Annotated[
        Optional[list[str]],
        typer.Option("--country", "-c", help="ISO3 country codes (e.g., IND BRA)"),
    ] = None,
    levels: Annotated[
        Optional[list[int]],
        typer.Option("--level", "-l", help="Admin levels to download (0, 1, 2)"),
    ] = None,
    cache_path: Annotated[
        str, typer.Option("--cache", help="GeoPackage cache path")
    ] = "data/boundaries/gadm_cache.gpkg",
) -> None:
    """Download GADM boundaries into local GeoPackage cache.

    Pre-downloads admin boundaries so the Streamlit app has instant dropdowns.
    """
    from src.boundaries import fetch_and_cache, list_cached_countries

    if levels is None:
        levels = [0, 1, 2]

    if countries is None:
        # Default set of major agricultural countries
        countries = [
            "ARG", "AUS", "BGD", "BRA", "CAN", "CHN", "COD", "COL",
            "EGY", "ETH", "FRA", "DEU", "GHA", "IND", "IDN", "IRN",
            "ITA", "JPN", "KEN", "MWI", "MYS", "MEX", "MOZ", "MMR",
            "NPL", "NGA", "PAK", "PER", "PHL", "RUS", "ZAF", "ESP",
            "LKA", "SDN", "TZA", "THA", "TUR", "UGA", "UKR", "GBR",
            "USA", "VNM", "ZMB", "ZWE", "KHM",
        ]

    cache = Path(cache_path)
    total = len(countries) * len(levels)
    done = 0

    from rich.progress import Progress

    with Progress() as progress:
        task = progress.add_task("Downloading GADM...", total=total)
        for code in countries:
            for level in levels:
                progress.update(task, description=f"{code} level {level}")
                try:
                    fetch_and_cache(code, level, cache)
                except Exception as e:
                    console.print(f"[yellow]Skip {code} L{level}:[/yellow] {e}")
                done += 1
                progress.update(task, completed=done)

    cached = list_cached_countries(cache)
    console.print(f"[green]Done:[/green] {len(cached)} layers in {cache}")


if __name__ == "__main__":
    app()
