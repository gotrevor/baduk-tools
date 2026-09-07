"""Where this tournament lives on disk and on the web.

Every publisher in this repo needs the same four facts: which OpenGotha
installation is running, which tournament file inside it, where the built pages
go, and how to push them.  Hard-coding those is what kept these tools private,
so they live in a `tournament.toml` instead:

    [opengotha]
    home       = "~/Applications/OpenGotha-3.52.03"
    tournament = "NEOpen2026"          # basename of the .xml, no extension

    [event]
    title    = "NE Open 2026"          # <title> and page heading
    subtitle = "5th New England Go Open &middot; Hopkinton Center for the Arts"

    [site]
    dir    = "~/src/wmgc/ne-open-2026" # built pages land here
    repo   = "~/src/wmgc"              # deploy runs from here
    url    = "https://wmgc.massgo.org/ne-open-2026/"
    deploy = ["bin/deploy"]            # argv prefix; page paths are appended

    [tdlist]
    path = "~/personal/data/aga/tdlist.tsv"

    [sheets]
    cmd = ["gdrive", "-a", "personal", "sheets", "read"]   # optional; TSV on stdout

Searched in order, first hit wins:

    --config PATH  (any tool)
    $BADUK_TOURNAMENT_CONFIG
    ./tournament.toml
    ~/.config/baduk-tools/tournament.toml

A missing config is a hard error naming every path tried - never a silent
fallback to somebody else's tournament.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

CONFIG_NAME = "tournament.toml"
USER_CONFIG = Path.home() / ".config" / "baduk-tools" / CONFIG_NAME


def _p(value, what: str) -> Path:
    if not value:
        sys.exit(f"tournament.toml: missing {what}")
    return Path(str(value)).expanduser()


class Config:
    def __init__(self, data: dict, source: Path):
        self.source = source
        self._og = data.get("opengotha", {})
        self._site = data.get("site", {})
        self._event = data.get("event", {})
        self._td = data.get("tdlist", {})
        self._sheets = data.get("sheets", {})

    # --- OpenGotha ------------------------------------------------------------
    @property
    def og_home(self) -> Path:
        return _p(os.environ.get("OPENGOTHA_HOME") or self._og.get("home"),
                  "[opengotha] home")

    @property
    def tournament(self) -> str:
        name = self._og.get("tournament")
        if not name:
            sys.exit("tournament.toml: missing [opengotha] tournament")
        return str(name)

    @property
    def xml_candidates(self) -> list[Path]:
        """OpenGotha keeps the live file under tournamentfiles/work while it is open."""
        base = self.og_home / "tournamentfiles"
        return [base / "work" / f"{self.tournament}.xml", base / f"{self.tournament}.xml"]

    def newest_xml(self) -> Path:
        live = [p for p in self.xml_candidates if p.is_file()]
        if not live:
            sys.exit("no OpenGotha tournament file found; looked in\n  " +
                     "\n  ".join(str(p) for p in self.xml_candidates) +
                     f"\n(config: {self.source})")
        return max(live, key=lambda p: p.stat().st_mtime)

    @property
    def export_dir(self) -> Path:
        return self.og_home / "exportfiles" / "html"

    # --- naming -------------------------------------------------------------
    @property
    def event_title(self) -> str:
        return str(self._event.get("title") or self.tournament)

    @property
    def event_subtitle(self) -> str:
        """Raw HTML: it lands inside the page's subtitle line, entities and all."""
        return str(self._event.get("subtitle", ""))

    # --- the site -------------------------------------------------------------
    @property
    def site_dir(self) -> Path:
        return _p(self._site.get("dir"), "[site] dir")

    @property
    def site_repo(self) -> Path:
        return _p(self._site.get("repo"), "[site] repo")

    @property
    def index_md(self) -> Path:
        return self.site_dir / self._site.get("index", "index.md")

    def page_url(self, filename: str) -> str:
        base = str(self._site.get("url", "")).rstrip("/")
        return f"{base}/{filename}" if base else filename

    def deploy(self, paths) -> int:
        """Run the site's own deploy command on the given paths, from the repo root."""
        cmd = list(self._site.get("deploy") or ["bin/deploy"])
        rel = []
        for p in paths:
            p = Path(p)
            rel.append(str(p.relative_to(self.site_repo)) if p.is_absolute() else str(p))
        return subprocess.run(cmd + rel, cwd=self.site_repo).returncode

    # --- the AGA rating list --------------------------------------------------
    @property
    def tdlist(self) -> Path:
        return _p(os.environ.get("AGA_TDLIST") or self._td.get("path"), "[tdlist] path")


    @property
    def sheets_cmd(self) -> list[str] | None:
        cmd = self._sheets.get("cmd")
        return [str(x) for x in cmd] if cmd else None


def add_config_arg(ap):
    ap.add_argument("--config", metavar="PATH",
                    help=f"tournament.toml to use (default: ./{CONFIG_NAME} or {USER_CONFIG})")


def load(explicit: str | None = None) -> Config:
    tried = []
    for cand in (explicit, os.environ.get("BADUK_TOURNAMENT_CONFIG"),
                 Path.cwd() / CONFIG_NAME, USER_CONFIG):
        if not cand:
            continue
        path = Path(str(cand)).expanduser()
        tried.append(path)
        if path.is_file():
            with path.open("rb") as fh:
                return Config(tomllib.load(fh), path)
    sys.exit("no tournament config found; looked for\n  " +
             "\n  ".join(str(p) for p in tried) +
             "\nCopy tournament.toml.example and fill it in.")
