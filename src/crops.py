"""Crop code registry, technology levels, variables, and filename parser.

This is a pure data module — no I/O, no imports from other src modules.
Source: MapSPAM 2020 V2r0 GeoTIFF filenames + mapspamc R package documentation.
"""

import re
from pathlib import PurePosixPath

CROPS: dict[str, dict[str, str]] = {
    # Cereals
    "WHEA": {"name": "Wheat", "category": "Cereals"},
    "RICE": {"name": "Rice", "category": "Cereals"},
    "MAIZ": {"name": "Maize", "category": "Cereals"},
    "BARL": {"name": "Barley", "category": "Cereals"},
    "PMIL": {"name": "Pearl Millet", "category": "Cereals"},
    "MILL": {"name": "Small Millet", "category": "Cereals"},
    "SORG": {"name": "Sorghum", "category": "Cereals"},
    "OCER": {"name": "Other Cereals", "category": "Cereals"},
    # Roots & Tubers
    "POTA": {"name": "Potato", "category": "Roots & Tubers"},
    "SWPO": {"name": "Sweet Potato", "category": "Roots & Tubers"},
    "YAMS": {"name": "Yams", "category": "Roots & Tubers"},
    "CASS": {"name": "Cassava", "category": "Roots & Tubers"},
    "ORTS": {"name": "Other Roots", "category": "Roots & Tubers"},
    # Pulses
    "BEAN": {"name": "Bean", "category": "Pulses"},
    "CHIC": {"name": "Chickpea", "category": "Pulses"},
    "COWP": {"name": "Cowpea", "category": "Pulses"},
    "PIGE": {"name": "Pigeon Pea", "category": "Pulses"},
    "LENT": {"name": "Lentil", "category": "Pulses"},
    "OPUL": {"name": "Other Pulses", "category": "Pulses"},
    # Oil Crops
    "SOYB": {"name": "Soybean", "category": "Oil Crops"},
    "GROU": {"name": "Groundnut", "category": "Oil Crops"},
    "CNUT": {"name": "Coconut", "category": "Oil Crops"},
    "OILP": {"name": "Oil Palm", "category": "Oil Crops"},
    "SUNF": {"name": "Sunflower", "category": "Oil Crops"},
    "RAPE": {"name": "Rapeseed", "category": "Oil Crops"},
    "SESA": {"name": "Sesame Seed", "category": "Oil Crops"},
    "OOIL": {"name": "Other Oil Crops", "category": "Oil Crops"},
    # Sugar Crops
    "SUGC": {"name": "Sugarcane", "category": "Sugar Crops"},
    "SUGB": {"name": "Sugarbeet", "category": "Sugar Crops"},
    # Fibres
    "COTT": {"name": "Cotton", "category": "Fibres"},
    "OFIB": {"name": "Other Fibre Crops", "category": "Fibres"},
    # Stimulants
    "COFF": {"name": "Coffee", "category": "Stimulants"},
    "RCOF": {"name": "Robusta Coffee", "category": "Stimulants"},
    "COCO": {"name": "Cocoa", "category": "Stimulants"},
    "TEAS": {"name": "Tea", "category": "Stimulants"},
    "TOBA": {"name": "Tobacco", "category": "Stimulants"},
    # Fruits
    "BANA": {"name": "Banana", "category": "Fruits"},
    "PLNT": {"name": "Plantain", "category": "Fruits"},
    "TROF": {"name": "Tropical Fruit", "category": "Fruits"},
    "TEMF": {"name": "Temperate Fruit", "category": "Fruits"},
    "CITR": {"name": "Citrus", "category": "Fruits"},
    # Vegetables
    "VEGE": {"name": "Vegetables", "category": "Vegetables"},
    "ONIO": {"name": "Onion", "category": "Vegetables"},
    "TOMA": {"name": "Tomato", "category": "Vegetables"},
    # Other
    "RUBB": {"name": "Rubber", "category": "Other"},
    "REST": {"name": "Rest of Crops", "category": "Other"},
}

TECH_LEVELS: dict[str, str] = {
    "A": "All systems combined",
    "I": "Irrigated",
    "R": "Rainfed",
}

VARIABLES: dict[str, dict[str, str]] = {
    "P": {"name": "Production", "unit": "metric tonnes"},
    "H": {"name": "Harvested Area", "unit": "hectares"},
    "A": {"name": "Physical Area", "unit": "hectares"},
    "Y": {"name": "Yield", "unit": "kg/ha"},
}

_FILENAME_PATTERN = re.compile(r"spam\d{4}_V\dr\d_global_([PHAY])_([A-Z]{4})_([AIR])\.tif$")


def parse_filename(filename: str) -> tuple[str, str, str]:
    """Extract (variable, crop_code, tech_level) from a SPAM GeoTIFF filename.

    Handles both bare filenames and paths with directory prefixes.
    Raises ValueError for unrecognized filenames, crop codes, or tech levels.
    """
    basename = PurePosixPath(filename).name
    match = _FILENAME_PATTERN.match(basename)
    if not match:
        raise ValueError(f"Unrecognized SPAM filename: {filename}")

    variable, crop_code, tech_level = match.groups()

    if variable not in VARIABLES:
        raise ValueError(f"Unknown variable code: {variable}")
    if crop_code not in CROPS:
        raise ValueError(f"Unknown crop code: {crop_code}")
    if tech_level not in TECH_LEVELS:
        raise ValueError(f"Unknown tech level: {tech_level}")

    return variable, crop_code, tech_level
