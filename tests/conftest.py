"""A synthetic save, so the operations can be tested without owning the game.

An F1 Manager 2022 save cannot go in the repository. It is tens of megabytes of
someone's career and it belongs to whoever played it. So the fixture builds a
SQLite database from `f1manager22.schema`, which is the schema as the queries
themselves use it, populated with plausible stock values.

What this proves and what it does not: it proves every statement is valid SQL,
targets columns that exist, matches the rows it intends to, and leaves the
values it claims. It does not prove the column names match a real 2022 save,
because that can only be checked against one. `f1m22 check` is the tool for
that, and it exists for exactly this reason.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from f1manager22.db import SaveDatabase
from f1manager22.enums import DriverStat, TyreCompound
from f1manager22.operations import Plan
from f1manager22.schema import create_statements

#: The grid, matching the bundled driver profiles.
DRIVER_CODES = [
    "HAM", "VER", "LEC", "ALO", "NOR", "RUS", "SAI", "PER", "OCO", "GAS",
    "BOT", "ALB", "TSU", "STR", "MAG", "RIC", "ZHO", "MSC", "LAT", "VET",
]
TEAM_COUNT = 10
TRACK_COUNT = 22
DESIGN_COUNT = 12
#: Stock values, deliberately flat, which is the problem the mod addresses: all
#: three dry compounds perform almost identically.
STOCK_TYRE = {
    TyreCompound.SOFT: (1.00, 1.00),
    TyreCompound.MEDIUM: (0.99, 1.02),
    TyreCompound.HARD: (0.98, 1.04),
    TyreCompound.INTERMEDIATE: (0.90, 1.10),
    TyreCompound.WET: (0.85, 1.20),
}


def build_save(path: Path, *, drivers: list[str] | None = None) -> Path:
    """Write a synthetic save database and return its path."""
    codes = DRIVER_CODES if drivers is None else drivers
    connection = sqlite3.connect(str(path))
    try:
        for statement in create_statements():
            connection.execute(statement)

        for compound, (grip, durability) in STOCK_TYRE.items():
            connection.execute(
                "INSERT INTO Tyres (Type, Grip, Durability, TempIncRate, TempDecRate,"
                " MinExtremeWear, MaxExtremeWear, MinOptimalWear, MaxOptimalWear,"
                " MinOptimalGrip, MaxOptimalGrip, MinExtremeGrip, MaxExtremeGrip)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (int(compound), grip, durability, 1.0, 0.1,
                 0.2, 0.5, 0.05, 0.2, 0.5, 0.7, 0.3, 0.5),
            )

        connection.execute(
            "INSERT INTO Parts_RaceSimConstants (DirtyAirLowSpeedMultiplier,"
            " DirtyAirMediumSpeedMultiplier, DirtyAirHighSpeedMultiplier,"
            " DirtyAirStraightSpeedMultiplier, MaxDRSTopSpeedMultiplier,"
            " MaxDRSAccelerationMultiplier, MinDRSAccelerationMultiplier)"
            " VALUES (?,?,?,?,?,?,?)",
            (0.98, 0.98, 0.98, 1.0, 1.01, 1.01, 0.95),
        )

        for index, code in enumerate(codes, start=1):
            connection.execute(
                "INSERT INTO Staff_DriverData (StaffID, DriverCode, Improvability,"
                " Aggression) VALUES (?,?,?,?)",
                (index, f"[DriverCode_{code.lower().capitalize()}]", 50, 50),
            )
            for stat in DriverStat:
                connection.execute(
                    "INSERT INTO Staff_PerformanceStats (StaffID, StatID, Val)"
                    " VALUES (?,?,?)",
                    (index, int(stat), 70.0),
                )

        for team in range(1, TEAM_COUNT + 1):
            connection.execute(
                "INSERT INTO Finance_TeamBalance (TeamID, Balance) VALUES (?,?)",
                (team, 100_000_000 + team * 1_000_000),
            )
            for part_type in range(4):
                connection.execute(
                    "INSERT INTO Parts_TeamExpertise (TeamID, PartType, Expertise,"
                    " SeasonStartExpertise) VALUES (?,?,?,?)",
                    (team, part_type, 100 * team, 100 * team),
                )
            for track in range(1, TRACK_COUNT + 1):
                connection.execute(
                    "INSERT INTO Races_TeamPerformance (TeamID, TrackID, Straights,"
                    " SlowCorners, MediumCorners, FastCorners) VALUES (?,?,?,?,?,?)",
                    (team, track, 0.9 + team / 100, 0.9, 0.95, 1.05),
                )

        # Four manufacturers, each with three designs, all distinct.
        for manufacturer in range(1, 5):
            base = manufacturer * 3
            connection.execute(
                "INSERT INTO Parts_Enum_EngineManufacturers (ManufacturerID,"
                " EngineDesignID, ErsDesignID, GearboxDesignID) VALUES (?,?,?,?)",
                (manufacturer, base - 2, base - 1, base),
            )

        for design in range(1, DESIGN_COUNT + 1):
            for stat in range(3):
                connection.execute(
                    "INSERT INTO Parts_DesignStatValues (DesignID, StatID, UnitValue,"
                    " Value) VALUES (?,?,?,?)",
                    (design, stat, 10.0 + design, (10.0 + design) * 10),
                )

        for crew in range(1, 21):
            for stat in range(3):
                connection.execute(
                    "INSERT INTO Staff_PitCrew_PerformanceStats (StaffID, StatID, Val)"
                    " VALUES (?,?,?)",
                    (crew, stat, 60.0),
                )

        connection.commit()
    finally:
        connection.close()
    return path


@pytest.fixture
def save_path(tmp_path: Path) -> Path:
    return build_save(tmp_path / "main.db")


@pytest.fixture
def database(save_path: Path):
    connection = SaveDatabase(save_path)
    yield connection
    connection.close()


@pytest.fixture
def plan() -> Plan:
    """The real bundled driver profiles, not a stub.

    If the shipped profile file stops parsing, these tests should fail.
    """
    from f1manager22.cli import BUNDLED_PROFILES

    return Plan(profiles_path=BUNDLED_PROFILES)
