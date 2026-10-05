# chess-results

Tools for [Chess-Results](https://chess-results.com) — for AI agents and the terminal.

- **Queries** — players (tournament appearances, national idents, FIDE ids, ratings,
  player cards), tournaments, any tournament page as data (rankings, pairings, round
  results, team compositions, tables), and the leagues of an Austrian championship
  season. No login needed.
- **Team result entry** — from a photographed paper match report to saved results.
  Every player is checked against both clubs' member lists and the teams' rosters on
  Chess-Results, missing idents are looked up, Chess-Results' own check runs, and
  results are saved only after explicit confirmation.

One folder, four ways in: a **Claude Code plugin**, an **OpenClaw plugin or skill**,
an **MCP server** for any MCP client (Codex, …), and a **command line**.

Chess-Results has no API. The client reads its public pages and replays the website's
own forms, spacing and caching its requests.

## Install

You need **Python 3.11+** and the packages in `requirements.txt`:

```bash
pip install -r requirements.txt
```

**Claude Code**

```text
/plugin marketplace add odrobnik/chess-results-skill
/plugin install chess-results@chess-results-skill
```

**OpenClaw** — as a plugin (MCP tools plus the skill), or as a skill only:

```bash
openclaw plugins install git:github.com/odrobnik/chess-results-skill@v0.1.0
openclaw skills install @odrobnik/chess-results
```

**Codex or another MCP client** — start `scripts/server.py` over stdio:

```toml
[mcp_servers.chess-results]
command = "python3"
args = ["/path/to/chess-results/scripts/server.py"]
```

**Command line**

```bash
python3 scripts/cli.py tournaments --name "Landesliga" --country AUT
python3 scripts/cli.py players --last-name Huber --federation AUT
```

See [SETUP.md](SETUP.md) for every option, including the OpenClaw details.

## Tools

| MCP tool | Command line | What it does |
|---|---|---|
| `search_players` | `cli.py players` | Players and their tournament appearances |
| `player_card` | `cli.py player <tnr> <snr>` | Birth year, ratings and games in one tournament |
| `search_tournaments` | `cli.py tournaments` | Tournaments by name, place, organiser, country |
| `tournament` | `cli.py tournament <tnr>` | Any tournament page as tables, with links to the other views |
| `championship_leagues` | `cli.py leagues <year>` | The leagues of an Austrian championship season |
| `check_match_report` | `cli.py check report.json` | Check a match report against Chess-Results; saves nothing |
| `enter_match_report` | `cli.py enter report.json` | Check and save, only with `confirm=true` |
| `status` | `cli.py status` | Whether a login is stored and works |

[SKILL.md](SKILL.md) describes the match-report workflow the agent follows.

## Login and club settings

The queries are public. **Result entry** needs a Chess-Results login and your club's
settings:

- **Login** — run `python3 scripts/cli.py login` once, in your own terminal. It asks
  for your personal number and password (hidden) and stores them in the system
  credential store: macOS Keychain, Windows Credential Manager or Linux Secret
  Service. On a machine without one, `cli.py login --file` writes a private file
  (mode 600) instead. The password never goes into a config file or a chat.
- **Club settings** — copy
  [`examples/chess-results.example.json`](examples/chess-results.example.json) to
  `chess-results.json` and adapt it (your club's name, its leagues, the entry
  deadline). It stays out of the repository.

## Good to know

- **Be gentle with the server.** Requests are spaced and retried with back-off, and
  public pages are cached. Ask for what you need, not whole seasons in a loop.
- **Appearances are not a register.** A player found by name alone may be several
  people, and one person may appear under several spellings.
- **Saved results are public** to the whole league. The agent only saves after the
  check came back clean and you said yes.

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests run offline. Every club, player and number in them is made up.

## Changes

**0.2.0** — Query results are consistent data: ISO dates everywhere, the last update
of a tournament as a timestamp (`updatedAt`, was "19 Hours 24 Min."), numbers as
integers, full tournament names in player searches (the site cuts them to 30
characters), a typed `player` block on player cards, `start`/`end` on tournament
pages, unique column names (a schedule's two "Team" columns no longer collapse into
one), match headings on round pages, and no menu entries among tournament details.
`cli.py enter` saves only after a typed yes (or `--yes`). SECURITY.md describes what
the skill accesses.

**0.1.0** — First release.

## License

MIT — see [LICENSE](LICENSE). Not affiliated with Chess-Results or its operators;
use it within the site's terms.
