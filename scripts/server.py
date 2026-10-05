"""The chess-results MCP server: Chess-Results queries and team result entry as tools.

Started by the host (Claude Code, Codex, …) over stdio. The Chess-Results login is
read from the system credential store (credentials.py), never from the host, so one
stored login serves every host. Club settings come from chess-results.json in the
project folder (report.py, find_config). A host that loads the server without
SKILL.md (ChatGPT, …) learns the workflow from the server's instructions and which
tool changes anything from the tool annotations.

    python3 server.py            # normally the host starts it
"""
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

import client
import credentials
from report import load_config, require_club

# SKILL.md in short, for hosts that only see the server.
INSTRUCTIONS = """\
Chess-Results (chess-results.com) has no API: these tools read its public pages and
replay its own forms. Quote what they return; don't fill gaps from memory. The site
throttles bursts: ask for what the question needs, not whole seasons in a loop.

search_players returns tournament appearances, not a register. A player grouped by
name only (no FIDE id or ident) may be several people, and one person may appear under
several spellings; say so.

Photographed team match reports (Spielberichte) -> entered results:
1. Transcribe each match exactly as written; do not correct names or numbers. A player
   is [ident, name as written], "" where the sheet has no ident (it is looked up); null
   is a board nobody sat at. Results from the home side. A blank result with both
   players present: ask the user. Read digits carefully (1/7, 3/8, 0/6) and say where
   one was unclear.
2. check_match_report(report) saves nothing. Show the user its log and every STOP,
   NOTICE and warn. Home and guest written the wrong way round is fine: the check turns
   the report around (a NOTE); tell the user.
3. enter_match_report(completed, confirm=true) only after the check came back clean and
   the user said yes, with the check's `completed` report. Saved results are public to
   the whole league.

Result entry needs a Chess-Results login, which the user stores in their own terminal
(python3 scripts/cli.py login). Never ask for the password in chat. Queries are public.
"""

mcp = FastMCP('chess-results', instructions=INSTRUCTIONS)
_session = {}

# Every tool reads chess-results.com; only enter_match_report changes anything there.
# Hosts such as ChatGPT ask the user before calling a tool that is not read-only.
READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
SAVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)


# ---------------------------------------------------------------- result models
# Every tool declares what it returns. Clients get an outputSchema and the result as
# structuredContent; a change on Chess-Results' side shows up as a validation error
# instead of silently different data.

class CredentialStatus(BaseModel):
    stored: bool = Field(description='Whether a Chess-Results login is available')
    source: str | None = Field(None, description='environment, keyring, or macOS Keychain')
    account: str | None = Field(None, description='The Chess-Results personal number (never the password)')
    hint: str | None = Field(None, description='How to store a login when none is found')


class Status(BaseModel):
    credentials: CredentialStatus
    settings: str | None = Field(None, description='The club settings file in use (chess-results.json)')
    club: str | None = Field(None, description='The club the match tools work for')
    login: str | None = Field(None, description='Whom Chess-Results logs on as, or why the login failed')


class Appearance(BaseModel):
    tournament: str | None = None
    end: str | None = Field(None, description='Tournament end date, YYYY-MM-DD')
    rank: int | None = Field(None, description='Final rank; none in team competitions')
    rounds: int | None = None
    players: int | None = Field(None, description='Number of participants')
    nameShortened: bool | None = Field(None, description='The name is cut short as the search printed it '
                                                         '(too many tournaments to look up); see tournament(tnr)')
    tnr: str | None = Field(None, description='Tournament number, for player_card and tournament')
    snr: str | None = Field(None, description="The player's number in that tournament, for player_card")


class Player(BaseModel):
    name: str
    ident: str | None = Field(None, description='National register number (e.g. ÖSB Pers. Nr.)')
    fideId: str | None = None
    federation: str | None = None
    clubs: list[str] = []
    grouping: str = Field(description='fide, ident, or name (name = unverified: may be several people)')
    appearances: list[Appearance] = []


class PlayerSearch(BaseModel):
    query: dict[str, str]
    players: list[Player]
    playerCount: int
    truncated: bool = Field(description='More results exist than returned; narrow the search')


class CardPlayer(BaseModel):
    name: str | None = None
    ident: str | None = Field(None, description='National register number')
    fideId: str | None = None
    federation: str | None = None
    title: str | None = None
    club: str | None = None
    birthYear: int | None = None
    rating: int | None = Field(None, description='The rating the tournament used')
    ratingNational: int | None = None
    ratingInternational: int | None = None
    performance: int | None = None
    startingRank: int | None = None
    rank: int | None = None
    points: float | None = None


class PlayerCard(BaseModel):
    tournament: str | None = None
    player: CardPlayer = Field(description='The card\'s facts, typed; 0 ratings are null')
    fields: dict[str, str] = Field(description='The card as printed: Name, Ident-Number, Fide-ID, …')
    games: list[dict[str, Any]] = Field(description="The player's rounds in that tournament")
    source: str


class TournamentHit(BaseModel):
    tnr: str | None = None
    name: str | None = None
    country: str | None = None
    start: str | None = Field(None, description='YYYY-MM-DD')
    end: str | None = Field(None, description='YYYY-MM-DD')
    location: str | None = None
    organizer: str | None = None
    director: str | None = None
    rounds: int | None = None
    players: int | None = None
    updatedAt: str | None = Field(None, description='Last upload, ISO 8601 UTC to the minute (the site '
                                                    'prints it as time ago)')


class TournamentSearch(BaseModel):
    query: dict[str, Any]
    tournaments: list[TournamentHit]
    count: int


class Table(BaseModel):
    header: list[str] | None = Field(None, description='Column names; rows are keyed by them')
    rows: list[dict[str, Any]] = Field(description='One dict per row, keyed by the header; {"section": …} marks '
                                                    'a heading row (a team, a round), with "date" (ISO) when it '
                                                    'names one; {"cells": […]} a row that does not fit the header; '
                                                    '"_link" the row\'s tournament link. Dates are ISO.')


class TournamentPage(BaseModel):
    tnr: str
    title: str | None = None
    url: str
    info: dict[str, str] | None = Field(None, description='Details block (with details=true): organiser, venue, …')
    start: str | None = Field(None, description='First day, YYYY-MM-DD (with details=true)')
    end: str | None = Field(None, description='Last day, YYYY-MM-DD (with details=true)')
    tables: list[Table]
    views: dict[str, dict[str, str]] = Field(description='Other pages of this tournament: label -> {art, rd, snr}')


class League(BaseModel):
    name: str
    tnr: str


class Leagues(BaseModel):
    leagues: list[League]


class MatchCheck(BaseModel):
    log: str = Field(description='The check, one table per match, with every STOP, NOTICE and warn')
    problems: int = Field(0, description='Number of problems; 0 means every match is clean')
    completed: dict[str, Any] | None = Field(None, description='The report with every ident filled in and the '
                                                               'sides as Chess-Results pairs them; pass it '
                                                               'to enter_match_report')
    loggedOnAs: str | None = None
    error: str | None = Field(None, description='Why the check could not run at all')


class MatchEntry(BaseModel):
    log: str
    problems: int = Field(0, description='Number of matches not saved or not confirmed; 0 means all saved')
    loggedOnAs: str | None = None
    error: str | None = None


# ---------------------------------------------------------------- tools

def session():
    """One polite, retrying session per server process (requests are spaced)."""
    if 's' not in _session:
        _session['s'] = client.session(load_config())
    return _session['s']


ERRORS = (client.EntryError, client.QueryError, credentials.CredentialError, ValueError)


def _run(fn, *args, **kwargs):
    """Call fn, capturing what it prints: (printed text, result, error message)."""
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            result = fn(*args, **kwargs)
        return out.getvalue(), result, None
    except ERRORS as e:
        return out.getvalue(), None, str(e)


def _query(fn, *args, **kwargs):
    """A query's result, or an MCP error with the reason."""
    _, result, error = _run(fn, *args, **kwargs)
    if error:
        raise ToolError(error)
    return result


@mcp.tool(annotations=READ)
def status() -> Status:
    """Whether a Chess-Results login is stored (never the password), which club
    settings file is in use, and whether the login works right now."""
    cfg = load_config()
    info = Status(credentials=CredentialStatus(**credentials.status()), settings=cfg.get('_path'),
                  club=cfg.get('club'))
    if info.credentials.stored:
        _, who, error = _run(client.login, session())
        info.login = who or f'failed: {error}'
    return info


@mcp.tool(annotations=READ)
def search_players(last_name: str = '', first_name: str = '', ident: str = '', fide_id: str = '',
                   federation: str = '', club: str = '', birth_year: str = '', date_from: str = '',
                   date_to: str = '', limit: int = 50) -> PlayerSearch:
    """Find players and their tournament appearances on Chess-Results. Needs a
    last_name, ident (national register number), fide_id or federation (three
    letters, e.g. AUT). date_from/date_to (YYYY-MM-DD) limit the tournaments' end
    dates. Appearances carry tnr/snr for player_card. Appearances, not a register:
    a player grouped by name only may be several people."""
    query = {k: v for k, v in dict(last_name=last_name, first_name=first_name, ident=ident,
                                   fide_id=fide_id, federation=federation, club=club,
                                   birth_year=birth_year, date_from=date_from, date_to=date_to).items() if v}
    return PlayerSearch(**_query(client.search_players, session(), limit=limit, **query))


@mcp.tool(annotations=READ)
def player_card(tnr: int, snr: int) -> PlayerCard:
    """A player's card in one tournament: ident, FIDE id, birth year, ratings
    (national and international), federation, club, and their games there."""
    return PlayerCard(**_query(client.player_card, session(), tnr, snr))


@mcp.tool(annotations=READ)
def search_tournaments(name: str = '', country: str = '', location: str = '', organizer: str = '',
                       director: str = '', tnr: str = '', ended_from: str = '', ended_to: str = '',
                       limit: int = 50) -> TournamentSearch:
    """Find tournaments on Chess-Results by name, country (three letters), location,
    organiser, director or number, optionally by end date (YYYY-MM-DD)."""
    query = {k: v for k, v in dict(name=name, location=location, organizer=organizer, director=director,
                                   tnr=tnr, ended_from=ended_from, ended_to=ended_to).items() if v}
    return TournamentSearch(**_query(client.search_tournaments, session(), country=country or None,
                                     limit=limit, **query))


@mcp.tool(annotations=READ)
def tournament(tnr: int, art: int | None = None, rd: int | None = None, snr: int | None = None,
               details: bool = False) -> TournamentPage:
    """Any page of a tournament as tables, plus `views`: the page's menu of other pages
    (label -> art/rd parameters). Start without `art` and follow the views. Common
    ones: art=1 final ranking (individual) or team compositions with results (team),
    art=2 pairings/schedule, art=3 + rd round results, art=8 team compositions,
    art=46 final table, art=9 + snr a player. details=True adds organiser, venue,
    arbiters and time control."""
    return TournamentPage(**_query(client.tournament, session(), tnr, art=art, rd=rd, snr=snr, details=details))


@mcp.tool(annotations=READ)
def championship_leagues(year: int, prefix: str = '') -> Leagues:
    """The leagues of an Austrian championship season (Chess-Results' "AUT
    championship" overview), optionally only names starting with `prefix` (e.g.
    "Bgld"). year is the season's first year: 2026 for 2026/27."""
    return Leagues(leagues=_query(client.championship_leagues, session(), year, prefix or None))


def _match(report, save):
    cfg = load_config()
    require_club(cfg)
    s = session()
    who = client.login(s)
    import match
    problems, completed = match.process(s, cfg, report, save)
    return who, problems, completed


@mcp.tool(annotations=READ)
def check_match_report(report: dict[str, Any]) -> MatchCheck:
    """Check a transcribed team match report against Chess-Results, saving nothing.

    report: {"date": "YYYY-MM-DD", "matches": [{"division", "round", "home": {"team"},
    "away": {"team"}, "total": "1:3", "boards": [{"home": [ident, name as written],
    "result": "1-0", "away": [ident, name]}]}]}. An ident of "" is looked up; a player
    of null is a no-show. Results: 1-0, 0-1, ½-½, +-- (1K-0K), --+ (0K-1K), --- , ?.
    Logs in, finds the pairing by date and our team, checks every player against the
    clubs' member lists and team compositions, then presses "Eingabe Prüfen".
    `completed` is the report with every ident filled in: pass it to
    enter_match_report."""
    log, result, error = _run(_match, report, False)
    if error:
        return MatchCheck(log=log, error=error)
    who, problems, completed = result
    return MatchCheck(log=log, problems=problems, completed=completed, loggedOnAs=who)


@mcp.tool(annotations=SAVE)
def enter_match_report(report: dict[str, Any], confirm: bool = False) -> MatchEntry:
    """Check and SAVE a team match report on Chess-Results. Saved results are public
    to the whole league. Only call after check_match_report came back clean and the
    user has said yes, with confirm=true. Matches that are not clean on every count,
    or outside the entry window, are not saved; the overview is reloaded to confirm
    each saved score."""
    if not confirm:
        raise ToolError('Not saved: call with confirm=true once the user has approved the checked results.')
    log, result, error = _run(_match, report, True)
    if error:
        return MatchEntry(log=log, error=error)
    who, problems, _ = result
    return MatchEntry(log=log, problems=problems, loggedOnAs=who)


if __name__ == '__main__':
    mcp.run()
