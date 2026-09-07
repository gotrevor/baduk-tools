"""The config layer.  Its one promise: never silently run the wrong tournament."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BIN, load_tool

import tdconfig


def test_reads_every_section(config_file):
    cfg = tdconfig.load(str(config_file))
    assert cfg.tournament == "FixtureOpen"
    assert cfg.event_title == "Fixture Open 2026"
    assert cfg.newest_xml().name == "FixtureOpen.xml"
    assert cfg.page_url("crosstab-r1.html") == "https://example.invalid/event/crosstab-r1.html"
    assert cfg.index_md.name == "index.md"


def test_explicit_config_that_does_not_exist_is_fatal(tmp_path):
    """The regression that matters: it used to fall through to the next candidate."""
    with pytest.raises(SystemExit) as e:
        tdconfig.load(str(tmp_path / "absent.toml"))
    assert "--config" in str(e.value) and "does not exist" in str(e.value)


def test_env_config_that_does_not_exist_is_fatal(tmp_path, monkeypatch):
    monkeypatch.setenv("BADUK_TOURNAMENT_CONFIG", str(tmp_path / "absent.toml"))
    with pytest.raises(SystemExit) as e:
        tdconfig.load()
    assert "BADUK_TOURNAMENT_CONFIG" in str(e.value)


def test_env_config_does_not_shadow_an_explicit_one(config_file, tmp_path, monkeypatch):
    monkeypatch.setenv("BADUK_TOURNAMENT_CONFIG", str(tmp_path / "absent.toml"))
    assert tdconfig.load(str(config_file)).tournament == "FixtureOpen"


def test_cwd_config_beats_the_user_one(config_file, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BADUK_TOURNAMENT_CONFIG", raising=False)
    assert tdconfig.load().source == config_file


def test_no_config_anywhere_names_what_it_tried(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BADUK_TOURNAMENT_CONFIG", raising=False)
    monkeypatch.setattr(tdconfig, "USER_CONFIG", tmp_path / "nope" / "tournament.toml")
    with pytest.raises(SystemExit) as e:
        tdconfig.load()
    msg = str(e.value)
    assert str(tmp_path / "tournament.toml") in msg
    assert "AGENTS.md" in msg, "the failure must point at the agent setup path"


def test_missing_key_names_the_key(tmp_path):
    path = tmp_path / "t.toml"
    path.write_text('[opengotha]\nhome = "/tmp"\n')
    cfg = tdconfig.load(str(path))
    with pytest.raises(SystemExit) as e:
        cfg.site_dir
    assert "[site] dir" in str(e.value)


def test_paths_expand_tilde(tmp_path):
    path = tmp_path / "t.toml"
    path.write_text('[tdlist]\npath = "~/some/list.tsv"\n')
    assert tdconfig.load(str(path)).tdlist == Path.home() / "some" / "list.tsv"


def test_deploy_runs_the_configured_command_with_repo_relative_paths(config_file, site):
    cfg = tdconfig.load(str(config_file))
    page = site / "event" / "crosstab-r1.html"
    page.write_text("x")
    assert cfg.deploy([page, cfg.index_md]) == 0
    assert (site / "deployed.txt").read_text().split() == [
        "event/crosstab-r1.html", "event/index.md"]
