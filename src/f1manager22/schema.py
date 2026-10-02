"""The tables and columns this tool touches, declared once.

Two uses. It builds the synthetic save the test suite runs against, so the
operations can be exercised without owning the game. And `f1m22 check` compares
it against a real save, which turns "it silently changed nothing" into a
specific list of what is missing.

This is the schema as the code uses it, derived from the queries themselves. It
is not a complete description of an F1 Manager 2022 save, which has well over a
hundred tables. Anything not listed here is not touched.
"""
from __future__ import annotations

#: table -> {column: SQLite type}. Primary keys are noted in PRIMARY_KEYS.
TABLES: dict[str, dict[str, str]] = {
    "Tyres": {
        "Type": "INTEGER",
        "Grip": "REAL",
        "Durability": "REAL",
        "TempIncRate": "REAL",
        "TempDecRate": "REAL",
        "MinExtremeWear": "REAL",
        "MaxExtremeWear": "REAL",
        "MinOptimalWear": "REAL",
        "MaxOptimalWear": "REAL",
        "MinOptimalGrip": "REAL",
        "MaxOptimalGrip": "REAL",
        "MinExtremeGrip": "REAL",
        "MaxExtremeGrip": "REAL",
    },
    "Parts_RaceSimConstants": {
        "DirtyAirLowSpeedMultiplier": "REAL",
        "DirtyAirMediumSpeedMultiplier": "REAL",
        "DirtyAirHighSpeedMultiplier": "REAL",
        "DirtyAirStraightSpeedMultiplier": "REAL",
        "MaxDRSTopSpeedMultiplier": "REAL",
        "MaxDRSAccelerationMultiplier": "REAL",
        "MinDRSAccelerationMultiplier": "REAL",
    },
    "Staff_DriverData": {
        "StaffID": "INTEGER",
        "DriverCode": "TEXT",
        "Improvability": "INTEGER",
        "Aggression": "INTEGER",
    },
    "Staff_PerformanceStats": {
        "StaffID": "INTEGER",
        "StatID": "INTEGER",
        "Val": "REAL",
    },
    "Finance_TeamBalance": {
        "TeamID": "INTEGER",
        "Balance": "INTEGER",
    },
    "Parts_Enum_EngineManufacturers": {
        "ManufacturerID": "INTEGER",
        "EngineDesignID": "INTEGER",
        "ErsDesignID": "INTEGER",
        "GearboxDesignID": "INTEGER",
    },
    "Parts_DesignStatValues": {
        "DesignID": "INTEGER",
        "StatID": "INTEGER",
        "UnitValue": "REAL",
        "Value": "REAL",
    },
    "Races_TeamPerformance": {
        "TeamID": "INTEGER",
        "TrackID": "INTEGER",
        "Straights": "REAL",
        "SlowCorners": "REAL",
        "MediumCorners": "REAL",
        "FastCorners": "REAL",
    },
    "Staff_PitCrew_PerformanceStats": {
        "StaffID": "INTEGER",
        "StatID": "INTEGER",
        "Val": "REAL",
    },
    "Parts_TeamExpertise": {
        "TeamID": "INTEGER",
        "PartType": "INTEGER",
        "Expertise": "INTEGER",
        "SeasonStartExpertise": "INTEGER",
    },
}

PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "Tyres": ("Type",),
    "Staff_DriverData": ("StaffID",),
    "Staff_PerformanceStats": ("StaffID", "StatID"),
    "Finance_TeamBalance": ("TeamID",),
    "Parts_Enum_EngineManufacturers": ("ManufacturerID",),
    "Parts_DesignStatValues": ("DesignID", "StatID"),
    "Races_TeamPerformance": ("TeamID", "TrackID"),
    "Staff_PitCrew_PerformanceStats": ("StaffID", "StatID"),
    "Parts_TeamExpertise": ("TeamID", "PartType"),
}


def create_statements() -> list[str]:
    """CREATE TABLE for every table above."""
    statements = []
    for table, columns in TABLES.items():
        definitions = [f'"{name}" {kind}' for name, kind in columns.items()]
        keys = PRIMARY_KEYS.get(table)
        if keys:
            definitions.append(
                "PRIMARY KEY (" + ", ".join(f'"{k}"' for k in keys) + ")"
            )
        statements.append(
            f'CREATE TABLE IF NOT EXISTS "{table}" (' + ", ".join(definitions) + ")"
        )
    return statements


def differences(present: dict[str, list[str]]) -> list[str]:
    """What a real save is missing against this schema.

    `present` is table -> columns, as read from the save. Returns one line per
    problem, which is more use than failing on the first.
    """
    problems = []
    for table, columns in TABLES.items():
        if table not in present:
            problems.append(f"missing table: {table}")
            continue
        absent = sorted(set(columns) - set(present[table]))
        if absent:
            problems.append(f"{table} is missing column(s): {', '.join(absent)}")
    return problems
