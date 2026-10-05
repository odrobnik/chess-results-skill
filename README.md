# chess-results

Tools for [Chess-Results](https://chess-results.com) for AI agents and the terminal:

- **Queries** — players (appearances, idents, FIDE ids, ratings, player cards),
  tournaments, any tournament page as data (rankings, pairings, round results, team
  compositions, tables), the leagues of an Austrian championship season.
- **Team result entry** — from the photographed match report to saved results:
  every player is checked against both clubs' member lists and the teams' rosters on
  Chess-Results, missing idents are looked up, Chess-Results' own check runs, and
  results are saved only after explicit confirmation.
- **Result cards** — a square PNG per match for social media, drawn from what
  Chess-Results has on record.

Works as an **MCP server** (Claude Code plugin, Codex, any MCP client), as an
**OpenClaw / ClawHub skill**, and as a **command line**. Chess-Results has no API;
the client reads its pages and replays the website's own forms, spacing its requests.

The login is kept in the system credential store (macOS Keychain, Windows Credential
Manager, Linux Secret Service) — one entry for every tool, never in a file.

## Documentation

- [SKILL.md](SKILL.md) — what the tools do and the match-report workflow
- [SETUP.md](SETUP.md) — installation, login, club settings, Claude Code and Codex
- Source: [github.com/odrobnik/chess-results-skill](https://github.com/odrobnik/chess-results-skill)

## Quick start

```bash
pip install -r requirements.txt
python3 scripts/cli.py tournaments --name "Landesliga" --country AUT
python3 scripts/cli.py login          # only for result entry
```

## License

MIT — see [LICENSE](LICENSE). Not affiliated with Chess-Results or its operators;
use it within the site's terms and go easy on the server.
