from __future__ import annotations

import pytest

import peven.__main__ as cli


def test_001(monkeypatch) -> None:
    """python -m peven setup dispatches to setup with the --yes flag."""
    calls = []
    monkeypatch.setattr(cli, "setup", lambda assumeYes: calls.append(assumeYes) or 0)

    assert cli.main(["setup"]) == 0
    assert cli.main(["setup", "--yes"]) == 0
    assert calls == [False, True]


def test_002() -> None:
    """The CLI requires a command and rejects unknown ones."""
    with pytest.raises(SystemExit):
        cli.main([])
    with pytest.raises(SystemExit):
        cli.main(["doctor"])


def test_003(monkeypatch, tmp_path) -> None:
    """findJulia prefers PATH, falls back to juliaup's home, else None.

    The juliaup fallback exists because a fresh juliaup install lands in
    ~/.juliaup/bin before the user's PATH picks it up in a new shell.
    """
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/julia")
    assert cli.findJulia() == "/usr/bin/julia"

    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path)
    assert cli.findJulia() is None

    juliaup = tmp_path / ".juliaup" / "bin"
    juliaup.mkdir(parents=True)
    (juliaup / "julia").touch()
    assert cli.findJulia() == str(juliaup / "julia")


def test_004() -> None:
    """The transport pin is a plain version string for Pkg.add."""
    assert type(cli.transportVersion) is str
    assert cli.transportVersion
