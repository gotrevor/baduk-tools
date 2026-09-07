# AGENTS.md — setting up and running baduk-tools

*(`CLAUDE.md` in this repo is a one-line `@AGENTS.md` include, so Claude Code loads
this file automatically.)*

You are reading this because someone pointed you at this repo, probably with
something like *"set up baduk-tools for my tournament."*  This file is written
for you, not for them.  The human is a **tournament director**: they know Go and
OpenGotha, and they may not know Python, TOML, or where their site lives.  Do the
finding-out yourself; ask them only what a filesystem cannot answer.

## What these tools do

[OpenGotha](https://www.opengotha.info/) is a desktop Java app.  The whole
tournament lives in one XML file on the TD's laptop.  These tools read that file
and publish it to the web, so the room can see pairings and standings without
crowding the wall chart.  Nothing here writes to the tournament file — every tool
is read-only on OpenGotha's data.  Say so if they ask; it is the first thing a TD
worries about.

## The setup, in order

**1. Find OpenGotha.**  Look for `tournamentfiles/` under the app directory:

```sh
ls -d ~/Applications/OpenGotha* /Applications/OpenGotha* 2>/dev/null
find ~ -maxdepth 4 -type d -name tournamentfiles 2>/dev/null | head
```

**2. Find the tournament.**  `<home>/tournamentfiles/work/*.xml` is the file
OpenGotha has open right now; `<home>/tournamentfiles/*.xml` is where saved ones
land.  The `[opengotha] tournament` key is the **basename without `.xml`**.  If
you find several, list them with modification times and ask which event this is —
do not guess, and do not just take the newest.

**3. Ask where the pages should go.**  This is the one part you cannot discover.
You need a local directory that is inside a git repo or upload root, the public
URL that directory is served at, and the command that publishes it.  Many TDs
have no site at all: that is fine, and worth saying out loud — set `site.dir` to
a local folder, leave `site.deploy` alone, and they can open the built HTML in a
browser or email it.  `--deploy` is the only thing they lose.

**4. Write the config.**  `cp tournament.toml.example tournament.toml` (or
`~/.config/baduk-tools/tournament.toml` for a machine-wide default), then fill it
in.  `[event] subtitle` is raw HTML dropped under the heading of every page —
club, venue, dates.  Keep it short; it is a subtitle, not a paragraph.

**5. Verify.**  `bin/og-doctor` checks every path and prints PASS/FAIL/SKIP with
the value it checked.  **Fix every FAIL before telling the human you are done.**
SKIP lines are optional features, not problems.  Then `bin/og-pairings -n` for a
dry run that writes nothing.

## Running an event

Pair the round in OpenGotha → **File > Save** → `og-pairings --deploy` → enter
result slips → `og-stale` → redeploy whatever it flags.

The single most important thing to tell a TD: **the tools read the file on disk,
not OpenGotha's memory.**  If they did not save, the page shows the previous
state and nothing warns them.  And every published page is a snapshot taken at
deploy time, so results entered afterwards are invisible until someone re-runs
the publisher — which is what `og-stale` exists to catch.  Run it after every
batch of slips; it exits 1 and prints the exact redeploy command.

Mid-tournament, a TD is busy and focused - deep in pairings, slips and the next
round.  Prefer running the command and reporting the result over handing them a
command to type.

## If you are changing the code

- Every path, the event name and the deploy command come from `tournament.toml`
  via `bin/tdconfig.py`.  **Never hard-code one back in** — that is the whole
  reason this repo exists.  A config named out loud (`--config`,
  `$BADUK_TOURNAMENT_CONFIG`) that does not exist is a hard error, never a
  fallback: silently running the wrong tournament is the one failure these tools
  must not have.
- `og-crosstab` reads the tournament's own `GeneralParameterSet` for the MM bar,
  floor, zero and bye/absent values, so a parameter change in OpenGotha is picked
  up automatically.  Do not reimplement the scoring rules as constants.
- **Run `bin/og-test` before and after any change**, and add a case for what you
  changed.  Fixtures are synthetic and live in `tests/fixtures/`; keep them that
  way — a real registrant's name does not belong in a public test suite.  Assert
  scoring against numbers you worked out from the fixture by hand, never against
  output you captured from the tool you are testing.
- **The known-answer control is `og-crosstab --verify`**: it diffs our computed
  MMS/SOS/SOSOS against OpenGotha's own exported StandingsRN.html, row by row.
  Run it after touching any scoring code.  A refactor that changes no behaviour
  should also regenerate an already-published page byte for byte — that is how
  this repo's extraction from a private tree was checked.
- The publishers use [uv](https://docs.astral.sh/uv/) via their shebang;
  `aga-rank.py` and `rating-changes` are deliberately stdlib-only so a TD can
  download one file and run it under any `python3`.  Keep them that way.
- These tools know real things about the AGA and about OpenGotha 3.52 — rating
  truncation, the TDList's JavaScript redirect, the 403 on a default User-Agent.
  Those are not arbitrary; check the docstring before "simplifying" one away.
