"""The game's own identifiers, declared once.

These are magic numbers from the save database. Spelling them out here means a
query that uses the wrong one is a visible mistake rather than an integer that
happens to be in range.
"""
from __future__ import annotations

from enum import Enum, IntEnum


class DriverStat(IntEnum):
    """Rows in `Staff_PerformanceStats`, keyed by `StatID`.

    The gap at 0 and 1 is the game's, not a mistake here: those IDs are used by
    staff who are not drivers.
    """

    CORNERING = 2
    BRAKING = 3
    CONTROL = 4
    SMOOTHNESS = 5
    ADAPTABILITY = 6
    OVERTAKING = 7
    DEFENCE = 8
    ACCELERATION = 9
    ACCURACY = 10

    @classmethod
    def from_name(cls, name: str) -> DriverStat:
        """Look one up from a driver-profile key such as "cornering"."""
        try:
            return cls[name.strip().upper()]
        except KeyError as exc:
            raise KeyError(
                f"{name!r} is not a driver stat; expected one of: "
                + ", ".join(s.name.lower() for s in cls)
            ) from exc


class TyreCompound(IntEnum):
    """Rows in `Tyres`, keyed by `Type`.

    Ordered softest to hardest, which is the order the game uses and the reason
    grip descends while durability ascends across the range.
    """

    SOFT = 0
    MEDIUM = 1
    HARD = 2
    INTERMEDIATE = 3
    WET = 4

    @property
    def is_slick(self) -> bool:
        return self in {TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD}


#: The dry compounds, in the order a race weekend uses them. Several
#: calculations only make sense across these three, because an intermediate is
#: not a harder slick.
DRY_COMPOUNDS = (TyreCompound.SOFT, TyreCompound.MEDIUM, TyreCompound.HARD)


class Table(str, Enum):
    """Table names, so a typo is an AttributeError and not an empty result set."""

    TYRES = "Tyres"
    RACE_CONSTANTS = "Parts_RaceSimConstants"
    DRIVERS = "Staff_DriverData"
    DRIVER_STATS = "Staff_PerformanceStats"
    TEAM_BALANCE = "Finance_TeamBalance"
    ENGINE_MANUFACTURERS = "Parts_Enum_EngineManufacturers"
    DESIGN_STATS = "Parts_DesignStatValues"
    TRACK_PERFORMANCE = "Races_TeamPerformance"
    PIT_CREW_STATS = "Staff_PitCrew_PerformanceStats"
    TEAM_EXPERTISE = "Parts_TeamExpertise"

    def __str__(self) -> str:
        return self.value
