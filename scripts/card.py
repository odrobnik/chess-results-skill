"""A square result card per team match, drawn with Pillow, for social media.

It shows what Chess-Results has on record, not what the sheet says: the round's
public entry page lists every saved board with idents, names, chess titles and the
ratings of that round (the national rating, or the FIDE one where a player has
none). So a card is made after the result has been entered, and is right by
construction. Our club's players are set bold and every result is coloured from our
side: won, drawn, lost.

    python3 cli.py card --date 2026-10-04 [--team 3]

One PNG per match, 1080 × 1080, in the folder the settings name ("card.output",
relative to the working folder).
"""
import re
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from client import EntryError, Pages, saved_pairings
from report import RESULTS, fold, is_ours, team_number

SIZE, MARGIN = 1080, 72
FOREST, INK, MUTED = (25, 55, 47), (24, 51, 46), (100, 114, 110)
PAPER, LINE, SAGE = (246, 245, 239), (220, 226, 220), (191, 206, 196)
WON, DRAWN, LOST = (36, 100, 80), (135, 96, 41), (149, 75, 67)

TEXT = {
    'de': dict(won='SIEG', drawn='UNENTSCHIEDEN', lost='NIEDERLAGE', round='Runde',
               forfeit='kampflos', absent='nicht angetreten'),
    'en': dict(won='WIN', drawn='DRAW', lost='LOSS', round='Round',
               forfeit='forfeit', absent='did not play'),
}

# (regular, bold, italic, medium, light) per font file; the first that exists is used.
SANS = [('/System/Library/Fonts/HelveticaNeue.ttc', (0, 1, 2, 10, 7)),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', None),
        ('C:/Windows/Fonts/arial.ttf', None)]
SERIF = ['/System/Library/Fonts/Supplemental/Georgia.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', 'C:/Windows/Fonts/georgia.ttf']
REGULAR, BOLD, ITALIC, MEDIUM, LIGHT = range(5)


def font(size, weight=REGULAR):
    for path, faces in SANS:
        if Path(path).exists():
            if faces:
                return ImageFont.truetype(path, size, index=faces[weight])
            bold = path.replace('DejaVuSans.ttf', 'DejaVuSans-Bold.ttf').replace('arial.ttf', 'arialbd.ttf')
            return ImageFont.truetype(bold if weight == BOLD and Path(bold).exists() else path, size)
    return ImageFont.load_default(size)


def serif(size):
    for path in SERIF:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return font(size)


def fit(draw, text, width, size, weight=REGULAR, minimum=20):
    while size > minimum:
        f = font(size, weight)
        if draw.textlength(text, font=f) <= width:
            return f
        size -= 1
    return font(minimum, weight)


def display_name(player):
    """'FM Anna Berger' from 'Berger, Anna' and the title; academic titles written
    into the name ("Huber, Karl DI.") are left out."""
    surname, _, given = player['name'].partition(',')
    given = ' '.join(w for w in given.split() if not w.endswith('.'))
    title = f"{player['title']} " if player.get('title') else ''
    return f'{title}{given} {surname.strip()}'.strip()


def score_text(x):
    whole, half = int(x), x % 1
    return (f'{whole}½' if whole else '½') if half else str(whole)


def draw_card(pairing, day, league, round_no, cfg):
    words = TEXT.get(cfg.get('card', {}).get('language', 'de'), TEXT['de'])
    img = Image.new('RGB', (SIZE, SIZE), PAPER)
    d = ImageDraw.Draw(img)
    ours = 'home' if is_ours(pairing['home'], cfg) else 'away'
    us = 0 if ours == 'home' else 1

    d.rectangle([0, 0, SIZE, 196], fill=FOREST)
    d.text((MARGIN, 58), cfg.get('card', {}).get('title', cfg['club_name'].upper()),
           font=font(24, MEDIUM), fill=SAGE)
    heading = league + (f" · {words['round']} {round_no}" if round_no else '')
    size = 40
    while size > 24 and d.textlength(heading, font=serif(size)) > SIZE - 2 * MARGIN - 200:
        size -= 1
    d.text((MARGIN, 98), heading, font=serif(size), fill=(237, 243, 238))
    d.text((SIZE - MARGIN, 62), f'{day:%d.%m.%Y}', font=font(26, LIGHT), fill=SAGE, anchor='ra')

    total = [sum(RESULTS[b['result']][i] for b in pairing['boards']) for i in (0, 1)]
    outcome = WON if total[us] > total[1 - us] else LOST if total[us] < total[1 - us] else DRAWN
    centre = SIZE // 2
    d.text((centre, 300), f'{score_text(total[0])} : {score_text(total[1])}', font=font(112, BOLD),
           fill=outcome, anchor='mm')
    half = centre - MARGIN - 150
    for side, x, anchor in (('home', MARGIN, 'lm'), ('away', SIZE - MARGIN, 'rm')):
        team, weight = pairing[side], BOLD if side == ours else REGULAR
        lines, f = [team], fit(d, team, half, 40, weight, minimum=30)
        if d.textlength(team, font=f) > half:
            parts = team.split()
            cut = max(1, len(parts) // 2)
            lines = [' '.join(parts[:cut]), ' '.join(parts[cut:])]
            f = fit(d, max(lines, key=len), half, 36, weight, minimum=22)
        y = 300 - (len(lines) - 1) * 22
        for line in lines:
            d.text((x, y), line, font=f, fill=INK if side == ours else MUTED, anchor=anchor)
            y += 44
    label = {WON: words['won'], DRAWN: words['drawn'], LOST: words['lost']}[outcome]
    d.text((centre, 390), label, font=font(22, MEDIUM), fill=outcome, anchor='mm')

    space_top, space_bottom = 440, SIZE - 100
    n = len(pairing['boards'])
    row = min(112, (space_bottom - space_top) // n)
    top = space_top + (space_bottom - space_top - row * n) // 2
    name_w = centre - MARGIN - 120
    mark = {1: '1', 0: '0', .5: '½'}
    for i, board in enumerate(pairing['boards']):
        y = top + i * row
        mid = y + row // 2
        if i:
            d.line([MARGIN, y, SIZE - MARGIN, y], fill=LINE, width=2)
        d.text((MARGIN, mid), str(i + 1), font=font(24, LIGHT), fill=MUTED, anchor='lm')
        res = RESULTS[board['result']]
        colour = WON if res[us] > res[1 - us] else LOST if res[us] < res[1 - us] else DRAWN
        forfeit = board['result'] in ('+--', '--+', '---')
        text = '?' if board['result'] == '?' else f'{mark[res[0]]} – {mark[res[1]]}'
        if board['result'] == '?':
            colour = MUTED
        d.text((centre, mid - (8 if forfeit else 0)), text, font=font(34, BOLD), fill=colour, anchor='mm')
        if forfeit:
            d.text((centre, mid + 24), words['forfeit'], font=font(18, MEDIUM), fill=colour, anchor='mm')
        for side, x, anchor in (('home', MARGIN + 46, 'ls'), ('away', SIZE - MARGIN, 'rs')):
            player = board[side]
            if player is None:
                d.text((x, mid + 11), words['absent'], font=font(26, ITALIC), fill=MUTED, anchor=anchor)
                continue
            bold = side == ours
            name = display_name(player)
            f = fit(d, name, name_w - (0 if side == 'away' else 46), 30, BOLD if bold else REGULAR)
            base = mid + (2 if player['rating'] else 11)
            d.text((x, base), name, font=f, fill=INK if bold else MUTED, anchor=anchor)
            if player['rating']:
                d.text((x, base + 8), str(player['rating']), font=font(20, LIGHT), fill=MUTED,
                       anchor='la' if anchor == 'ls' else 'ra')

    footer = cfg.get('card', {}).get('footer', 'chess-results.com')
    d.text((MARGIN, SIZE - 52), footer, font=font(20, LIGHT), fill=MUTED, anchor='ls')
    return img


def round_number(html):
    m = re.search(r'(\d+)\.\s*(?:Runde|Round)', html)
    return m.group(1) if m else None


def make_cards(s, cfg, day, teams=None, out=None):
    """Draw a card per entered match of our club on `day` (only team numbers in
    `teams`, if given). Returns (paths, notes)."""
    out = Path(out or cfg.get('card', {}).get('output', '.')) / f'{day:%Y-%m-%d}'
    prefix = (cfg.get('tournaments', {}).get('championship') or {}).get('prefix', '')
    teams = {str(t) for t in teams} if teams else None
    pages, paths, notes = Pages(s, cfg), [], []
    for league, tnr in pages.league_list(day):
        _, html, round_day, _ = pages.page(tnr)
        if round_day != day:
            continue
        for pairing in saved_pairings(html):
            side = 'home' if is_ours(pairing['home'], cfg) else 'away' if is_ours(pairing['away'], cfg) else None
            if not side or (teams and team_number(pairing[side]) not in teams):
                continue
            if not pairing['boards'] or any(b['result'] is None for b in pairing['boards']):
                notes.append(f"{pairing['home']} – {pairing['away']}: not entered on Chess-Results yet; no card.")
                continue
            name = league[len(prefix):].strip() if prefix and league.startswith(prefix) else league
            img = draw_card(pairing, day, name, round_number(html), cfg)
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"{day:%Y-%m-%d}-{re.sub(r'[^a-z0-9]+', '-', fold(pairing[side])).strip('-')}.png"
            img.save(path, optimize=True)
            paths.append(str(path))
    if not paths and not notes:
        notes.append(f'No {cfg["club"]} match found for {day}.')
    return paths, notes
