"""og-doctor is the tool an agent reads to fix a broken setup, so its output is
an interface, not a convenience.  Every check gets driven BOTH ways: a check
that cannot go red is not a check.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import BIN

DOCTOR = BIN / "og-doctor"


def run(config, **env):
    e = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(Path.home())}
    e.update(env)
    return subprocess.run([sys.executable, str(DOCTOR), "--config", str(config)],
                          capture_output=True, text=True, env=e)


def status_of(out: str, name: str) -> str:
    for line in out.splitlines():
        m = re.match(r"(PASS|FAIL|SKIP)\s+(.+?)\s\s+", line)
        if m and m.group(2).strip() == name:
            return m.group(1)
    raise AssertionError(f"no row for {name!r} in:\n{out}")


def break_config(path: Path, key: str, value: str) -> Path:
    """Rewrite one `key = ...` line, so each red case differs by exactly one fact."""
    lines = []
    for line in path.read_text().splitlines():
        stripped = line.split("=")[0].strip()
        lines.append(f'{key} = {value}' if stripped == key else line)
    out = path.parent / f"broken-{key}.toml"
    out.write_text("\n".join(lines) + "\n")
    return out


def test_green_setup_passes_everything(config_file):
    r = run(config_file)
    assert r.returncode == 0, r.stdout
    assert "FAIL" not in r.stdout
    assert status_of(r.stdout, "opengotha.home") == "PASS"
    assert status_of(r.stdout, "opengotha.tournament") == "PASS"
    assert status_of(r.stdout, "site.dir") == "PASS"
    assert status_of(r.stdout, "site.deploy") == "PASS"
    assert "ready" in r.stdout


@pytest.mark.parametrize("key,value,red_row", [
    ("home",       '"/definitely/not/here"', "opengotha.home"),
    ("tournament", '"NoSuchEvent"',          "opengotha.tournament"),
    ("dir",        '"/definitely/not/here"', "site.dir"),
    ("repo",       '"/definitely/not/here"', "site.repo"),
    ("deploy",     '["bin/absent-script"]',  "site.deploy"),
])
def test_each_check_goes_red_on_its_own_defect(config_file, key, value, red_row):
    r = run(break_config(config_file, key, value))
    assert r.returncode == 1, r.stdout
    assert status_of(r.stdout, red_row) == "FAIL", r.stdout


def test_failure_output_names_the_bad_value(config_file):
    r = run(break_config(config_file, "home", '"/definitely/not/here"'))
    assert "/definitely/not/here" in r.stdout, "an agent cannot fix what is not named"


def test_failure_points_at_the_agent_setup_path(config_file):
    r = run(break_config(config_file, "dir", '"/definitely/not/here"'))
    assert "AGENTS.md" in r.stdout


def test_optional_settings_skip_rather_than_fail(config_file, tmp_path):
    """A missing TDList must not read as a broken setup: only two tools need it."""
    r = run(break_config(config_file, "path", f'"{tmp_path}/no-tdlist.tsv"'))
    assert status_of(r.stdout, "tdlist.path") == "SKIP"
    assert r.returncode == 0, "an absent TDList is not a setup failure"
    assert "fetch-tdlist" in r.stdout, "a SKIP should say how to satisfy it"


def test_site_dir_outside_site_repo_is_caught(config_file, tmp_path):
    """Deploy resolves page paths relative to the repo; outside it, that is a crash."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    r = run(break_config(config_file, "dir", f'"{elsewhere}"'))
    assert status_of(r.stdout, "site.dir inside site.repo") == "FAIL"


def test_unreachable_url_is_a_skip_not_a_failure(config_file):
    """Before the first deploy there is nothing to fetch - that is normal."""
    r = run(break_config(config_file, "url", '"https://nothing.invalid/x/"'))
    assert status_of(r.stdout, "site.url") == "SKIP"
    assert r.returncode == 0


def test_missing_config_is_reported_once(tmp_path):
    r = run(tmp_path / "absent.toml")
    assert r.returncode == 1
    # 'AGENTS.md' appears twice INSIDE one hint, so count the hint's own opener.
    assert r.stdout.count("Stuck?") == 1, "the hint used to print twice"
