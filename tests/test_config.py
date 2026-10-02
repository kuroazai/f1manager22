"""Settings, and the --save argument the original ignored."""
from __future__ import annotations

from pathlib import Path

import pytest

from f1manager22.config import ConfigError, Settings, load_env_file


@pytest.fixture
def save_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "My Games" / "F1 Manager 2022"
    folder.mkdir(parents=True)
    (folder / "autosave.sav").write_bytes(b"x")
    (folder / "career 2024.sav").write_bytes(b"y")
    return folder


def test_nothing_configured_says_what_to_set() -> None:
    settings = Settings()
    with pytest.raises(ConfigError, match="F1M22_SAVE_FOLDER"):
        settings.resolve_save()
    with pytest.raises(ConfigError, match="F1M22_UNPACKER"):
        settings.resolve_unpacker()


def test_the_default_save_is_the_configured_name(save_folder: Path) -> None:
    settings = Settings(save_folder=save_folder)
    assert settings.resolve_save() == save_folder / "autosave.sav"


def test_a_bare_name_resolves_inside_the_save_folder(save_folder: Path) -> None:
    """Which is how people use it: "that other save", not a full path.

    In the original, `--save` was declared, documented in the README, and then
    never read. The path was hardcoded a few lines further down, so choosing a
    different save silently did nothing.
    """
    settings = Settings(save_folder=save_folder)
    assert settings.resolve_save("career 2024.sav") == save_folder / "career 2024.sav"


def test_a_full_path_is_used_as_given(save_folder: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "backup copy" / "old.sav"
    settings = Settings(save_folder=save_folder)
    assert settings.resolve_save(str(elsewhere)) == elsewhere


def test_a_full_path_needs_no_configured_folder(tmp_path: Path) -> None:
    """So the tool is usable with one argument and no setup."""
    target = tmp_path / "somewhere" / "autosave.sav"
    assert Settings().resolve_save(str(target)) == target


def test_an_explicit_unpacker_overrides_the_configured_one(tmp_path: Path) -> None:
    settings = Settings(unpacker=tmp_path / "configured.py")
    assert settings.resolve_unpacker(str(tmp_path / "chosen.py")) == (
        tmp_path / "chosen.py"
    )


def test_env_file_is_read(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        f"F1M22_SAVE_FOLDER={tmp_path}\n"
        'F1M22_SAVE_NAME="career.sav"\n'
        "NOT_A_PAIR\n",
        encoding="utf-8",
    )
    for key in ("F1M22_SAVE_FOLDER", "F1M22_SAVE_NAME", "F1M22_UNPACKER",
                "F1M22_PROFILES"):
        monkeypatch.delenv(key, raising=False)

    loaded = load_env_file(str(env))
    assert loaded["F1M22_SAVE_NAME"] == "career.sav"  # quotes stripped
    assert "NOT_A_PAIR" not in loaded

    settings = Settings.from_env(env_file=None)
    assert settings.save_name == "career.sav"


def test_the_real_environment_beats_an_env_file(tmp_path: Path, monkeypatch) -> None:
    """A tracked config file was the original's approach, and it meant your own
    path conflicted on every pull. The environment has to win."""
    env = tmp_path / ".env"
    env.write_text("F1M22_SAVE_NAME=from-file.sav\n", encoding="utf-8")
    monkeypatch.setenv("F1M22_SAVE_NAME", "from-environment.sav")

    load_env_file(str(env))
    assert Settings.from_env(env_file=None).save_name == "from-environment.sav"


def test_a_missing_env_file_is_fine(tmp_path: Path) -> None:
    assert load_env_file(str(tmp_path / "absent.env")) == {}


def test_describe_flags_a_path_that_is_not_there(tmp_path: Path) -> None:
    settings = Settings(save_folder=tmp_path / "nope", unpacker=tmp_path / "gone.py")
    described = settings.describe()
    assert described.count("MISSING") == 2


def test_describe_reports_a_valid_setup(save_folder: Path, tmp_path: Path) -> None:
    unpacker = tmp_path / "script.py"
    unpacker.write_text("", encoding="utf-8")
    described = Settings(save_folder=save_folder, unpacker=unpacker).describe()
    assert "MISSING" not in described
    assert "found" in described
