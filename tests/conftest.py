"""Shared fixtures.

Everything here is synthetic.  The tournament fixture invents eight players; no
real registrant's name, AGA id or rating appears anywhere in this directory.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "bin"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(BIN))


def load_tool(name: str):
    """Import one of the bin/ executables as a module (they have no .py suffix)."""
    spec = importlib.util.spec_from_loader(
        name.replace("-", "_"),
        importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(BIN / name)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tournament_xml():
    return FIXTURES / "FixtureOpen.xml"


@pytest.fixture
def site(tmp_path):
    """A pretend site repo: repo root with a bin/deploy and a pages directory."""
    repo = tmp_path / "site-repo"
    pages = repo / "event"
    pages.mkdir(parents=True)
    (repo / "bin").mkdir()
    deploy = repo / "bin" / "deploy"
    deploy.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" >> \"$(dirname \"$0\")/../deployed.txt\"\n")
    deploy.chmod(0o755)
    (pages / "index.md").write_text("# Fixture Open 2026\n\nSome prose.\n")
    return repo


@pytest.fixture
def config_file(tmp_path, site, tournament_xml):
    """A valid tournament.toml wired to the fixture tournament and pretend site."""
    og = tmp_path / "OpenGotha"
    (og / "tournamentfiles" / "work").mkdir(parents=True)
    (og / "exportfiles" / "html").mkdir(parents=True)
    (og / "tournamentfiles" / "work" / "FixtureOpen.xml").write_text(
        tournament_xml.read_text())
    tdlist = tmp_path / "tdlist.tsv"
    tdlist.write_text("Aldergate, Rowan\t90001\tFull\t5.5\t6/1/2027\tWMGC\tMA\t0.5\t1/1/2026\n")

    path = tmp_path / "tournament.toml"
    path.write_text(f'''
[opengotha]
home = "{og}"
tournament = "FixtureOpen"

[event]
title = "Fixture Open 2026"
subtitle = "A tournament that does not exist"

[site]
dir = "{site / 'event'}"
repo = "{site}"
url = "https://example.invalid/event/"
deploy = ["bin/deploy"]

[tdlist]
path = "{tdlist}"
''')
    return path
