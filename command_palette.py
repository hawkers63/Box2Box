"""The command palette: what it offers, how a typed query finds it and how results are ranked.

The matching is pure and has no window code, so it is tested on its own. The overlay that shows it
(CommandPalette) is at the foot of this module and is built by the main window.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

COMPETITION, CLUB, VIEW, SPLIT, ACTION = "Competition", "Club", "View", "Split", "Action"
RESULT_LIMIT = 12                                   # results shown at once
_KIND_ORDER = {kind: order for order, kind in enumerate((VIEW, SPLIT, ACTION, CLUB, COMPETITION))}
_OFFERED_WITHOUT_A_QUERY = (VIEW, SPLIT, ACTION)    # five thousand clubs are not a menu


@dataclass(frozen=True, slots=True)
class PaletteItem:
    """One thing the palette can do. `priority` lifts an item within its tier (the open competition's
    own clubs); `detail` is a second line shown beside the title, such as a club's competition."""

    kind: str
    title: str
    detail: str = ""
    action: Callable[[], None] | None = None
    priority: int = 0


def fold(text: str) -> str:
    """Text folded for matching: accents, case and punctuation gone, words separated by one space.
    Unlike the club-colour matching it keeps every word ('FC' and 'United' included)."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]", " ", plain.casefold()).split())


def _letters_of(query_word: str, title_word: str) -> bool:
    """True when the query word is the title word's first letter followed by some of its later letters
    in order: 'utd' in 'united'."""
    if not query_word or query_word[0] != title_word[:1]:
        return False
    rest = iter(title_word[1:])
    return all(letter in rest for letter in query_word[1:])


def _tier(query: str, words: list[str], title: str) -> int | None:
    """0 the exact title, 1 every query word starts a title word, 2 every query word starts a title word
    or abbreviates one ('utd'), 3 the query occurs inside the title; None for no match."""
    if title == query:
        return 0
    title_words = title.split()
    if all(any(t.startswith(q) for t in title_words) for q in words):
        return 1
    if all(any(t.startswith(q) or _letters_of(q, t) for t in title_words) for q in words):
        return 2
    if query in title:
        return 3
    return None


def search(items: Sequence[PaletteItem], query: str, limit: int = RESULT_LIMIT) -> list[PaletteItem]:
    """The items a query finds, best first and at most `limit`. A query with nothing to match (empty,
    spaces, punctuation) offers views, splits and actions in the order given. Within a tier a higher
    priority comes first, then views, splits, actions, clubs, competitions, then the title."""
    folded = fold(query)
    if not folded:
        return [i for i in items if i.kind in _OFFERED_WITHOUT_A_QUERY][:limit]
    words = folded.split()
    ranked = []
    for entry in items:
        title = fold(entry.title)
        tier = _tier(folded, words, title)
        if tier is not None:
            ranked.append(((tier, -entry.priority, _KIND_ORDER.get(entry.kind, len(_KIND_ORDER)), title), entry))
    ranked.sort(key=lambda pair: pair[0])
    return [entry for _, entry in ranked[:limit]]
