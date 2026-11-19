# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
"""Football clubs' colours, for the followed club's tint in the window and the exports.

Saves hold no club colours, so these are written by hand: a club's main and second colour, keyed on
its name as Football Manager spells it. Names match after folding case, accents, "&", punctuation
and "FC", "AFC" or "CF", and nothing looser, so a club is never given another club's colours. Edits
made in the app are kept in the settings file, not here, and win over this list. No UI code.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_DROPPED_WORDS = {"fc", "afc", "cf"}

RED_WHITE = ("#e2001a", "#ffffff")

CLUB_COLOURS: dict[str, tuple[str, str]] = {
    # Premier League
    "AFC Bournemouth": ("#da291c", "#000000"),
    "Arsenal": ("#ef0107", "#ffffff"),
    "Aston Villa": ("#670e36", "#95bfe5"),
    "Brentford": ("#e30613", "#ffffff"),
    "Brighton & Hove Albion": ("#0057b8", "#ffffff"),
    "Chelsea": ("#034694", "#ffffff"),
    "Coventry City": ("#59b9e6", "#ffffff"),
    "Crystal Palace": ("#1b458f", "#c4122e"),
    "Everton": ("#003399", "#ffffff"),
    "Fulham": ("#ffffff", "#000000"),
    "Hull City": ("#f5a12d", "#000000"),
    "Ipswich Town": ("#0044a9", "#ffffff"),
    "Leeds United": ("#ffffff", "#1d428a"),
    "Liverpool": ("#c8102e", "#ffffff"),
    "Manchester City": ("#6cabdd", "#ffffff"),
    "Manchester United": ("#da291c", "#ffffff"),
    "Newcastle United": ("#241f20", "#ffffff"),
    "Nottingham Forest": ("#e53233", "#ffffff"),
    "Sunderland": ("#eb172b", "#ffffff"),
    "Tottenham Hotspur": ("#ffffff", "#132257"),
    # Championship
    "Birmingham City": ("#0047ab", "#ffffff"),
    "Blackburn Rovers": ("#009ee0", "#ffffff"),
    "Bolton Wanderers": ("#ffffff", "#263c7e"),
    "Bristol City": ("#e21a23", "#ffffff"),
    "Burnley": ("#6c1d45", "#99d6ea"),
    "Cardiff City": ("#0070b5", "#ffffff"),
    "Charlton Athletic": ("#d4021d", "#ffffff"),
    "Derby County": ("#ffffff", "#000000"),
    "Lincoln City": ("#e1261c", "#ffffff"),
    "Middlesbrough": ("#e11b22", "#ffffff"),
    "Millwall": ("#001d5e", "#ffffff"),
    "Norwich City": ("#fff200", "#00a650"),
    "Portsmouth": ("#001489", "#ffffff"),
    "Preston North End": ("#ffffff", "#0a2240"),
    "Queens Park Rangers": ("#1d5ba4", "#ffffff"),
    "Sheffield United": ("#ee2737", "#ffffff"),
    "Southampton": ("#d71920", "#ffffff"),
    "Stoke City": ("#e03a3e", "#ffffff"),
    "Swansea City": ("#ffffff", "#000000"),
    "Watford": ("#fbee23", "#000000"),
    "West Bromwich Albion": ("#122f67", "#ffffff"),
    "West Ham United": ("#7a263a", "#1bb1e7"),
    "Wolverhampton Wanderers": ("#fdb913", "#231f20"),
    "Wolverhamption Wanderers": ("#fdb913", "#231f20"),     # as some saves spell it
    "Wrexham": ("#d71920", "#ffffff"),
    # League One
    "AFC Wimbledon": ("#002e7d", "#fff200"),
    "Barnsley": ("#d71920", "#ffffff"),
    "Blackpool": ("#f68712", "#ffffff"),
    "Bradford City": ("#8b0e3a", "#f5b324"),
    "Bromley": ("#ffffff", "#000000"),
    "Burton Albion": ("#fdd600", "#000000"),
    "Cambridge United": ("#f9a01b", "#000000"),
    "Doncaster Rovers": ("#e1241f", "#ffffff"),
    "Huddersfield Town": ("#0e63ad", "#ffffff"),
    "Leicester City": ("#003090", "#ffffff"),
    "Leyton Orient": ("#e41e2b", "#ffffff"),
    "Luton Town": ("#f78f1e", "#002d62"),
    "Mansfield Town": ("#f5a623", "#00529f"),
    "Milton Keynes Dons": ("#ffffff", "#000000"),
    "Notts County": ("#000000", "#ffffff"),
    "Oxford United": ("#fff200", "#002d62"),
    "Peterborough United": ("#0055a5", "#ffffff"),
    "Plymouth Argyle": ("#00573f", "#ffffff"),
    "Reading": ("#004494", "#ffffff"),
    "Sheffield Wednesday": ("#2b56a2", "#ffffff"),
    "Stevenage": RED_WHITE,
    "Stockport County": ("#0057a5", "#ffffff"),
    "Wigan Athletic": ("#1d59af", "#ffffff"),
    "Wycombe Wanderers": ("#6cace4", "#00205b"),
    # League Two
    "Accrington Stanley": RED_WHITE,
    "Barnet": ("#f7a823", "#000000"),
    "Bristol Rovers": ("#0055a5", "#ffffff"),
    "Cheltenham Town": RED_WHITE,
    "Chesterfield": ("#0047ab", "#ffffff"),
    "Colchester United": ("#0055a5", "#ffffff"),
    "Crawley Town": RED_WHITE,
    "Crewe Alexandra": ("#d71920", "#ffffff"),
    "Exeter City": RED_WHITE,
    "Fleetwood Town": RED_WHITE,
    "Gillingham": ("#1c3f94", "#ffffff"),
    "Grimsby Town": ("#000000", "#ffffff"),
    "Newport County": ("#f7a823", "#000000"),
    "Northampton Town": ("#7a1f2e", "#ffffff"),
    "Oldham Athletic": ("#0055a5", "#ffffff"),
    "Port Vale": ("#ffffff", "#000000"),
    "Rochdale": ("#0057b8", "#000000"),
    "Rotherham United": RED_WHITE,
    "Salford City": RED_WHITE,
    "Shrewsbury Town": ("#0055a5", "#f7a823"),
    "Swindon Town": RED_WHITE,
    "Tranmere Rovers": ("#ffffff", "#003da5"),
    "Walsall": RED_WHITE,
    "York City": ("#d71920", "#1b2a4a"),
    # Former league clubs that may come back up
    "Carlisle United": ("#0055a5", "#ffffff"),
    "Forest Green Rovers": ("#7ac143", "#000000"),
    "Harrogate Town": ("#fdd600", "#000000"),
    "Hartlepool United": ("#0055a5", "#ffffff"),
    "Morecambe": RED_WHITE,
    "Scunthorpe United": ("#8b1538", "#6cace4"),
    "Southend United": ("#0047ab", "#ffffff"),
    "Sutton United": ("#f7a823", "#5c3317"),
    # Spain
    "Real Madrid": ("#ffffff", "#00529f"),
    "FC Barcelona": ("#a50044", "#004d98"),
    "Atletico Madrid": ("#cb3524", "#ffffff"),
    "Athletic Club Bilbao": ("#ee2523", "#ffffff"),
    "Real Sociedad": ("#0067b1", "#ffffff"),
    "Real Betis": ("#00954c", "#ffffff"),
    "Sevilla FC": ("#ffffff", "#d81920"),
    "Valencia CF": ("#ffffff", "#000000"),
    "Villarreal": ("#ffe667", "#005187"),
    # Germany
    "Bayern Munchen": ("#dc052d", "#ffffff"),
    "Borussia Dortmund": ("#fde100", "#000000"),
    "Bayer 04 Leverkusen": ("#e32221", "#000000"),
    "RasenBallsport Leipzig": ("#ffffff", "#dd0741"),
    "Eintracht Frankfurt": ("#e1000f", "#000000"),
    "VfB Stuttgart": ("#ffffff", "#e32219"),
    # Italy
    "Juventus": ("#ffffff", "#000000"),
    "Juventus FC": ("#ffffff", "#000000"),
    "AC Milan": ("#fb090b", "#000000"),
    "Internazionale": ("#0068a8", "#000000"),
    "FC Internazionale Milano": ("#0068a8", "#000000"),
    "Napoli": ("#12a0d7", "#ffffff"),
    "Roma": ("#8e1f2f", "#f0bc42"),
    "Associazione Sportiva Roma": ("#8e1f2f", "#f0bc42"),
    "Lazio": ("#87d8f7", "#ffffff"),
    "Atalanta": ("#1e71b8", "#000000"),
    "Fiorentina": ("#482e92", "#ffffff"),
    "ACF Fiorentina": ("#482e92", "#ffffff"),
    # France
    "Paris Saint-Germain": ("#004170", "#da291c"),
    "Olympique Marseille": ("#ffffff", "#2faee0"),
    "Olympique Lyonnais": ("#ffffff", "#14387f"),
    "AS Monaco": ("#e51b22", "#ffffff"),
    "Lille Olympique": ("#e01e13", "#ffffff"),
    # Portugal
    "SL Benfica": ("#e83030", "#ffffff"),
    "FC Porto": ("#00428c", "#ffffff"),
    "Sporting CP": ("#008057", "#ffffff"),
    "SC Braga": RED_WHITE,
    # The Netherlands
    "AFC Ajax": ("#d2122e", "#ffffff"),
    "PSV Eindhoven": ("#ed1c24", "#ffffff"),
    "Feyenoord Rotterdam": ("#e3001b", "#ffffff"),
    "AZ Alkmaar": ("#db0021", "#ffffff"),
    # Scotland
    "Celtic": ("#018749", "#ffffff"),
    "Rangers": ("#1b458f", "#ffffff"),
    "Aberdeen": RED_WHITE,
    "Heart of Midlothian": ("#8a1538", "#ffffff"),
    "Hibernian": ("#005f2e", "#ffffff"),
    # Turkey
    "Galatasaray": ("#a90432", "#fdb912"),
    "Fenerbahce": ("#163962", "#ffed00"),
    "Besiktas": ("#000000", "#ffffff"),
    "Trabzonspor": ("#a41d34", "#41b6e6"),
}


def normalise(name: str) -> str:
    """A club name folded for matching: 'AFC Bournemouth' and 'bournemouth' are the same club."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold().replace("&", " and ")
    return " ".join(word for word in re.sub(r"[^\w\s]", " ", text).split() if word not in _DROPPED_WORDS)


_BY_KEY = {normalise(name): colours for name, colours in CLUB_COLOURS.items()}


def builtin_colours(name: str | None) -> tuple[str, str] | None:
    """The club's colours from the list above, or None for a club it does not know."""
    return _BY_KEY.get(normalise(name)) if name else None


def initials(name: str | None) -> str:
    """Up to two letters for a club's roundel: the first letters of its first two words, or the first two of a
    one-word name. Club words (FC, AFC, CF), a "(team 2)" suffix and numbers are set aside; none left gives ""."""
    if not name:
        return ""
    words = [w for w in normalise(re.sub(r"\(.*?\)", " ", name)).split() if not w.isdigit()]
    if not words:
        return ""
    return (words[0][0] + words[1][0] if len(words) > 1 else words[0][:2]).upper()


def _is_pair(value: object) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(isinstance(colour, str) and _HEX.match(colour) for colour in value))


def colours_for(name: str | None, edits: object) -> tuple[str, str] | None:
    """The club's colours: Mark's edit if he made one (two colours, or None for none), otherwise
    the list's. An edit that is not two '#rrggbb' colours or None is ignored."""
    if not name:
        return None
    if isinstance(edits, Mapping):
        key = normalise(name)
        for club, value in edits.items():
            if isinstance(club, str) and normalise(club) == key:
                if value is None:
                    return None
                if _is_pair(value):
                    return (value[0], value[1])
                break
    return builtin_colours(name)
