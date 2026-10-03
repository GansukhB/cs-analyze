"""Deciding when two team names mean the same organisation.

The same club reaches this project under several spellings and none of them are
wrong: HLTV writes ``Natus Vincere``, the match server's ``team_clan_name`` says
``NAVI``, a caller types ``navi``, and an event bracket says ``Na'Vi``. Getting
this wrong is expensive and silent -- an unmatched clan name unattributes a whole
match, scores land as 0-0 and its maps belong to nobody, which is the failure
:mod:`app.services.analysis_store` already guards against for the easy cases.

The easy cases are the ones a noise-word strip solves: ``Team Vitality`` and
``Vitality``, ``FaZe Clan`` and ``FaZe``, ``bc.game`` and ``bcgame``. Those
already worked. What did not, and what this module adds:

* **Acronyms.** ``NIP`` is ``Ninjas in Pyjamas``; ``VP`` is ``Virtus.pro``;
  ``EG`` is ``Evil Geniuses``. Derivable from the initials, so they are derived
  rather than listed.
* **Syllabic abbreviations.** ``NaVi`` is ``NA-tus VI-ncere`` -- the first two
  letters of each word, not the initials. Also derivable.
* **Diacritics.** ``KRÜ`` and ``KRU`` are one team. Unicode-folded.
* **The genuinely irregular.** ``MOUZ`` for ``mousesports`` and ``coL`` for
  ``Complexity`` cannot be derived from the letters by any rule that would not
  also merge unrelated clubs. Those are a table, and a short one.

**A wrong merge is far worse than a missed one.** Two clubs collapsed into one
row corrupts every number downstream and is tedious to unpick; a name left
unresolved is visible, logged, and fixed by one :class:`~app.models.TeamAlias` row. So the
matcher is deliberately conservative: it returns a score and the reason it
matched, callers choose a threshold, and a family of suffixes
(:data:`DISTINGUISHING`) hard-blocks a match rather than being folded away --
``Spirit Academy`` is not ``Spirit`` and never should be.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable, Sequence

logger = logging.getLogger(__name__)

# Words an org's name carries in one source and not the other. Stripping them is
# what makes "Team Vitality" and "Vitality" the same string.
# "pro" is deliberately absent: it is noise in "Team Pro" and load-bearing in
# "Virtus.pro", and stripping it turns that org's core into "virtus", which then
# matches nothing it should.
NOISE_WORDS = frozenset(
    {
        "team",
        "esports",
        "esport",
        "gaming",
        "club",
        "clan",
        "the",
        "org",
        "organization",
    }
)

# Words that mean this is a *different* roster wearing the same brand. These are
# never stripped and their presence on one side only blocks the match outright:
# an academy side's numbers in a senior side's report are worse than no numbers.
DISTINGUISHING = frozenset(
    {
        "academy",
        "talent",
        "talents",
        "youth",
        "junior",
        "juniors",
        "young",
        "fe",
        "female",
        "women",
        "womens",
        "girls",
        "gc",
        "b",
        "ii",
        "2",
        "second",
        "reserve",
        "trial",
        "tryout",
        # Academy-tier brands that are not the word "academy": MOUZ NXT, NAVI Junior.
        "nxt",
        "next",
        "prodigy",
        "rising",
        "impact",
        "future",
    }
)

# Small words that an acronym may or may not include -- "Ninjas in Pyjamas" is
# NIP, keeping the "in", while plenty of others drop theirs. Both are generated.
CONNECTIVES = frozenset({"in", "of", "and", "the", "de", "la", "el", "for", "on"})

# The irregular ones. A rule that turned "mousesports" into "mouz" would also
# turn half the server into each other, so these are simply known. Keys and
# values are folded forms; the table is symmetric at load.
_IRREGULAR: dict[str, set[str]] = {
    "mousesports": {"mouz"},
    "complexity": {"col"},
    "ninjasinpyjamas": {"nip"},
    "natusvincere": {"navi", "nv"},
    "virtuspro": {"vp"},
    "evilgeniuses": {"eg"},
    "cloud9": {"c9"},
    "liquid": {"tl"},
    "g2": {"g2esports"},
    "madeinbrazil": {"mibr"},
    "bignetwork": {"big"},
    "berlininternationalgaming": {"big"},
    "eternalfire": {"ef"},
    "gamerlegion": {"gl"},
    "badnewseagles": {"bne"},
    "lynnvision": {"lvg", "lv"},
    "rareatom": {"ra"},
    "wingsup": {"wu"},
    "betboom": {"bb"},
    "9pandas": {"ninepandas"},
    "9z": {"9zteam"},
    "kru": {"kruesports"},
    "ihc": {"ihcesports"},
    "themongolz": {"mongolz", "tmz"},
    "zerotenacity": {"zt"},
    # Nothing speculative belongs here. An invented short form such as "tf" for
    # Falcons or "ts" for Spirit costs nothing when it is never seen and merges
    # an unrelated club the moment some other name derives the same two letters
    # -- "Take Flyte" did exactly that. Only abbreviations the scene actually
    # uses are listed, and the noise-word strip already handles the rest.
}


def _build_alias_index() -> dict[str, set[str]]:
    """Symmetric closure of :data:`_IRREGULAR`, so lookup works either way."""
    index: dict[str, set[str]] = {}
    for canonical, aliases in _IRREGULAR.items():
        group = {canonical} | set(aliases)
        for member in group:
            index.setdefault(member, set()).update(group - {member})
    return index


ALIAS_INDEX = _build_alias_index()

# Anything shorter than this is not a usable key: a one-letter "acronym" from a
# single-word name matches half the database.
MIN_KEY = 2
# ...and a *derived* key needs one more letter than a curated one. Two letters
# is roughly 676 possibilities against a scene of thousands of orgs, so
# generated initials collide constantly: "Take Flyte" and "Team Falcons" both
# produce "tf". Curated aliases stay at MIN_KEY because a human vouched for
# them; anything this module invents must be at least three characters.
MIN_DERIVED_KEY = 3


# ------------------------------------------------------------------ folding ---
def fold(value: str) -> str:
    """Lowercase, strip diacritics, drop everything that is not alphanumeric.

    ``"KRÜ Esports"`` → ``"kruesports"``, ``"bc.game"`` → ``"bcgame"``,
    ``"Na'Vi"`` → ``"navi"``. This is the coarsest key and the one every other
    form is built from.
    """
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch.lower() for ch in text if ch.isalnum())


def words(value: str) -> list[str]:
    """Split into lowercase alphanumeric words, diacritics folded.

    Digits stay attached to the letters they were written with, so ``Cloud9``
    is one word and ``9 Pandas`` is two -- which is what their acronyms follow.
    """
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    return [w for w in text.split() if w]


def core_words(value: str) -> list[str]:
    """Words with the noise removed, but never the distinguishing ones."""
    return [w for w in words(value) if w not in NOISE_WORDS]


def core(value: str) -> str:
    """The name both sources agree on: noise stripped, joined, folded.

    ``"Team Vitality"`` and ``"Vitality"`` both give ``"vitality"``. This is the
    primary key almost every match is decided on.
    """
    return "".join(core_words(value))


def distinguishers(value: str) -> set[str]:
    """Tokens that mark a different roster under the same brand."""
    return {w for w in words(value) if w in DISTINGUISHING}


# --------------------------------------------------------------- prediction ---
def variants(value: str) -> set[str]:
    """Every spelling this organisation plausibly appears under.

    This is the "predict the name" half: rather than comparing two strings with
    a fuzzy distance and hoping, each name is expanded into the forms it could
    legitimately be written as, and a match is an intersection of two such sets.
    That is why ``NAVI`` finds ``Natus Vincere`` -- not because the strings are
    similar, they are not, but because ``natusvincere`` generates ``navi``.

    Generated, in order of how much they are trusted:

    * the folded name and the noise-stripped core
    * the irregular aliases, both directions
    * initials, with and without connectives (``Ninjas in Pyjamas`` → ``nip``,
      ``np``)
    * two- and three-letter syllabic prefixes (``Natus Vincere`` → ``navi``,
      ``natvin``)
    * letter-plus-digit for names ending in a number (``Cloud9`` → ``c9``)
    """
    out: set[str] = set()
    folded, c = fold(value), core(value)
    for key in (folded, c):
        if len(key) >= MIN_KEY:
            out.add(key)

    for key in (folded, c):
        out.update(a for a in ALIAS_INDEX.get(key, ()) if len(a) >= MIN_KEY)

    derived: set[str] = set()
    cw = core_words(value)
    if len(cw) >= 2:
        # Initials, keeping and dropping the connectives.
        derived.add("".join(w[0] for w in cw))
        derived.add("".join(w[0] for w in cw if w not in CONNECTIVES))
        # Syllabic: the first n letters of each word. NAVI is this, not initials.
        for n in (2, 3):
            derived.add("".join(w[:n] for w in cw if w not in CONNECTIVES))

    # "Cloud9" -> "c9". Only when letters are followed by digits.
    for word in cw:
        m = re.fullmatch(r"([a-z]+)(\d+)", word)
        if m and len(m.group(1)) >= 3:
            derived.add(m.group(1)[0] + m.group(2))

    out.update(k for k in derived if len(k) >= MIN_DERIVED_KEY)
    return {v for v in out if len(v) >= MIN_KEY}


# ------------------------------------------------------------------ matching ---
# What a match was decided on, strongest first. Callers that need to explain
# themselves (and the merge command does) print this rather than a bare score.
EXACT = "exact"
CORE = "core"
ALIAS = "known alias"
PREDICTED = "predicted variant"
CONTAINS = "one name contains the other"

_SCORES = {EXACT: 1.0, CORE: 0.97, ALIAS: 0.93, PREDICTED: 0.85, CONTAINS: 0.72}


def compare(left: str, right: str) -> tuple[float, str]:
    """How confident are we that these two names are the same club.

    Returns ``(score, reason)``; ``0.0`` means no. The distinguishing-suffix
    check runs first and short-circuits, because "Spirit Academy" scores
    extremely well against "Spirit" on every other test and is still a different
    team.
    """
    if not (left or "").strip() or not (right or "").strip():
        return 0.0, ""

    if distinguishers(left) != distinguishers(right):
        return 0.0, "different roster tier"

    if fold(left) == fold(right):
        return _SCORES[EXACT], EXACT

    left_core, right_core = core(left), core(right)
    if left_core and left_core == right_core:
        return _SCORES[CORE], CORE

    if right_core in ALIAS_INDEX.get(left_core, ()) or left_core in ALIAS_INDEX.get(right_core, ()):
        return _SCORES[ALIAS], ALIAS

    if variants(left) & variants(right):
        return _SCORES[PREDICTED], PREDICTED

    # Weakest test, and the one that needs a length floor: "9z" is inside
    # "9z Team" legitimately, but two-letter cores are inside far too much.
    if len(left_core) >= 4 and len(right_core) >= 4:
        if left_core in right_core or right_core in left_core:
            return _SCORES[CONTAINS], CONTAINS

    return 0.0, ""


def equivalent(left: str, right: str, threshold: float = 0.8) -> bool:
    """Would we treat these two names as the same organisation."""
    return compare(left, right)[0] >= threshold


def resolve(
    name: str, candidates: Iterable, *, key=lambda t: t.name, threshold: float = 0.8
) -> tuple[object, float, str] | None:
    """Best candidate for ``name``, or None. Returns ``(candidate, score, why)``.

    Ties are broken by the longer stored name, on the reasoning that
    ``"Natus Vincere"`` is the record and ``"NAVI"`` is the nickname, so when
    both are present the fuller one is the row worth keeping.
    """
    best: tuple[object, float, str] | None = None
    for candidate in candidates:
        if candidate is None:
            continue
        score, why = compare(name, key(candidate))
        if score < threshold:
            continue
        if best is None or (score, len(key(candidate) or "")) > (best[1], len(key(best[0]) or "")):
            best = (candidate, score, why)
    return best


def group_duplicates(names: Sequence[str], threshold: float = 0.8) -> list[list[int]]:
    """Cluster indices of ``names`` that refer to one organisation.

    Single-linkage: A matches B and B matches C puts all three together even if
    A and C would not have matched directly. That is the right shape here --
    ``NAVI`` ↔ ``Natus Vincere`` ↔ ``Na'Vi`` is one club -- but it is also how a
    bad pair contaminates a whole cluster, which is why the merge command shows
    the reason for every pair before touching anything.
    """
    parent = list(range(len(names)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if compare(names[i], names[j])[0] >= threshold:
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for i in range(len(names)):
        clusters.setdefault(find(i), []).append(i)
    return [sorted(v) for v in clusters.values() if len(v) > 1]
