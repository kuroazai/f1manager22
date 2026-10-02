"""Driver profiles."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from f1manager22.cli import BUNDLED_PROFILES
from f1manager22.drivers import (
    DriverStat,
    driver_code,
    load_profiles,
    parse_profile,
    suspicious_codes,
)

GOOD = {
    "driver": "Lewis Hamilton", "ID": "HAM",
    "cornering": 96, "braking": 95, "control": 97, "smoothness": 97,
    "adaptability": 94, "overtaking": 95, "defence": 92, "acceleration": 96,
    "accuracy": 94,
}


def write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_the_shipped_profiles_parse() -> None:
    """If the bundled file stops being valid, this should fail."""
    profiles = load_profiles(BUNDLED_PROFILES)
    assert len(profiles) == 20
    assert all(len(p.ratings) == len(DriverStat) for p in profiles)


def test_the_shipped_profiles_all_use_a_three_letter_code() -> None:
    """The file shipped with Mick Schumacher as "Schumacher", which becomes
    `[DriverCode_Schumacher]` and matches no driver in any save."""
    assert suspicious_codes(load_profiles(BUNDLED_PROFILES)) == []


def test_driver_code_matches_the_games_format() -> None:
    assert driver_code("HAM") == "[DriverCode_Ham]"
    assert driver_code("ham") == "[DriverCode_Ham]"
    assert driver_code("  VER  ") == "[DriverCode_Ver]"


def test_an_empty_code_is_refused() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        driver_code("  ")


def test_a_profile_missing_a_stat_is_refused() -> None:
    """Half a driver's ratings applied is worse than none: it looks fine and
    races wrong."""
    incomplete = {k: v for k, v in GOOD.items() if k != "braking"}
    with pytest.raises(ValueError, match="braking"):
        parse_profile(incomplete)


def test_a_non_numeric_rating_is_refused() -> None:
    with pytest.raises(ValueError, match="non-numeric"):
        parse_profile({**GOOD, "cornering": "very good"})


@pytest.mark.parametrize("value", [0, -5, 101, 1000])
def test_an_out_of_range_rating_is_refused(value: int) -> None:
    with pytest.raises(ValueError, match="outside"):
        parse_profile({**GOOD, "cornering": value})


def test_a_profile_without_a_name_or_id_is_refused() -> None:
    with pytest.raises(ValueError, match="'driver' and 'ID'"):
        parse_profile({**GOOD, "ID": ""})


def test_duplicate_profiles_are_refused(tmp_path: Path) -> None:
    """Two profiles for one driver means the second quietly wins."""
    path = write(tmp_path / "dupes.json", [GOOD, GOOD])
    with pytest.raises(ValueError, match="more than one profile"):
        load_profiles(path)


def test_a_missing_file_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_profiles(tmp_path / "absent.json")


def test_invalid_json_says_so(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_profiles(path)


def test_a_json_object_instead_of_a_list_says_so(tmp_path: Path) -> None:
    path = write(tmp_path / "object.json", GOOD)
    with pytest.raises(ValueError, match="list of driver profiles"):
        load_profiles(path)


def test_average_summarises_a_driver() -> None:
    profile = parse_profile(GOOD)
    assert 90 < profile.average < 100
    assert profile.save_code == "[DriverCode_Ham]"
