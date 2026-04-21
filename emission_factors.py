# ─────────────────────────────────────────────────────────────────────────────
# emission_factors.py
# Emission factor database for SupplierTrace AI
# Sources: DEFRA 2023 Conversion Factors, EPA 2022, CEA India 2023
# Units: kgCO2e per unit (kg, kWh, or tonne-km)
# ─────────────────────────────────────────────────────────────────────────────

EMISSION_FACTORS: dict[str, dict] = {

    # ── Metals ───────────────────────────────────────────────────────────────
    "steel":                {"factor": 1.85,  "unit": "kg",        "label": "Steel (virgin)",        "source": "DEFRA 2023"},
    "steel_recycled":       {"factor": 0.43,  "unit": "kg",        "label": "Steel (recycled)",      "source": "DEFRA 2023"},
    "iron":                 {"factor": 1.91,  "unit": "kg",        "label": "Cast iron",             "source": "DEFRA 2023"},
    "aluminium":            {"factor": 11.5,  "unit": "kg",        "label": "Aluminium (virgin)",    "source": "DEFRA 2023"},
    "aluminium_recycled":   {"factor": 0.62,  "unit": "kg",        "label": "Aluminium (recycled)",  "source": "DEFRA 2023"},
    "copper":               {"factor": 3.85,  "unit": "kg",        "label": "Copper",                "source": "DEFRA 2023"},
    "zinc":                 {"factor": 3.61,  "unit": "kg",        "label": "Zinc",                  "source": "DEFRA 2023"},
    "titanium":             {"factor": 35.0,  "unit": "kg",        "label": "Titanium",              "source": "EPA 2022"},

    # ── Plastics ─────────────────────────────────────────────────────────────
    "plastic_generic":      {"factor": 3.14,  "unit": "kg",        "label": "Plastic (generic)",     "source": "DEFRA 2023"},
    "plastic_pet":          {"factor": 3.48,  "unit": "kg",        "label": "Plastic PET",           "source": "DEFRA 2023"},
    "plastic_hdpe":         {"factor": 1.93,  "unit": "kg",        "label": "Plastic HDPE",          "source": "DEFRA 2023"},
    "plastic_pp":           {"factor": 1.96,  "unit": "kg",        "label": "Plastic PP",            "source": "DEFRA 2023"},

    # ── Textiles ─────────────────────────────────────────────────────────────
    "cotton":               {"factor": 5.89,  "unit": "kg",        "label": "Cotton",                "source": "DEFRA 2023"},
    "polyester":            {"factor": 9.52,  "unit": "kg",        "label": "Polyester",             "source": "DEFRA 2023"},
    "nylon":                {"factor": 7.28,  "unit": "kg",        "label": "Nylon",                 "source": "DEFRA 2023"},
    "wool":                 {"factor": 10.4,  "unit": "kg",        "label": "Wool",                  "source": "DEFRA 2023"},
    "viscose":              {"factor": 3.41,  "unit": "kg",        "label": "Viscose / Rayon",       "source": "DEFRA 2023"},

    # ── Paper & Packaging ────────────────────────────────────────────────────
    "paper":                {"factor": 0.91,  "unit": "kg",        "label": "Paper",                 "source": "DEFRA 2023"},
    "cardboard":            {"factor": 0.72,  "unit": "kg",        "label": "Cardboard",             "source": "DEFRA 2023"},
    "glass":                {"factor": 0.85,  "unit": "kg",        "label": "Glass",                 "source": "DEFRA 2023"},

    # ── Construction ─────────────────────────────────────────────────────────
    "cement":               {"factor": 0.83,  "unit": "kg",        "label": "Cement",                "source": "DEFRA 2023"},
    "concrete":             {"factor": 0.13,  "unit": "kg",        "label": "Concrete",              "source": "DEFRA 2023"},
    "timber_wood":          {"factor": 0.31,  "unit": "kg",        "label": "Timber / Wood",         "source": "DEFRA 2023"},
    "rubber":               {"factor": 2.85,  "unit": "kg",        "label": "Rubber",                "source": "DEFRA 2023"},

    # ── Electronics ──────────────────────────────────────────────────────────
    "electronics_general":  {"factor": 28.5,  "unit": "kg",        "label": "Electronics (general)", "source": "EPA 2022"},
    "battery_lithium":      {"factor": 12.5,  "unit": "kg",        "label": "Lithium battery",       "source": "EPA 2022"},
    "pcb":                  {"factor": 40.0,  "unit": "kg",        "label": "PCB / Circuit board",   "source": "EPA 2022"},

    # ── Transport (per tonne-km) ─────────────────────────────────────────────
    "road_diesel":          {"factor": 0.10,  "unit": "tonne-km",  "label": "Road freight (diesel)", "source": "DEFRA 2023"},
    "road_electric":        {"factor": 0.05,  "unit": "tonne-km",  "label": "Road freight (EV)",     "source": "DEFRA 2023"},
    "sea_freight":          {"factor": 0.016, "unit": "tonne-km",  "label": "Sea freight",           "source": "DEFRA 2023"},
    "air_freight":          {"factor": 1.78,  "unit": "tonne-km",  "label": "Air freight",           "source": "DEFRA 2023"},
    "rail_freight":         {"factor": 0.028, "unit": "tonne-km",  "label": "Rail freight",          "source": "DEFRA 2023"},

    # ── Energy ───────────────────────────────────────────────────────────────
    "electricity_india":    {"factor": 0.82,  "unit": "kWh",       "label": "Grid electricity (IN)", "source": "CEA India 2023"},
    "electricity_uk":       {"factor": 0.23,  "unit": "kWh",       "label": "Grid electricity (UK)", "source": "DEFRA 2023"},
    "electricity_us":       {"factor": 0.38,  "unit": "kWh",       "label": "Grid electricity (US)", "source": "EPA 2022"},
    "natural_gas":          {"factor": 2.04,  "unit": "kg",        "label": "Natural gas",           "source": "DEFRA 2023"},
    "diesel_fuel":          {"factor": 2.68,  "unit": "litre",     "label": "Diesel fuel",           "source": "DEFRA 2023"},

    # ── Fallback ─────────────────────────────────────────────────────────────
    "unknown":              {"factor": 2.0,   "unit": "kg",        "label": "Unknown material",      "source": "Estimated average"},
}

# GHG Protocol Scope 3 category labels
SCOPE3_LABELS: dict[str, str] = {
    "purchased_goods":    "Cat 1 – Purchased goods & services",
    "capital_goods":      "Cat 2 – Capital goods",
    "energy_related":     "Cat 3 – Fuel & energy activities",
    "upstream_transport": "Cat 4 – Upstream transportation",
    "waste":              "Cat 5 – Waste generated in operations",
    "business_travel":    "Cat 6 – Business travel",
    "other":              "Cat 15 – Other",
}

# Material key → valid unit types (for validation)
VALID_UNITS = {
    "tonne-km": ["tonne-km", "tkm"],
    "kWh":      ["kwh", "kwh/unit"],
    "kg":       ["kg", "g", "tonne", "mt", "pieces", "units", "pcs", "litre", "l"],
}

def get_factor(material_key: str) -> dict:
    """Return emission factor dict for a given material key, falling back to 'unknown'."""
    return EMISSION_FACTORS.get(material_key, EMISSION_FACTORS["unknown"])

def calculate_co2e(material_key: str, quantity: float) -> float:
    """Calculate kgCO2e for a given material and quantity."""
    ef = get_factor(material_key)
    return round(quantity * ef["factor"], 4)

def get_all_material_keys() -> list[str]:
    return list(EMISSION_FACTORS.keys())
