"""The command line, called directly rather than through a subprocess."""
from __future__ import annotations

from pathlib import Path

import pytest

from f1manager22.cli import build_parser, main


def test_every_subcommand_has_a_handler() -> None:
    """A subcommand with no handler fails with AttributeError at runtime, which
    is a poor way to find a typo in the parser wiring."""
    parser = build_parser()
    actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    assert actions

    for action in actions:
        for name, sub in action.choices.items():
            assert sub.get_default("handler") is not None, f"{name} has no handler"


def test_preview_works_with_nothing_configured(capsys, tmp_path: Path) -> None:
    """The one command that should always work, so you can see the numbers
    before deciding whether to install anything."""
    assert main(["--env-file", str(tmp_path / "absent.env"), "preview"]) == 0
    printed = capsys.readouterr().out
    assert "soft" in printed
    assert "hard" in printed
    assert "driver profile" in printed


def test_preview_honours_a_preset(capsys, tmp_path: Path) -> None:
    main(["--env-file", str(tmp_path / "absent.env"), "preview", "--preset", "racing"])
    printed = capsys.readouterr().out
    assert "tyres" in printed
    assert "cash-infusion" not in printed


def test_preview_rejects_an_unknown_preset(capsys, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--env-file", str(tmp_path / "absent.env"),
              "preview", "--preset", "nonsense"])


def test_preview_rejects_an_unknown_operation(capsys, tmp_path: Path) -> None:
    code = main(["--env-file", str(tmp_path / "absent.env"),
                 "preview", "--only", "nonsense"])
    assert code == 1
    assert "unknown operation" in capsys.readouterr().out


def test_preview_refuses_nonsense_tuning(capsys, tmp_path: Path) -> None:
    """Validation happens before anything is written, not after."""
    with pytest.raises(ValueError, match="under base_grip"):
        main(["--env-file", str(tmp_path / "absent.env"),
              "preview", "--grip-spread", "5"])


def test_config_reports_the_wiring(capsys, tmp_path: Path) -> None:
    assert main(["--env-file", str(tmp_path / "absent.env"), "config"]) == 0
    printed = capsys.readouterr().out
    assert "save folder" in printed
    assert "unpacker" in printed


def test_apply_without_configuration_explains_itself(capsys, tmp_path: Path) -> None:
    code = main(["--env-file", str(tmp_path / "absent.env"), "apply", "--dry-run"])
    assert code == 1
    assert "F1M22_SAVE_FOLDER" in capsys.readouterr().out


def test_backups_without_configuration_explains_itself(capsys, tmp_path: Path) -> None:
    code = main(["--env-file", str(tmp_path / "absent.env"), "backups"])
    assert code == 1
    assert "configured" in capsys.readouterr().out


def test_an_unknown_command_exits(capsys) -> None:
    with pytest.raises(SystemExit):
        main(["nonsense"])


def test_output_is_ascii(capsys, tmp_path: Path) -> None:
    """A pound sign or an em-dash crashes a legacy Windows console code page,
    and this is a tool people run on Windows."""
    main(["--env-file", str(tmp_path / "absent.env"), "preview"])
    capsys.readouterr().out.encode("ascii")
