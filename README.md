# baduk-tools

Command-line tools for running an American Go Association tournament — the ones
that turn a **desktop OpenGotha** into a live, phone-readable web presence, plus a
few for working with the AGA rating list.

Everything here is Python.  Nothing is a service, nothing phones home, and the
only state is your own tournament file and a `tournament.toml`.

## The publishing loop

[OpenGotha](https://www.opengotha.info/) is the pairing program most AGA
tournaments run on.  It is a desktop Java app: the tournament lives in one XML
file on the TD's laptop, and the room finds out what is happening by walking to
the wall chart.  These four tools read that same file and publish it, so a player
can check pairings from the parking lot and a parent can follow along from home.

| | |
|---|---|
| `og-pairings` | Round pairings → a self-contained page.  Winners go green as results are entered, so a link posted at pairing time keeps working all round. |
| `og-crosstab` | Cross-tab standings **computed live** from the tournament file — MMS / SOS / SOSOS, no Publish click, refreshable mid-round.  Reads the tournament's own `GeneralParameterSet`, so a parameter change in OpenGotha is picked up here.  `--verify` diffs our numbers against OpenGotha's own export as a known-answer control. |
| `og-test` | The test suite — 47 tests over a synthetic 8-player tournament and a pretend site.  `og-test` runs it; no install step. |
| `og-doctor` | Does every path in your config actually resolve?  PASS / FAIL / SKIP per setting, with the value it checked.  Run it before round 1. |
| `og-stale` | **The check you will forget.**  Every published page is a snapshot taken at deploy time; results entered afterwards are invisible until someone re-runs the publisher, and nothing else notices.  This compares each deployed page against the live XML and prints the exact redeploy command.  Exits 1 if anything is stale. |

The usual rhythm: pair the round in OpenGotha → **save** → `og-pairings --deploy`
→ enter result slips → `og-stale` → redeploy whatever it flags.  Save first,
always: the tools read the file on disk, not OpenGotha's memory, and the page
stamps that save time.

## AGA rating list

The **TDList** is the AGA's public list of every rated player — about 17,000 rows,
the same file OpenGotha downloads with its "Update AGA rating list" button.

| | |
|---|---|
| `fetch-tdlist` | Download and timestamp it.  Resolves the real endpoint at run time from `usgo.org/TDList{A,B,N}` — that address is a **JavaScript** redirect to a random-suffixed Azure host which has already rotated once, silently freezing a lot of downstream copies — and sends a browser User-Agent, without which you get a 403.  Keeps labelled snapshots (`--label pre-neopen`) so "what changed" is answerable later, and refreshes OpenGotha's own copy in place. |
| `aga-rank.py` | Where does one player stand nationally?  By name or AGA ID, inside their rank band and overall.  Pool defaults to players active in the last 5 years.  Stdlib only, no config — hand it a TDList and go. |
| `rating-changes` | Diff two TDList snapshots against a tournament results file: who gained, who lost, who moved a full rank.  Stdlib only. |
| `rank-audit` | Check a registration sheet's *declared* ranks against the book.  Truncation is the hard rule (+4.98 is 4d, not 5d), and asks are measured in **rank steps**, never rating delta — a delta threshold is wrong in both directions.  One-step promotion asks are auto-deny; two or more is the only case a TD actually rules on. |

## Setup

Requires **Python 3.11+** (for `tomllib`).  The OpenGotha publishers use
[uv](https://docs.astral.sh/uv/) via their shebang; `aga-rank.py` and
`rating-changes` are plain stdlib and run under any `python3`.

```sh
git clone https://github.com/gotrevor/baduk-tools
cd baduk-tools
cp tournament.toml.example tournament.toml     # then edit it
export PATH="$PWD/bin:$PATH"
```

**Not sure what to put in it?  Hand the job to an agent.**  These tools assume you
have a frontier model on hand, and [`AGENTS.md`](AGENTS.md) is written for one:

```sh
claude "set up baduk-tools for my tournament"    # CLAUDE.md loads AGENTS.md for you
codex  "read AGENTS.md and set up baduk-tools for my tournament"
```

It will find your OpenGotha installation and tournament file itself, ask you only
about your website, write the config, and verify it with `og-doctor`.  Every
failure message in this repo points back there.

`tournament.toml` is the only configuration: which OpenGotha installation, which
tournament file inside it, where built pages go, and how to push them.  It is
found in the current directory or at `~/.config/baduk-tools/tournament.toml`;
`--config PATH` and `$BADUK_TOURNAMENT_CONFIG` override.  A missing config is a
hard error naming every path tried — never a silent fallback to someone else's
tournament.

Deployment is deliberately not our problem: set `site.deploy` to whatever command
publishes your site, and the page paths get appended to it.  Any static host
works.  The example config points at
[wmgc.massgo.org](https://wmgc.massgo.org/ne-open-2026/), where these pages ran
the 2026 New England Go Open — that event is the worked example throughout.

## Tests

```sh
bin/og-test              # everything
bin/og-test -k doctor    # pytest arguments pass through
```

Fixtures build a synthetic tournament and a pretend site under `tmp_path`; **no
test touches a real tournament file, and no fixture carries a real registrant's
name, AGA id or rating.**  The scoring assertions are hand-computed from the
fixture's own results rather than pasted from a tool run — otherwise they would
only prove the code agrees with itself.  `og-doctor` is driven red *and* green on
every check it makes.  CI runs the suite on Python 3.11 and 3.13.

## Caveats

These grew out of running real tournaments, so they know things about the AGA and
about OpenGotha 3.52 that are true rather than general.  Bug reports and patches
from other TDs are very welcome — especially "this assumed my tournament looks
like yours."

Apache 2.0.
