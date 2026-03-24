"""Curated FAQ content for the Help tab. No external dependencies."""

FAQ_SECTIONS = {
    "About the Dataset": [
        {
            "q": "What is MapSPAM?",
            "a": (
                "MapSPAM (Spatial Production Allocation Model) is a global dataset "
                "that provides spatially-disaggregated crop production statistics at "
                "~10km resolution. It allocates national and subnational agricultural "
                "statistics to individual grid cells using a cross-entropy optimization "
                "approach. The 2020 version (V2r0) covers 46 crops across the entire globe."
            ),
        },
        {
            "q": "What year does this data cover?",
            "a": (
                "This tool uses MapSPAM 2020 Version 2 Release 0 (V2r0). "
                "The data represents crop production patterns for the year 2020."
            ),
        },
        {
            "q": "How many crops are included?",
            "a": (
                "46 crops organized into 11 categories: Cereals (8), "
                "Roots & Tubers (5), Pulses (6), Oil Crops (8), Sugar Crops (2), "
                "Fibres (2), Stimulants (5), Fruits (5), Vegetables (3), and Other (2). "
                "Use the Location Analysis tab to see all crops for any region."
            ),
        },
        {
            "q": "What is the spatial resolution?",
            "a": (
                "The GeoTIFF rasters are at 5 arc-minute resolution (~10km at the equator). "
                "Each pixel represents the estimated crop production for that grid cell."
            ),
        },
    ],
    "Variables & Methodology": [
        {
            "q": "What variables are available?",
            "a": (
                "Four variables:\n"
                "- **Production** (metric tonnes): total output\n"
                "- **Harvested Area** (hectares): area actually harvested\n"
                "- **Physical Area** (hectares): physical land area planted\n"
                "- **Yield** (tonnes/hectare): productivity measure"
            ),
        },
        {
            "q": "How is yield calculated?",
            "a": (
                "Yield is a weighted average, not a simple sum. For a region, "
                "it's calculated as: sum(yield_pixel × harvested_area_pixel) / "
                "sum(harvested_area_pixel). This ensures larger producing areas "
                "have proportionally more influence on the regional average yield."
            ),
        },
        {
            "q": "What are technology levels (Irrigated vs Rainfed)?",
            "a": (
                "Each crop has three technology level variants:\n"
                "- **A (All)**: total across all production systems\n"
                "- **I (Irrigated)**: irrigated production only\n"
                "- **R (Rainfed)**: rainfed production only\n\n"
                "The stacked bar charts show the I/R breakdown. "
                "Note: A = I + R (they sum to the total)."
            ),
        },
        {
            "q": "Why doesn't it make sense to sum production across crops?",
            "a": (
                "Different crops have vastly different densities, water content, "
                "and economic value. Adding 395M tonnes of sugarcane to 108M tonnes "
                "of wheat gives a meaningless number. The tool avoids showing "
                "cross-crop totals for this reason."
            ),
        },
    ],
    "Using the Tool": [
        {
            "q": "How do I analyze a specific region?",
            "a": (
                "1. Select Country, State/Province, and optionally District in the sidebar\n"
                "2. Choose the Variable (Production, Area, or Yield)\n"
                "3. Go to the 'Location Analysis' tab and click 'Analyze'\n"
                "4. The top crops bar chart, category breakdown, and data table will appear"
            ),
        },
        {
            "q": "How do I see crop rankings?",
            "a": (
                "Go to the 'Crop Rankings' tab, select a crop and click 'Show Rankings'. "
                "The ranking level is determined by your sidebar selection:\n"
                "- Country selected → shows top states\n"
                "- State selected → shows top districts\n"
                "- District selected → compares against sibling districts"
            ),
        },
        {
            "q": "What does the Global Comparisons tab show?",
            "a": (
                "It shows a single crop's distribution across all countries or states, "
                "comparing Production, Harvested Area, and Yield side by side. "
                "This is independent of the sidebar country selection — it's a global view."
            ),
        },
        {
            "q": "Why are some crops missing from the dropdown?",
            "a": (
                "In the Crop Rankings tab, the dropdown only shows crops that have "
                "nonzero production data in the selected country. If a crop doesn't "
                "grow in that country, it won't appear."
            ),
        },
    ],
    "Data Quality & Interpretation": [
        {
            "q": "Why does a small region show extremely high yield?",
            "a": (
                "Small regions with very little harvested area can show inflated yields "
                "(e.g., a 2-hectare greenhouse operation). The tool filters yield rankings "
                "to only show regions with >= 5,000 hectares of harvested area AND in the "
                "top 20 by production. This prevents tiny operations from dominating."
            ),
        },
        {
            "q": "Why don't the district totals add up to the state total?",
            "a": (
                "Minor discrepancies are normal. The tool uses raster pixel masking — "
                "pixels at district borders are assigned to the district whose center "
                "falls inside the boundary. Some pixels may be counted in one district "
                "but not its neighbor, causing small differences when summed."
            ),
        },
        {
            "q": "Where do the administrative boundaries come from?",
            "a": (
                "Boundaries are from GADM (Global Administrative Areas) version 4.1, "
                "downloaded and cached locally. Custom boundaries can override GADM — "
                "place a GeoPackage file in data/boundaries/."
            ),
        },
        {
            "q": "What does the map color represent?",
            "a": (
                "The choropleth map colors regions by their share of total production "
                "for that crop. A region producing 75% of the world's output will be "
                "much darker than one producing 3%. The scale uses square root of "
                "percentage for visual clarity."
            ),
        },
    ],
}
