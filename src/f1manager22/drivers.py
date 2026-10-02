"""Driver ratings from a profile file.

The repository ships `profiles/F1_22.json`, twenty drivers rated at their career
peak. Swap the numbers and you get a different grid; the format is deliberately
plain so it can be edited by hand.

    [{"driver": "Lewis Hamilton", "ID": "HAM", "cornering": 96, ...}]
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .enums import DriverStat

#: How the game spells a driver code in `Staff_DriverData.DriverCode`.
DRIVER_CODE_TEMPLATE = "[DriverCode_{code}]"
#: Ratings outside this range are rejected rather than clamped silently.
RATING_RANGE = (1, 100)


def driver_code(code: str) -> str:
    """"HAM" -> "[DriverCode_Ham]", which is the game's own form."""
    cleaned = (code or "").strip()
    if not cleaned:
        raise ValueError("a driver profile needs a non-empty ID")
    return DRIVER_CODE_TEMPLATE.format(code=cleaned.lower().capitalize())


@dataclass(frozen=True)
class DriverProfile:
    name: str
    code: str
    ratings: dict[DriverStat, int]

    @property
    def save_code(self) -> str:
        return driver_code(self.code)

    @property
    def average(self) -> float:
        return round(sum(self.ratings.values()) / len(self.ratings), 1)


def parse_profile(entry: dict) -> DriverProfile:
    """One profile, with the errors named.

    A profile missing a stat is rejected rather than partially applied. Half a
    driver's ratings updated is worse than none, because the result looks fine
    and races wrong.
    """
    name = str(entry.get("driver", "")).strip()
    code = str(entry.get("ID", "")).strip()
    if not name or not code:
        raise ValueError(f"a profile needs both 'driver' and 'ID': {entry!r}")

    ratings: dict[DriverStat, int] = {}
    low, high = RATING_RANGE
    for stat in DriverStat:
        key = stat.name.lower()
        if key not in entry:
            raise ValueError(f"{name} ({code}) has no {key!r} rating")
        try:
            value = int(entry[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{name} ({code}) has a non-numeric {key!r}: {entry[key]!r}"
            ) from exc
        if not low <= value <= high:
            raise ValueError(
                f"{name} ({code}) has {key}={value}, outside {low}-{high}"
            )
        ratings[stat] = value

    return DriverProfile(name=name, code=code, ratings=ratings)


def load_profiles(path: str | Path) -> list[DriverProfile]:
    """Every profile in a file, or an error naming the first bad one."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"no driver profile file at {source}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source.name} is not valid JSON: {exc}") from exc

    if not isinstance(payload, list):
        raise ValueError(f"{source.name} should hold a list of driver profiles")

    profiles = [parse_profile(entry) for entry in payload]

    duplicates = _duplicate_codes(profiles)
    if duplicates:
        # Two profiles for one driver means whichever is applied second wins,
        # quietly. Better to say so.
        raise ValueError(
            f"{source.name} has more than one profile for: " + ", ".join(duplicates)
        )
    return profiles


def _duplicate_codes(profiles: list[DriverProfile]) -> list[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for profile in profiles:
        if profile.code in seen:
            repeated.add(profile.code)
        seen.add(profile.code)
    return sorted(repeated)


#: Every driver code in the game is the three-letter FIA abbreviation.
CODE_LENGTH = 3


def suspicious_codes(profiles: list[DriverProfile]) -> list[str]:
    """Profiles whose ID is not a three-letter code.

    Not an error, because a future game version could use something else, but
    worth saying out loud. The shipped file had Mick Schumacher as
    "Schumacher" rather than "MSC", which becomes `[DriverCode_Schumacher]` and
    matches no driver. In the original that reached `.fetchone()[0]` and ended
    the whole run with `TypeError: 'NoneType' object is not subscriptable`, so
    the driver step could never complete.
    """
    return [
        f"{profile.name} (ID {profile.code!r})"
        for profile in profiles
        if len(profile.code) != CODE_LENGTH or not profile.code.isalpha()
    ]


def describe(profiles: list[DriverProfile], limit: int = 10) -> str:
    """The strongest drivers in a profile set, as a table."""
    ranked = sorted(profiles, key=lambda p: -p.average)
    lines = [f"{len(profiles)} driver profile(s)", f"{'driver':<22}{'avg':>6}"]
    lines += [f"{p.name:<22}{p.average:>6.1f}" for p in ranked[:limit]]
    if len(ranked) > limit:
        lines.append(f"... and {len(ranked) - limit} more")

    odd = suspicious_codes(profiles)
    if odd:
        lines.append(f"{len(odd)} ID(s) are not a three-letter code: "
                     + ", ".join(odd))
    return "\n".join(lines)
