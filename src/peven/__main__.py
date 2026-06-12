"""Command line entry point: python -m peven setup."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


transportVersion = "0.1"

juliaupCommand = "curl -fsSL https://install.julialang.org | sh -s -- --yes"


def findJulia() -> str | None:
    julia = shutil.which("julia")
    if julia is not None:
        return julia
    juliaup = Path.home() / ".juliaup" / "bin" / "julia"
    return str(juliaup) if juliaup.exists() else None


def setup(assumeYes: bool) -> int:
    julia = findJulia()
    if julia is None:
        if not assumeYes:
            reply = input("julia not found — install it via juliaup? [Y/n] ")
            if reply.strip().lower() in ("n", "no"):
                print("install julia via https://julialang.org/install/ and rerun")
                return 1
        subprocess.run(juliaupCommand, shell=True, check=True)
        julia = findJulia()
        if julia is None:
            print("juliaup finished but julia was not found; open a new shell and rerun")
            return 1

    add = (
        'using Pkg; Pkg.activate("peven"; shared=true); '
        f'Pkg.add(name="PevenTransport", version="{transportVersion}")'
    )
    subprocess.run([julia, "-e", add], check=True)
    print("peven setup complete — peven.gateway() is ready")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="peven")
    commands = parser.add_subparsers(dest="command", required=True)
    setupParser = commands.add_parser("setup", help="install the Julia side of peven")
    setupParser.add_argument("--yes", action="store_true", help="run non-interactively")
    args = parser.parse_args(argv)
    return setup(args.yes)


if __name__ == "__main__":
    sys.exit(main())
