"""The Assistant (CONTEXT.md): Claude, reading the analysis tables through tools.

Ported from cstat's ``hltv/services/assistant.py``. This is deliberately not
another report builder. Every fact it can state comes from a tool call into the
report builders that already exist -- :mod:`app.services.gameplan`,
:mod:`app.services.scouting`, :mod:`app.services.roles`,
:mod:`app.services.mapstrategy` -- the same modules the pages render. The chat's
job is orchestration and wording, not a second copy of the numbers.

``context`` tells the Assistant what page it was opened from: a Game Plan
(a Fixture, with each side's Lineup), a Team page or a Match page, so "what's our
T-side plan here" resolves without a tool round trip. With no context it is the
generic form, and ``list_teams``/``team_overview`` are how it finds its feet.

The conversation is stateless on the server: the browser resends the transcript
every turn, trimmed to plain ``{"role", "content"}`` text pairs, never the
``tool_use``/``tool_result`` blocks a turn generates internally. Those are cheap
DB reads, not paid tokens, so nothing needs a session model. Within a turn the
messages only grow (each round appends the model's content and the tool
results), which keeps the model's thinking blocks valid from round to round.

Nothing waits for the whole answer. Every round streams: text is cut into
paragraphs the moment a blank line closes one, and each paragraph is voiced and
yielded right then. A tool call is reported the instant it is seen, because a
silent gap reads as a stall.

:func:`chat_events` runs inside a streamed response, which Starlette iterates
from the threadpool with a fresh copy of the context on every step. So the
analysis session and the Lineups are bound around each tool call only
(:func:`_execute_tool`), never across a ``yield``.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import uuid
from collections.abc import Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import get_settings
from app.models import (
    AnalysisJob,
    GameMap,
    JobStatus,
    MapRoster,
    Match,
    MatchMap,
    Player,
    Round,
    Team,
)
from app.services import (
    after_contact,
    dbctx,
    decision,
    forecast,
    grounding,
    jobs,
    lineup,
    mapstrategy,
    mn,
    playbook_view,
    player_page,
    review_view,
    roles,
    round_search,
    scouting,
    scrim_log,
    strat_match,
    voice,
)
from app.services import gameplan as gameplan_service

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_MESSAGE_CHARS = 2000
TOOL_RESULT_CHAR_LIMIT = 12_000  # guard against one tool call blowing the budget

# List prices, USD per million tokens: input, output, cache read, cache write
# (a 5-minute write is 1.25x input). October 2026; a model not listed is costed
# as Sonnet. Only the cap and the bill read them, never the answer.
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.50),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.00),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}


@dataclass
class Usage:
    """What one chat turn spent, added up over its tool rounds."""

    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    tool_rounds: int = 0
    tts_chars: int = 0
    # Not stored: the tools called, and the numbers no tool gave (AS-4's eval).
    tools: list = field(default_factory=list)
    unchecked: list = field(default_factory=list)

    def add(self, usage) -> None:
        if usage is None:
            return
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_read_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.cache_write_tokens += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)

    def cost_usd(self) -> float:
        price_in, price_out, price_read, price_write = PRICES.get(
            self.model, PRICES["claude-sonnet-5-5"]
        )
        return (
            self.input_tokens * price_in
            + self.output_tokens * price_out
            + self.cache_read_tokens * price_read
            + self.cache_write_tokens * price_write
        ) / 1_000_000


# Opt-in server-side retry when the model declines (Claude API only).
FALLBACK_BETA = "server-side-fallback-2026-07-01"


# Standard CS2 terms kept in English no matter what language the Assistant
# replies in -- see the "terminology" ground rule below.
CS2_TERMS = {
    "match & format": ("map", "veto", "H2H", "Bo1", "Bo3", "Bo5", "LAN", "overtime", "MR12"),
    "round phases": (
        "pistol round", "eco", "force buy", "full buy", "save round",
        "default", "execute", "retake", "rush",
    ),
    "bomb": ("bomb plant", "defuse", "site A", "site B"),
    "movement & combat": (
        "peek", "trade", "clutch", "entry", "lurk", "rotate", "boost",
        "stack", "smoke", "flash", "molotov", "incendiary",
    ),
    "roles": (
        "AWP", "entry fragger", "lurker", "support", "anchor", "rotator", "trader", "IGL",
    ),
    "stats": ("ADR", "K/D", "rating", "opening duel", "first kill", "multi-kill"),
    "other": ("player",),
}  # fmt: skip


def _glossary_line() -> str:
    return ", ".join(term for terms in CS2_TERMS.values() for term in terms)


SYSTEM_PROMPT = f"""You are the cs-analyze scouting assistant, embedded in a Counter-Strike \
analysis tool built on parsed demo data (not opinion, not memory -- every \
number you state has to come from a tool call).

Ground rules:
- Reply in whatever language the user's most recent message is written in -- \
never default to English just because this system prompt, an earlier turn, or \
a tool result happens to be in English. Detect the language fresh on every \
turn from the message you were just sent, and answer entirely in that \
language (standard CS2 terms excepted -- see below). This rule outranks \
matching the language of anything else in the conversation.
- Never state a statistic, record, role, or verdict from memory. Call a tool \
for it. If no tool covers the question, say so plainly instead of guessing.
- Every claim carries its sample size the way the tools already report it \
(rounds, maps, duels). A team with two parsed maps is not "clearly weak", it \
is "weak on a two-map sample" -- say the second part.
- If a tool returns an error (unknown team id, no parsed data), tell the user \
what is missing rather than inventing a plausible-sounding answer around it.
- Prefer the most specific tool: gameplan_section for a two-team fixture \
question, team_overview/map_strategy/role_report for a single team, \
scouting_report for head-to-head threats and tendencies. For "what should we \
exploit / watch out for / how do we beat them on <map>", read \
gameplan_section 'levers' first: it is the Playbook's own list of Levers and \
Cautions, ranked, with the numbers behind each. For "can we win / what are our \
chances" use forecast, and for one player player_form; team_matches finds a \
team's latest Match ids. "What do they do after the opening / do they rotate / \
how do they retake" is after_contact; "find rounds where..." is find_rounds; \
the user's own strats are stratbook, their practice matches scrims.
- Write the reply as short paragraphs (2-4 sentences each) separated by a \
blank line. Each paragraph is read aloud as its own unit by a text-to-speech \
voice, so keep one idea per paragraph and avoid bullet lists, headings, or \
markdown -- write for the ear, not the eye.
- The text-to-speech voice does not officially support every language \
(Mongolian included), so a bare symbol in an unsupported language gets sounded \
out using a *different* language's pronunciation rules -- most visibly, "%" and \
a bare decimal point read with a Russian accent in Mongolian text. Avoid that \
failure mode by never leaving a symbol for the voice to guess at: spell out "%" \
as the word for percent in whatever language you are replying in (Mongolian \
"хувь", not the "%" sign), and prefer whole numbers over decimals when the \
fractional part is not the point -- "54.9%" becomes "54.9 хувь" only if the \
decimal itself matters, and "55 хувь" if it does not. The same rule applies to \
any other language the voice does not fully support.
- Keep standard CS2 terminology in its English form no matter what language \
you are replying in. These are the game's own vocabulary, not English words \
that happen to need translating -- a Mongolian sentence with "bomb plant" or \
"veto" left in English reads normally to a player, while a translated or \
transliterated version of the same word reads as wrong. Never translate or \
transliterate: {_glossary_line()}. Everything else in the sentence -- grammar, \
particles, the words around them -- follows the reply language as normal; \
only these terms themselves stay untouched.
- In Mongolian, a player blinded by a flash is "цайрсан" and one who blinded \
someone "цайруулсан" (and their other forms: цайрч, цайруулж, цайруулав). \
Never write "сохор", "сохорсон" or "сохорлосон". A teammate is "багийн \
гишүүн" (plural "багийн гишүүд"), never "нөхөр" or "нөхөд".
- Keep the whole reply to at most about five paragraphs unless the user \
explicitly asks for more detail.
- When a tool hands you a specific Round (a Finding's round and second, a \
Playbook or Summary evidence ref), you may point at it with a Round token, \
which the page turns into a link that opens the Replay there: [R14] for Round \
14 of the Match Map the conversation is about (the one match_review read, or \
the match page open), [R14 1:23] for a moment of it, [R14 1:23 @<steamid>] to \
ring that player; for any other Match Map put the match id and map number \
first, [4021.2:R14]. Only rounds, ids and seconds a tool returned. The voice \
reads a token as the round's number, so don't also say the number in words \
beside it, and use at most three tokens in a paragraph.
- When you need a tool, call it directly with no preamble -- don't write "let \
me check" or similar before a tool call. The interface already shows the user \
which lookup is running; text you write in that turn would be read aloud as \
if it were part of the answer."""


# ------------------------------------------------------------------ tools ----
TOOLS = [
    {
        "name": "list_teams",
        "description": (
            "Search the known teams by name, or list the ones with parsed maps "
            "when no query is given. Use this first when the user names a team "
            "you don't already have an id for."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Case-insensitive substring match on the team name. "
                    "Empty to list the most-covered teams.",
                },
            },
        },
    },
    {
        "name": "team_overview",
        "description": (
            "One team's results record, per-map win rate, and current roster. "
            "The general-purpose starting point for any single-team question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"team_id": {"type": "integer"}},
            "required": ["team_id"],
        },
    },
    {
        "name": "map_strategy",
        "description": (
            "Veto guidance for one team's map pool (strong/weak/untested maps), or, "
            "when an opponent is given, the head-to-head map board plus a CT/T "
            "tactical plan per map: pistol rate, plant tempo and site split, "
            "retake record."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer"},
                "opponent_id": {
                    "type": "integer",
                    "description": "Optional. Adds the veto board and per-map "
                    "CT/T plans for this fixture.",
                },
            },
            "required": ["team_id"],
        },
    },
    {
        "name": "role_report",
        "description": (
            "Who plays which job (entry, AWP, lurker, support, anchor, rotator, "
            "trader) on a team, rated against every player in the database who does "
            "the same job. Add an opponent to get a role-for-role comparison "
            "between the two sides instead of one team alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer"},
                "opponent_id": {"type": "integer"},
            },
            "required": ["team_id"],
        },
    },
    {
        "name": "scouting_report",
        "description": (
            "Head-to-head scouting between two teams: underperforming players on "
            "our side, dangerous players on theirs, exploitable tendencies, and the "
            "player-vs-player duel record. Requires parsed maps between the two "
            "teams for the head-to-head part."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer", "description": "The team being scouted for."},
                "opponent_id": {"type": "integer"},
            },
            "required": ["team_id", "opponent_id"],
        },
    },
    {
        "name": "gameplan_section",
        "description": (
            "One section of the full match-preparation report for a fixture "
            "(the same report the game-plan page renders). Sections: 'verdict' "
            "(the headline call and top actions), 'board' (map veto board), "
            "'map_plans' (per-map CT/T plans), 'roles' (role-for-role fit gap), "
            "'players' (both rosters with per-player scouting instructions), "
            "'duels' (player-vs-player kill totals), 'linchpins' (who each team "
            "cannot afford to lose early), 'man_advantage' (how each side closes a "
            "numbers lead), 'continuity' (how much of the current roster set the "
            "head-to-head record), 'my_delta'/'opponent_delta' (own form vs form "
            "against this opponent), 'sample'/'lede' (how much data this is built on), "
            "'levers' (per map, from both teams' match reviews against the pool: the "
            "Levers -- what to exploit, my strengths meeting their weaknesses first -- "
            "and the Cautions -- what to watch out for, their strengths meeting my "
            "weaknesses first -- per side, each with its numbers, counter and evidence "
            "strength, plus the limits of the data; give 'map' such as 'de_inferno' for "
            "one map, or leave it out for the top lines of every map the veto makes likely), "
            "'decision' (the call from the Forecast, its lead, the four cards and three "
            "moves), 'playbook' (one map's Playbook: their habits with counters, our plan, "
            "pistols, players; give 'map')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mine_id": {"type": "integer"},
                "theirs_id": {"type": "integer"},
                "section": {"type": "string"},
                "map": {
                    "type": "string",
                    "description": "For 'levers' and 'playbook', e.g. de_inferno.",
                },
            },
            "required": ["mine_id", "theirs_id", "section"],
        },
    },
    {
        "name": "match_summary",
        "description": (
            "Each team's Summary of a whole match, the way a coach or analyst would "
            "debrief it: one line per map (score, the main strength and problem of each "
            "team), the strengths and problems that repeated on two maps or more, each "
            "team's top Focus points (what to work on, costliest first, with advice) and "
            "its players' Swing over the match. Use it for 'how did this match go', 'what "
            "should this team work on', or any question about the match as a whole; use "
            "match_review for one map's rounds and findings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"match_id": {"type": "integer"}},
            "required": ["match_id"],
        },
    },
    {
        "name": "match_review",
        "description": (
            "The Review of one parsed map of a match: each team's Summary of the map "
            "(its numbers, what went well, what went wrong, Focus points), round by "
            "round who won it and how, each player's Swing (how much their actions moved "
            "their team's round win probability), and the Findings -- key plays, "
            "mistakes, missed chances and utility effects -- each with its round, time "
            "and Swing. Use it for questions about how a specific map was played: why a "
            "round was lost, who made mistakes, which frags or utility mattered."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer"},
                "map_number": {
                    "type": "integer",
                    "description": "Which map of the match (1, 2, 3). Defaults to the first "
                    "parsed one.",
                },
                "round": {"type": "integer", "description": "Only this round's Findings."},
                "player": {
                    "type": "string",
                    "description": "Only Findings about this player (case-insensitive name).",
                },
                "kind": {
                    "type": "string",
                    "enum": ["key_play", "mistake", "missed_chance", "utility"],
                },
            },
            "required": ["match_id"],
        },
    },
    {
        "name": "team_matches",
        "description": (
            "A team's latest Matches, newest first, with match_id, date, opponent, score "
            "and which maps are parsed. Use it to find 'the last match' or a match to open "
            "with match_summary or match_review."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer"},
                "limit": {"type": "integer", "description": "At most 20; 10 by default."},
            },
            "required": ["team_id"],
        },
    },
    {
        "name": "player_form",
        "description": (
            "One player's page: the teams he played for, his totals (rounds, ADR, KAST, "
            "opening duels, Swing per round from the reviews), his numbers by map and "
            "side, the Findings he gets most per 24 rounds against every player's rate, "
            "and his latest maps' form. Give his Steam id as a string (from match_review "
            "or the players section) or his name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "steamid": {"type": "string"},
                "name": {"type": "string", "description": "Case-insensitive, if no Steam id."},
            },
        },
    },
    {
        "name": "forecast",
        "description": (
            "The Forecast for a fixture: both teams' Ratings (an Elo over every series "
            "Valve's regional standings counted, with its sample and region), our chance "
            "of winning a Bo1, Bo3 and Bo5 with how often such forecasts came true, the "
            "maps each team played lately, and the limits of the model. Say chances "
            "rounded to 5 points, as the page does."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"mine_id": {"type": "integer"}, "theirs_id": {"type": "integer"}},
            "required": ["mine_id", "theirs_id"],
        },
    },
    {
        "name": "rating",
        "description": "One team's Rating, how many series it rests on and when it last moved.",
        "input_schema": {
            "type": "object",
            "properties": {"team_id": {"type": "integer"}},
            "required": ["team_id"],
        },
    },
    {
        "name": "find_rounds",
        "description": (
            "Find Rounds where one side stood a certain way: e.g. 'T with 2+ in Apartments "
            "between 15 and 30 s'. Each condition is a Callout (the game's place name), how "
            "many of that side were there (min, max) and a window of seconds after freeze "
            "end; every condition must hold at some second of its window (give or take 2 s). "
            "Returns how many Rounds were looked at, matched and won by that side, and the "
            "newest Rounds with their match id and map number. Call it with no conditions to "
            "get the map's Callout names first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "map_name": {"type": "string", "description": "e.g. de_mirage"},
                "side": {"type": "string", "enum": ["t", "ct"]},
                "team_id": {"type": "integer", "description": "Only this team's Rounds."},
                "buy": {"type": "string", "enum": ["full", "light"]},
                "score": {
                    "type": "string",
                    "enum": ["ahead", "close", "behind"],
                    "description": "That side's team 2+ rounds ahead, within 1, or 2+ behind.",
                },
                "conditions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "place": {"type": "string"},
                            "min": {"type": "integer"},
                            "max": {"type": "integer"},
                            "start": {"type": "integer"},
                            "end": {"type": "integer"},
                        },
                        "required": ["place"],
                    },
                },
            },
            "required": ["map_name", "side"],
        },
    },
    {
        "name": "after_contact",
        "description": (
            "What a team does after the first contact on one map: for each opening (the "
            "round's first kill, won or lost, at A, mid or B) where the bomb then went down "
            "(A, B or not at all) and how many of those rounds it won; on T where most of "
            "them stood at 20 s and whether they planted the other site (a rotate), plant "
            "timing, and where they sat after the plant; on CT, after losing the opening at "
            "a site, how often another CT reached it within 10 s, and retakes by the numbers "
            "left at the plant."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"team_id": {"type": "integer"}, "map_name": {"type": "string"}},
            "required": ["team_id", "map_name"],
        },
    },
    {
        "name": "stratbook",
        "description": (
            "The user's own Stratbook: the strats their staff wrote (name, map, side, kind, "
            "status) and how each did in the rounds it was found in (played, won, a range). "
            "Optionally one of their teams or one map."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"team_id": {"type": "integer"}, "map_name": {"type": "string"}},
        },
    },
    {
        "name": "scrims",
        "description": (
            "The user's own team's Scrim log, newest first: the partner, each map's score "
            "and what its Summary says to work on. Scrims are private practice: never "
            "compare them with official results as if they were the same."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer", "description": "Defaults to the first own team."},
                "limit": {"type": "integer", "description": "At most 10; 5 by default."},
            },
        },
    },
]


# AS-8: what a Player login's Assistant can call, each held to their own play.
PLAYER_TOOLS = [
    {
        "name": "player_form",
        "description": (
            "The user's own player page: their totals, numbers by map and side, the "
            "Findings they get most per 24 rounds against every player's rate, and their "
            "latest maps' form. Takes no arguments."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "my_matches",
        "description": "The user's latest parsed Match Maps, newest first, with their ids.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "At most 20."}},
        },
    },
    next(t for t in TOOLS if t["name"] == "match_review"),
    {
        "name": "my_goals",
        "description": (
            "The user's active Development goals: the KPI, its target and due date, where "
            "it stands now and whether it is reached."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "my_briefings",
        "description": (
            "Briefings the staff shared with the team: with no id the list, with an id one "
            "Briefing's notes and lines per map."
        ),
        "input_schema": {"type": "object", "properties": {"briefing_id": {"type": "string"}}},
    },
]


class UnknownTeam(Exception):
    """A tool was given a team id the database doesn't have."""


def _team(team_id: int) -> Team:
    team = dbctx.db().get(Team, team_id)
    if team is None:
        raise UnknownTeam(team_id)
    return team


def _parsed_map_counts() -> dict[int, int]:
    """``{team_id: n}`` parsed maps, in one query."""
    counts: dict[int, set] = {}
    rows = dbctx.db().execute(
        select(Round.ct_team_id, Round.t_team_id, Round.match_map_id)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .where(MatchMap.parsed_at.is_not(None))
        .distinct()
    )
    for ct_id, t_id, map_id in rows:
        for team_id in (ct_id, t_id):
            if team_id:
                counts.setdefault(team_id, set()).add(map_id)
    return {k: len(v) for k, v in counts.items()}


def _tool_list_teams(query: str = "") -> dict:
    stmt = select(Team).order_by(Team.name).limit(300)
    if query:
        stmt = stmt.where(Team.name.ilike(f"%{query}%"))
    parsed = _parsed_map_counts()
    rows = []
    for t in dbctx.db().scalars(stmt):
        maps = parsed.get(t.id, 0)
        if not query and not maps:
            continue
        rows.append({"id": t.id, "name": t.name, "parsed_maps": maps})
    rows.sort(key=lambda r: -r["parsed_maps"])
    if not rows:
        return {"teams": [], "note": "No team matched that name."}
    return {"teams": rows[:30]}


def _tool_team_overview(team_id: int) -> dict:
    team = _team(team_id)
    session = dbctx.db()
    matches = session.scalars(
        select(Match).where(or_(Match.team1_id == team.id, Match.team2_id == team.id))
    ).all()
    record = {"won": 0, "lost": 0, "drawn": 0}
    for m in matches:
        if m.team1_id == team.id:
            ours, theirs = m.team1_score, m.team2_score
        else:
            ours, theirs = m.team2_score, m.team1_score
        if ours is None or theirs is None:
            continue
        if ours > theirs:
            record["won"] += 1
        elif ours < theirs:
            record["lost"] += 1
        else:
            record["drawn"] += 1

    n_maps = func.count(func.distinct(MapRoster.match_map_id))
    roster = session.execute(
        select(Player.name, n_maps)
        .join(Player, Player.id == MapRoster.player_id)
        .where(MapRoster.team_id == team.id)
        .group_by(Player.id, Player.name)
        .order_by(n_maps.desc())
        .limit(10)
    )
    return {
        "id": team.id,
        "name": team.name,
        "matches_recorded": len(matches),
        "record": record,
        "map_profiles": mapstrategy.map_profiles(team),
        "roster": [{"name": name, "maps": maps} for name, maps in roster],
    }


def _tool_map_strategy(team_id: int, opponent_id: int | None = None) -> dict:
    team = _team(team_id)
    if opponent_id:
        opponent = _team(opponent_id)
        if opponent.id == team.id:
            return {"error": "team_id and opponent_id must be different teams"}
        return mapstrategy.build_map_report(team, opponent)
    return mapstrategy.map_pool(team)


def _trim_role_player(p: dict) -> dict:
    sides = {}
    for side, verdict in p["roles"].items():
        fit = (p.get("fit") or {}).get(side) or {}
        sides[side] = {
            "role": verdict["label"],
            "confidence": verdict["confidence"],
            "fit_score": fit.get("score"),
            "fit_verdict": fit.get("verdict"),
        }
    return {
        "name": p["name"],
        "rating": p["rating"],
        "adr": p["overall"]["adr"],
        "kd_ratio": p["overall"]["kd_ratio"],
        "in_current_lineup": p.get("in_current_lineup", True),
        "sides": sides,
    }


def _slim_role_section(section: dict | None) -> dict | None:
    if not section or not section.get("available"):
        return section
    return {
        "team": section["team"],
        "maps": section["maps"],
        "best": section["best"],
        "worst": section["worst"],
        "changes": section.get("changes"),
    }


def _tool_role_report(team_id: int, opponent_id: int | None = None) -> dict:
    team = _team(team_id)
    if opponent_id:
        opponent = _team(opponent_id)
        if opponent.id == team.id:
            return {"error": "team_id and opponent_id must be different teams"}
        report = roles.build_role_report(
            team, opponent, mapstrategy.maps_in_window(team), mapstrategy.maps_in_window(opponent)
        )
        return {
            "pool_maps": report.get("pool_maps"),
            "mine": _slim_role_section(report.get("my_team")),
            "opponent": _slim_role_section(report.get("opponent")),
        }

    pool = list(
        dbctx.db()
        .scalars(
            select(MatchMap)
            .where(MatchMap.parsed_at.is_not(None))
            .options(joinedload(MatchMap.match), joinedload(MatchMap.game_map))
        )
        .unique()
    )
    if not pool:
        return {"available": False, "note": "No parsed maps, so no roles could be read."}
    baseline = roles.league_baseline(pool)
    cohorts = roles.role_cohorts(pool, baseline)
    maps = mapstrategy.maps_in_window(team)
    if not maps:
        return {"available": False, "note": f"No parsed maps for {team.name}."}
    picture = roles.rate_team(team, maps, baseline=baseline, cohorts=cohorts)
    return {
        "team": team.name,
        "available": True,
        "players": [_trim_role_player(p) for p in picture["players"]],
        "best": [p["name"] for p in picture["best"]],
        "worst": [p["name"] for p in picture["worst"]],
    }


def _tool_scouting_report(team_id: int, opponent_id: int) -> dict:
    team, opponent = _team(team_id), _team(opponent_id)
    if opponent.id == team.id:
        return {"error": "team_id and opponent_id must be different teams"}

    my_maps = scouting.maps_for_team(team)
    opp_maps = scouting.maps_for_team(opponent)
    h2h_maps = scouting.head_to_head_maps(team, opponent)
    my_profiles = scouting.player_profiles(team, my_maps)
    opp_profiles = scouting.player_profiles(opponent, opp_maps)
    my_shape = scouting.team_shape(team, my_maps)
    opp_shape = scouting.team_shape(opponent, opp_maps)

    matchups = scouting.matchup_report(team, opponent, h2h_maps)
    return {
        "team": team.name,
        "opponent": opponent.name,
        "head_to_head": scouting.head_to_head_report(team, opponent, h2h_maps),
        "underperformers": scouting.find_underperformers(my_profiles, my_shape),
        "threats": scouting.find_threats(opp_profiles),
        "vulnerabilities": scouting.find_vulnerabilities(
            opp_profiles, opp_shape, opponent, opp_maps
        ),
        "duels_by_our_player": [
            {"player": p["player"], "net": p["net"], "advice": p["advice"]}
            for p in matchups.get("by_my_player", [])
        ],
    }


GAMEPLAN_SECTIONS = {
    "verdict", "board", "map_plans", "roles", "players", "duels", "linchpins",
    "man_advantage", "continuity", "my_delta", "opponent_delta", "sample", "lede",
    "levers", "decision", "playbook",
}  # fmt: skip


# Lines per column: all of one Map's would be the whole page; across Maps, the top.
LEVERS_PER_COLUMN = {True: 6, False: 3}


def _levers(my_team, opponent, map_name: str, *, one: bool = True) -> dict:
    """One Map's Levers and Cautions as the Playbook words them, compacted."""
    worded = playbook_view.advice(my_team, opponent, map_name)

    def compact(entries):
        return [
            {"title": e["title"], "facts": e["facts"], "counter": e["counter"],
             "evidence_strength": e["strength"], "worth": e["weight_label"]}
            for e in entries[: LEVERS_PER_COLUMN[one]]
        ]  # fmt: skip

    return {
        "map": map_name,
        "limits": worded["limits"],
        "sides": [
            {
                "my_side": col["label"],
                "levers": compact(col["levers"]),
                "cautions": compact(col["cautions"]),
            }
            for col in worded["sides"]
        ],  # fmt: skip
    }


def _tool_gameplan_section(mine_id: int, theirs_id: int, section: str, map: str = "") -> dict:
    if section not in GAMEPLAN_SECTIONS:
        return {
            "error": f"unknown section {section!r}. Choose one of: "
            + ", ".join(sorted(GAMEPLAN_SECTIONS))
        }
    my_team, opponent = _team(mine_id), _team(theirs_id)
    if my_team.id == opponent.id:
        return {"error": "mine_id and theirs_id must be different teams"}

    report = gameplan_service.build(my_team, opponent)
    if section == "decision":
        built = decision.build(report, my_team, opponent)
        return {k: built[k] for k in ("label", "lead", "forecast", "cards", "moves", "confidence")}
    if section == "playbook":
        if not map:
            # Which Maps have one, in veto order: ask again with one of them.
            return {"maps": playbook_view.maps(report), "note": "give 'map' for its Playbook"}
        if not re.fullmatch(r"de_[a-z0-9_]{2,30}", map):
            return {"error": f"unknown map {map!r}; maps look like 'de_inferno'"}
        panel = playbook_view.panel(my_team, opponent, map)
        return {
            k: panel.get(k) for k in ("label", "plan", "advice", "sections", "pistols", "players")
        }
    if section == "levers":
        if map:
            if not re.fullmatch(r"de_[a-z0-9_]{2,30}", map):
                return {"error": f"unknown map {map!r}; maps look like 'de_inferno'"}
            return _levers(my_team, opponent, map)
        # Across Maps: the ones the veto makes likely to be played.
        likely = [m for m in playbook_view.maps(report) if m["call"] in ("pick", "contest")]
        return {"maps": [_levers(my_team, opponent, m["map"], one=False) for m in likely]}
    if section == "verdict":
        return gameplan_service.verdict(report, my_team, opponent)
    if section == "duels":
        d = report["duels"]
        # With no head-to-head maps the matrix carries only its note.
        return {"totals": d.get("totals", []), "note": d["note"], "dropped": d.get("dropped", {})}
    if section == "roles":
        return {"comparison": report["roles"]["comparison"]}
    if section == "players":
        return {
            key: [
                {
                    "name": p["name"],
                    "rating": p.get("rating"),
                    "in_lineup": p.get("in_lineup"),
                    "instructions": p.get("instructions"),
                }
                for p in report["players"][key]
            ]
            for key in ("mine", "opponent")
        }
    return report[section]


REVIEW_FINDINGS_LIMIT = 40


def _summary_lines(items: list[dict], limit: int = 5) -> list[str]:
    return [i["text"] for i in items[:limit]]


def _compact_summary(summary: dict, team_name: str) -> dict:
    """A Team's Summary as the model reads it: sentences, not ids."""
    return {
        "team": team_name,
        "rounds_won": f"{summary['won']} of {summary['rounds']}",
        "numbers": {
            n["label"]: n["value"] + (f" ({n['tone']})" if n["tone"] else "")
            for n in summary.get("numbers", [])
        },
        "went_well": _summary_lines(summary["strengths"]),
        "went_wrong": _summary_lines(summary["problems"]),
        "focus_points": [
            {"what": f["text"], "work_on": f["advice"], "cost_rounds": f["weight"]}
            for f in summary["focus"]
        ],
    }


def _tool_match_summary(match_id: int) -> dict:
    session = dbctx.db()
    match = session.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(
            joinedload(Match.team1),
            joinedload(Match.team2),
            selectinload(Match.map_results).joinedload(MatchMap.game_map),
        )
    )
    if match is None:
        return {"error": f"no match with id {match_id}"}
    panel = review_view.match_panel(session, match)
    names = {t["id"]: t["name"] for t in panel["teams"]}
    if not any(m["reviewed"] for m in panel["maps"]):
        return {"error": "none of this match's maps has tick data to review",
                "maps": [f"{m['label']} {m['scoreline']}" for m in panel["maps"]]}  # fmt: skip
    return {
        "maps": [
            {
                "map_number": m["map_number"],
                "map": m["label"],
                "score": m["scoreline"],
                "winner": names.get(m["winner_team_id"], ""),
                "reviewed": m["reviewed"],
                "teams": {
                    names.get(t["team_id"], "?"): {
                        "main_strength": t["strength"]["text"] if t["strength"] else "",
                        "main_problem": t["problem"]["text"] if t["problem"] else "",
                    }
                    for t in m["teams"]
                },
            }
            for m in panel["maps"]
        ],
        "teams": [
            {
                "team": names.get(s["team_id"], "?"),
                "rounds_won": f"{s['won']} of {s['rounds']} over {s['maps_played']} maps",
                "repeated_strengths": _summary_lines(s["strengths"]),
                "repeated_problems": _summary_lines(s["problems"]),
                "focus_points": [
                    {
                        "what": f["label"],
                        "maps": f["maps"],
                        "work_on": f["advice"],
                        "cost_rounds": f["weight"],
                    }
                    for f in s["focus"]
                ],  # fmt: skip
                "players": [
                    {
                        "name": p["name"],
                        "swing": p["swing"],
                        "swing_per_round": p["swing_per_round"],
                    }
                    for p in s["players"]
                ],
            }
            for s in panel["summaries"]
        ],
        "weight_unit": "rounds: what a line won or cost its team",
    }


def _tool_match_review(
    match_id: int,
    map_number: int | None = None,
    round: int | None = None,  # noqa: A002 - the tool's own parameter name
    player: str = "",
    kind: str = "",
) -> dict:
    session = dbctx.db()
    maps = list(
        session.scalars(
            select(MatchMap)
            .where(MatchMap.match_id == match_id, MatchMap.parsed_at.is_not(None))
            .order_by(MatchMap.map_number)
        )
    )
    if not maps:
        return {"error": "this match has no parsed map"}
    match_map = (
        next((m for m in maps if m.map_number == map_number), None) if map_number else maps[0]
    )
    if match_map is None:
        return {"error": f"map {map_number} of this match is not parsed",
                "parsed_maps": [m.map_number for m in maps]}  # fmt: skip
    panel = review_view.panel(session, match_map)
    if panel is None:
        return {"error": "this map has no tick data to review"}
    sid = None
    if player:
        wanted = player.strip().lower()
        sid = next(
            (p["sid"] for p in panel["players"] if p["name"].lower() == wanted), None
        ) or next((p["sid"] for p in panel["players"] if wanted in p["name"].lower()), None)
        if sid is None:
            return {"error": f"no player named {player!r} on this map",
                    "players": [p["name"] for p in panel["players"]]}  # fmt: skip
    findings = [
        f for f in panel["findings"]
        if (round is None or f["round"] == round)
        and (sid is None or f["sids"][:1] == [sid])
        and (not kind or f["kind"] == kind)
    ]  # fmt: skip
    total = len(findings)
    if total > REVIEW_FINDINGS_LIMIT:
        findings = sorted(findings, key=lambda f: -abs(f["swing"]))[:REVIEW_FINDINGS_LIMIT]
        findings.sort(key=lambda f: (f["round"] or 0, f["t"] or 0))
    return {
        "map": mn.game_map(match_map.game_map.name if match_map.game_map else ""),
        "match_id": match_id,
        "map_number": match_map.map_number,
        "parsed_maps": [m.map_number for m in maps],
        "note": panel["missing"],
        "swing_unit": "share of one round; +0.25 = raised the team's round win chance by 25 points",
        "summary": [
            _compact_summary(
                t, next((x["name"] for x in panel["teams"] if x["id"] == t["team_id"]), "?")
            )
            for t in panel["summary"]["all"]
        ],
        "players": [
            {
                "name": p["name"],
                "team": p["team"],
                "swing": p["swing"],
                "swing_per_round": p["swing_per_round"],
                "best_round": p["best_round"],
                "worst_round": p["worst_round"],
                "findings": p["counts"],
            }
            for p in panel["players"]
        ],  # fmt: skip
        "rounds": [
            {"round": r["n"], "summary": r["summary"]}
            for r in panel["rounds"]
            if round is None or r["n"] == round
        ],
        "findings": [
            {
                "round": f["round"],
                "time": f["t"],
                "kind": f["kind_label"],
                "what": f["code_label"],
                "title": f["title"],
                "text": f["text"],
                "swing": f["swing"],
            }
            for f in findings
        ],  # fmt: skip
        "findings_total": total,
        "findings_shown": len(findings),
    }


TEAM_MATCHES_LIMIT = 20


def _tool_team_matches(team_id: int, limit: int = 10) -> dict:
    team = _team(team_id)
    session = dbctx.db()
    rows = session.scalars(
        select(Match)
        .where((Match.team1_id == team.id) | (Match.team2_id == team.id))
        .options(selectinload(Match.map_results).joinedload(MatchMap.game_map))
        .order_by(Match.played_at.desc())
        .limit(max(1, min(int(limit or 10), TEAM_MATCHES_LIMIT)))
    ).all()
    out = []
    for m in rows:
        other_id = m.team2_id if m.team1_id == team.id else m.team1_id
        other = session.get(Team, other_id) if other_id else None
        out.append(
            {
                "match_id": m.id,
                "date": m.played_at.date().isoformat() if m.played_at else None,
                "opponent": other.name if other else m.opponent_label,
                "score": m.score,
                "parsed_maps": [
                    {"map_number": mm.map_number, "map": mn.game_map(mm.game_map.name)}
                    for mm in sorted(m.map_results, key=lambda x: x.map_number)
                    if mm.is_parsed and mm.game_map
                ],
            }
        )
    return {"team": team.name, "matches": out}


def _tool_player_form(steamid: str = "", name: str = "") -> dict:
    session = dbctx.db()
    if not steamid and name:
        found = session.scalar(
            select(Player.steamid).where(func.lower(Player.name) == name.strip().lower())
        )
        steamid = str(found) if found else ""
    if not steamid.isdigit():
        return {"error": "give the player's Steam id, or his exact name"}
    built = player_page.build(int(steamid))
    if built is None:
        return {"error": f"no player with Steam id {steamid}"}
    return {
        "player": built["player"],
        "teams": [{"name": t["name"], "maps": t["maps"]} for t in built["teams"]],
        "totals": built["totals"],
        "by_map_side": built["maps"],
        "findings": built["findings"][:10],
        "latest_maps": built["form"][-8:],
    }


def _tool_forecast(mine_id: int, theirs_id: int) -> dict:
    my_team, opponent = _team(mine_id), _team(theirs_id)
    if my_team.id == opponent.id:
        return {"error": "mine_id and theirs_id must be different teams"}
    built = forecast.build(
        my_team,
        opponent,
        my_lineup=[p.name for p in lineup.chosen(my_team) or []] or None,
        their_lineup=[p.name for p in lineup.chosen(opponent) or []] or None,
    )
    return decision._forecast(built, my_team, opponent)


def _tool_rating(team_id: int) -> dict:
    team = _team(team_id)
    found = forecast.standing(team)
    if found is None:
        return {"team": team.name, "rating": None, "note": "no series of this team in the results"}
    return {"team": team.name, **forecast._standing_json(found)}


# AS-3: the user's Workspace, bound around each tool call, for the tools that
# read its private data (the Stratbook, Scrims).
_WORKSPACE: ContextVar[int | None] = ContextVar("assistant_workspace", default=None)
FIND_ROUNDS_LIMIT = 15


def _tool_find_rounds(
    map_name: str, side: str, conditions: list | None = None, team_id: int | None = None,
    buy: str | None = None, score: str | None = None,
) -> dict:  # fmt: skip
    if not re.fullmatch(r"de_[a-z0-9_]{2,30}", map_name or ""):
        return {"error": "map_name like de_mirage"}
    if side not in ("t", "ct"):
        return {"error": "side is t or ct"}
    places = round_search.places(map_name)
    if not conditions:
        return {"map": map_name, "places": places}
    cleaned = []
    for c in conditions[:6]:
        place = str(c.get("place") or "")
        if place not in places:
            return {"error": f"no Callout {place!r} on this map", "places": places}
        cleaned.append({
            "place": place, "min": int(c.get("min", 1)),
            "max": None if c.get("max") is None else int(c["max"]),
            "start": int(c.get("start", 0)), "end": int(c.get("end", 180)),
        })  # fmt: skip
    if team_id is not None:
        _team(team_id)
    found = round_search.search(map_name, side, cleaned, team_id, buy, score=score)
    return {**found, "rounds": found["rounds"][:FIND_ROUNDS_LIMIT]}


def _tool_after_contact(team_id: int, map_name: str) -> dict:
    team = _team(team_id)
    after = after_contact.team(team.id, map_name)
    return {"team": team.name, **after}


def _tool_stratbook(team_id: int | None = None, map_name: str | None = None) -> dict:
    from app.models import Strat

    workspace = _WORKSPACE.get()
    if workspace is None:
        return {"error": "the user has no Workspace"}
    session = dbctx.db()
    query = select(Strat).where(Strat.workspace_id == workspace)
    if team_id:
        query = query.where(Strat.team_id == team_id)
    if map_name:
        query = query.where(Strat.map_name == map_name)
    out = []
    for strat in session.scalars(query.order_by(Strat.map_name, Strat.side, Strat.name)):
        report = strat_match.report(strat)
        out.append({
            "name": strat.name, "map": strat.map_name, "side": strat.side, "kind": strat.kind,
            "status": strat.status, "played": report.get("played"), "won": report.get("won"),
            "won_range": [report.get("low"), report.get("high")],
        })  # fmt: skip
    return {"strats": out} if out else {"strats": [], "note": "no strat written yet"}


def _tool_scrims(team_id: int | None = None, limit: int = 5) -> dict:
    from app.models import WorkspaceTeam

    workspace = _WORKSPACE.get()
    if workspace is None:
        return {"error": "the user has no Workspace"}
    session = dbctx.db()
    mine = list(
        session.scalars(
            select(WorkspaceTeam.team_id).where(WorkspaceTeam.workspace_id == workspace)
        )
    )
    if not mine:
        return {"error": "the user's Workspace names no team of its own"}
    team_id = team_id or mine[0]
    if team_id not in mine:
        return {"error": "scrims are only kept for the user's own teams"}
    rows = scrim_log.log(session, workspace, team_id, max(1, min(int(limit or 5), 10)))
    return {"team": _team(team_id).name, "scrims": rows}


# -- AS-8: what a Player login may ask -------------------------------------------------
_PLAYER: ContextVar[Player | None] = ContextVar("assistant_player", default=None)
MY_MATCHES_LIMIT = 10


def _tool_my_matches(limit: int = MY_MATCHES_LIMIT) -> dict:
    player = _PLAYER.get()
    session = dbctx.db()
    rows = session.execute(
        select(MatchMap.match_id, MatchMap.map_number, GameMap.name, Match.played_at,
               MapRoster.team_id)
        .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
        .join(Match, Match.id == MatchMap.match_id)
        .outerjoin(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(MapRoster.player_id == player.id, MatchMap.parsed_at.is_not(None))
        .order_by(Match.played_at.desc())
        .limit(max(1, min(int(limit or MY_MATCHES_LIMIT), 20)))
    ).all()  # fmt: skip
    return {"player": player.name, "maps": [
        {"match_id": m, "map_number": n, "map": mn.game_map(name or ""),
         "date": played.date().isoformat() if played else None}
        for m, n, name, played, _team in rows
    ]}  # fmt: skip


def _tool_my_goals() -> dict:
    from app.models import DevelopmentGoal, GoalStatus
    from app.services import development

    player = _PLAYER.get()
    session = dbctx.db()
    goals = session.scalars(
        select(DevelopmentGoal).where(
            DevelopmentGoal.player_id == player.id,
            DevelopmentGoal.workspace_id == _WORKSPACE.get(),
            DevelopmentGoal.status == GoalStatus.ACTIVE,
        )
    ).all()
    specs = development.kpis()
    out = []
    for g in goals:
        progress = development.progress(g, player)
        out.append({
            "kpi": (specs.get(g.kpi) or {}).get("label", g.kpi), "baseline": g.baseline,
            "target": g.target, "due": g.due_on.isoformat(), "now": progress["value"],
            "verdict": progress["verdict"], "notes": g.notes,
        })  # fmt: skip
    return {"player": player.name, "goals": out}


def _tool_my_briefings(briefing_id: str = "") -> dict:
    from app.models import Briefing
    from app.services import briefings

    session = dbctx.db()
    shared = select(Briefing).where(
        Briefing.workspace_id == _WORKSPACE.get(), Briefing.shared_at.is_not(None)
    )
    if not briefing_id:
        rows = session.scalars(shared.order_by(Briefing.shared_at.desc()).limit(10)).all()
        return {"briefings": [{"id": str(b.public_id), "title": b.title} for b in rows]}
    try:
        wanted = uuid.UUID(briefing_id)
    except ValueError:
        return {"error": "give a briefing id from the list"}
    b = session.scalar(shared.where(Briefing.public_id == wanted))
    if b is None:
        return {"error": "no shared briefing with that id"}
    content = briefings.unpack(b.payload)
    return {"title": b.title, "note": content.get("note", ""), "maps": [
        {"map": m.get("label"), "note": m.get("note", ""),
         "lines": [i.get("title") for i in m.get("items", [])]}
        for m in content.get("maps", [])
    ]}  # fmt: skip


def _for_a_player(name: str, tool_input: dict):
    """A Player login's call, held to their own play; None when it may not be made."""
    player = _PLAYER.get()
    if name == "player_form":
        return _tool_player_form(steamid=str(player.steamid))
    if name == "match_review":
        match_id = tool_input.get("match_id")
        played = dbctx.db().scalar(
            select(MapRoster.id)
            .join(MatchMap, MatchMap.id == MapRoster.match_map_id)
            .where(MatchMap.match_id == match_id, MapRoster.player_id == player.id)
            .limit(1)
        )
        if played is None:
            return {"error": "you did not play in that match"}
        out = _tool_match_review(**{**tool_input, "player": player.name})
        if isinstance(out, dict) and "players" in out:
            out["players"] = [p for p in out["players"] if p.get("name") == player.name]
        return out
    if name in PLAYER_DISPATCH:
        return PLAYER_DISPATCH[name](**tool_input)
    return None


PLAYER_DISPATCH = {
    "my_matches": _tool_my_matches,
    "my_goals": _tool_my_goals,
    "my_briefings": _tool_my_briefings,
}


DISPATCH = {
    "list_teams": _tool_list_teams,
    "team_overview": _tool_team_overview,
    "map_strategy": _tool_map_strategy,
    "role_report": _tool_role_report,
    "scouting_report": _tool_scouting_report,
    "gameplan_section": _tool_gameplan_section,
    "match_summary": _tool_match_summary,
    "match_review": _tool_match_review,
    "team_matches": _tool_team_matches,
    "player_form": _tool_player_form,
    "forecast": _tool_forecast,
    "rating": _tool_rating,
    "find_rounds": _tool_find_rounds,
    "after_contact": _tool_after_contact,
    "stratbook": _tool_stratbook,
    "scrims": _tool_scrims,
}


# --------------------------------------------------------------- context -----
@dataclass
class Context:
    """What page the Assistant was opened from, checked against real rows.

    ``fixture`` is ``(mine, theirs)`` on a Game Plan; ``lineups`` maps a Fixture
    Team's id to the Steam ids picked for it. ``team`` is a Team page; ``match``
    a Match page, whose two Teams are both named and neither is "mine".
    """

    fixture: tuple[Team, Team] | None = None
    lineups: dict[int, list[int]] = field(default_factory=dict)
    lineup_names: dict[int, list[str]] = field(default_factory=dict)
    team: Team | None = None
    match: Match | None = None
    map_number: int | None = None
    # The Round open on the Replay, on a match page.
    round_number: int | None = None
    # AS-7: a Player page, a Scout's job page, or the Game Plan picker.
    player: Player | None = None
    job: AnalysisJob | None = None
    picker: bool = False
    # The signed-in User's Workspace's my teams (CONTEXT.md): who "we" are.
    my_teams: list[Team] = field(default_factory=list)
    workspace_id: int | None = None
    # AS-8: a Player login asks about their own play only.
    player_login: Player | None = None

    def note(self) -> str:
        """A preface for the system prompt: standing knowledge, not something the user said."""
        if self.player_login is not None:
            p = self.player_login
            return (
                f"\n\nThe user is the player {p.name!r} (Steam id {p.steamid}), not staff. "
                "They may ask only about their own play: their form (player_form), the "
                "Reviews of Matches they played (my_matches, then match_review, which shows "
                "their own Findings), their Development goals (my_goals) and the Briefings "
                "shared with their team (my_briefings). Say plainly that anything else "
                "(other teams' scouting, Forecasts, the Stratbook) is for their staff."
            )
        return self._ours() + self._page()

    def _ours(self) -> str:
        if not self.my_teams:
            return ""
        names = ", ".join(f"{t.name!r} (team_id {t.id})" for t in self.my_teams)
        return f"\n\nThe user works for {names}: when they say we, us or our team, they mean " + (
            "it." if len(self.my_teams) == 1 else "the first of these unless they name another."
        )

    def _page(self) -> str:
        if self.fixture:
            mine, theirs = self.fixture
            text = (
                f"\n\nThe user is currently on the game-plan page for {mine.name!r} "
                f"(team_id {mine.id}) versus {theirs.name!r} (team_id {theirs.id}). "
                "Prefer gameplan_section for questions about this fixture; use those two "
                "ids as mine_id/theirs_id without asking."
            )
            picked = [
                f"{team.name}: {', '.join(self.lineup_names[team.id])}"
                for team in (mine, theirs)
                if self.lineup_names.get(team.id)
            ]
            if picked:
                text += (
                    " The user picked these Lineups on the page, and the tools already rank "
                    "and name players by them: " + "; ".join(picked) + "."
                )
            return text
        if self.team:
            return (
                f"\n\nThe user is currently on the team page for {self.team.name!r} "
                f"(team_id {self.team.id}). Use rating for its Rating and team_matches "
                "for its latest Matches."
            )
        if self.player:
            p = self.player
            return (
                f"\n\nThe user is currently on the player page for {p.name!r} (Steam id "
                f"{p.steamid}). 'This player' means them: use player_form with steamid "
                f"'{p.steamid}'."
            )
        if self.job:
            j = self.job
            text = f"\n\nThe user is currently on the page of a Scout, {j.label!r}: {j.status}"
            if j.status == JobStatus.RUNNING:
                text += f", at {jobs.STAGE_LABELS.get(j.stage, j.stage)} ({j.progress}%)"
            if j.error:
                text += f", with the error {j.error[:200]!r}"
            text += ". A Scout downloads and parses the Teams' Matches; the analysis is on the "
            if j.status == JobStatus.SUCCESS and j.my_team_id and j.opponent_id:
                text += (
                    f"Game Plan page for team_id {j.my_team_id} versus {j.opponent_id}: send "
                    "the user there, and use gameplan_section with those ids for questions."
                )
            else:
                text += "Game Plan page once it succeeds."
            return text
        if self.picker:
            return (
                "\n\nThe user is on the Game Plan picker, choosing two Teams and, for each, "
                "a Lineup of up to five players. For who plays for a Team now use "
                "team_overview, and for one player's form player_form."
            )
        if self.match:
            m = self.match
            sides = " versus ".join(
                f"{t.name!r} (team_id {t.id})" for t in (m.team1, m.team2) if t is not None
            )
            mine = {t.id for t in self.my_teams}
            ours = next((t for t in (m.team1, m.team2) if t is not None and t.id in mine), None)
            return (
                f"\n\nThe user is currently on the match page for {sides}"
                + (f" at {m.tournament.name!r}" if m.tournament else "")
                + (
                    f". {ours.name!r} is the user's own team in this match. Use "
                    if ours
                    else ". Neither side is the user's own team unless they say so. Use "
                )
                + f"match_summary with match_id {m.id} for the match as a whole, and "
                f"match_review with match_id {m.id}"
                + (
                    f" and map_number {self.map_number} (the map open on the page)"
                    if self.map_number
                    else ""
                )
                + " for how this match was played."
                + (
                    f" The Replay is showing round {self.round_number}: 'this round' means it "
                    "(match_review's round argument)."
                    if self.round_number
                    else ""
                )
            )
        return ""

    def label(self) -> str:
        if self.fixture:
            return f"{self.fixture[0].name} vs {self.fixture[1].name}"
        if self.team:
            return self.team.name
        if self.match and self.match.team1 and self.match.team2:
            return f"{self.match.team1.name} vs {self.match.team2.name}"
        if self.player:
            return self.player.name
        if self.job:
            return self.job.label
        return ""


def _steamids(raw) -> list[int]:
    if not isinstance(raw, list):
        return []
    out = []
    for s in raw[:5]:
        try:
            out.append(int(s))
        except (TypeError, ValueError):
            continue
    return list(dict.fromkeys(out))


def clean_context(session: Session, raw, user=None) -> Context:
    """See :func:`_page_context`; adds the User's my teams, so "we" resolves."""
    ctx = _page_context(session, raw)
    if user is not None and user.workspace is not None:
        ctx.my_teams = [wt.team for wt in user.workspace.teams]
        ctx.workspace_id = user.workspace_id
    if user is not None and not user.is_staff and user.player_id is not None:
        ctx.player_login = session.get(Player, user.player_id)
    return ctx


def _page_context(session: Session, raw) -> Context:
    """Validate the page hint against real rows, or drop it.

    A team id the client claims but the database does not have is worth ignoring
    rather than trusting -- the Assistant would otherwise quote a team name it
    made up around a real-looking id. A Lineup with an unknown Steam id is dropped
    the same way, and the side falls back to its most recent five.
    """
    if not isinstance(raw, dict):
        return Context()
    try:
        if raw.get("mine") not in (None, "") and raw.get("theirs") not in (None, ""):
            mine = session.get(Team, int(raw["mine"]))
            theirs = session.get(Team, int(raw["theirs"]))
            if mine is None or theirs is None or mine.id == theirs.id:
                return Context()
            ctx = Context(fixture=(mine, theirs))
            with dbctx.using(session):
                for team, key in ((mine, "my_lineup"), (theirs, "their_lineup")):
                    ids = _steamids(raw.get(key))
                    try:
                        players = lineup.resolve(ids) if ids else []
                    except KeyError:
                        players = []
                    if players:
                        ctx.lineups[team.id] = [p.steamid for p in players]
                        ctx.lineup_names[team.id] = [p.name for p in players]
            return ctx
        if raw.get("team") not in (None, ""):
            team = session.get(Team, int(raw["team"]))
            return Context(team=team) if team else Context()
        if raw.get("match") not in (None, ""):
            match = session.get(Match, int(raw["match"]))
            number = int(raw["map"]) if raw.get("map") not in (None, "") else None
            rnd = int(raw["round"]) if raw.get("round") not in (None, "") and number else None
            if match is None:
                return Context()
            return Context(match=match, map_number=number, round_number=rnd)
        if raw.get("player") not in (None, ""):
            player = session.scalar(select(Player).where(Player.steamid == int(raw["player"])))
            return Context(player=player) if player else Context()
        if raw.get("job") not in (None, ""):
            job = session.scalar(
                select(AnalysisJob).where(AnalysisJob.public_id == uuid.UUID(str(raw["job"])))
            )
            return Context(job=job) if job else Context()
        if raw.get("picker"):
            return Context(picker=True)
    except (TypeError, ValueError):
        return Context()
    return Context()


def clean_history(raw, page: str = "") -> list[dict]:
    """The last few turns, trimmed to plain text -- never raw SDK content blocks.

    Bounded on both axes, so a client cannot inflate the bill by replaying an
    ever-growing history. A question asked on another page than ``page`` is
    marked as such: "their AWPer" there meant that page's opponent, not this one's.
    """
    if not isinstance(raw, list):
        return []
    turns = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        role, content = entry.get("role"), entry.get("content")
        if not isinstance(content, str):
            continue
        content = content.strip()
        if role not in ("user", "assistant") or not content:
            continue
        content = content[:MAX_MESSAGE_CHARS]
        asked_on = entry.get("page")
        if role == "user" and isinstance(asked_on, str) and asked_on and asked_on != page:
            content = f"[Asked on another page: {asked_on[:120]}] {content}"
        turns.append({"role": role, "content": content})
    turns = turns[-get_settings().claude_max_history_turns :]
    # The API wants the first turn from the user.
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


def keyterms(session: Session) -> list[str]:
    """The words a spoken question is most likely to name: Maps, Teams, CS2 terms.

    Teams with the most parsed maps first, so the list stays under
    :data:`app.services.voice.MAX_KEYTERMS` with the ones people ask about.
    """
    with dbctx.using(session):
        teams = sorted(_parsed_map_counts().items(), key=lambda kv: -kv[1])[:50]
    names = dict(
        session.execute(select(Team.id, Team.name).where(Team.id.in_([t for t, _ in teams]))).all()
    )
    short_terms = [
        t
        for group in ("roles", "round phases", "match & format", "stats")
        for t in CS2_TERMS[group]
    ]
    return [
        *mn.MAPS.values(),
        "Dust2",
        *(names[t] for t, _ in teams if t in names),
        *short_terms,
    ]


# Mongolian Cyrillic adds two letters Russian doesn't have (Өө, Үү): a cheap,
# unambiguous signal.
_MONGOLIAN_MARKERS = set("өӨүҮ")


def _language_reminder(message: str) -> str:
    """A per-turn nudge beside the user's own text, where recency beats a rule far away.

    Plenty of Mongolian sentences have neither marker ("Энэ тоглолтыг хэн хожих
    вэ?"), and this tool's Users write Mongolian, so other Cyrillic gets the
    Mongolian nudge too, with room left for a genuinely Russian question.
    """
    if any(ch in _MONGOLIAN_MARKERS for ch in message):
        return (
            "\n\n[Reply in Mongolian -- this message is written in "
            "Mongolian. Do not answer in English.]"
        )
    if any("\u0400" <= ch <= "\u04ff" for ch in message):
        return (
            "\n\n[This message is in Cyrillic: reply in Mongolian unless it is "
            "clearly Russian. Do not answer in English.]"
        )
    return "\n\n[Reply in the same language as this message.]"


def _execute_tool(session: Session, ctx: Context, name: str, tool_input: dict) -> str:
    """Always a JSON string -- that is what a ``tool_result`` block's content must be."""
    fn = DISPATCH.get(name) or PLAYER_DISPATCH.get(name)
    if fn is None:
        result = {"error": f"no such tool: {name}"}
    else:
        try:
            token = _WORKSPACE.set(ctx.workspace_id)
            mine = _PLAYER.set(ctx.player_login)
            try:
                with dbctx.using(session):
                    if ctx.player_login is not None:
                        result = _for_a_player(name, dict(tool_input))
                        if result is None:
                            result = {"error": "that is for your staff to look at"}
                    else:
                        picked = {
                            team_id: lineup.resolve(ids) for team_id, ids in ctx.lineups.items()
                        }
                        with lineup.using(picked):
                            result = fn(**tool_input)
            finally:
                _PLAYER.reset(mine)
                _WORKSPACE.reset(token)
        except UnknownTeam:
            result = {"error": "no team with that id"}
        except TypeError as exc:
            result = {"error": f"bad arguments: {exc}"}
        except Exception:
            logger.exception("assistant tool %s(%r) failed", name, tool_input)
            session.rollback()
            result = {"error": "that lookup failed on the server"}
    return fit(result)


def _dump(value) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _lists(value, path=()):
    """Every list inside ``value`` that sits under a dict key, with that dict."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, list):
                yield value, key, item
            yield from _lists(item, (*path, key))
    elif isinstance(value, list):
        for item in value:
            yield from _lists(item, path)


def fit(result, limit: int = TOOL_RESULT_CHAR_LIMIT) -> str:
    """``result`` as JSON within ``limit`` characters, still valid JSON.

    Cutting the text mid-way handed the model broken JSON and no idea what was
    lost. Instead the longest list is halved, again and again, and its dict says
    how many items were left out (``<key>_omitted``), so the answer can say "and
    N more" rather than invent them."""
    payload = _dump(result)
    if len(payload) <= limit:
        return payload
    data = json.loads(payload)  # a copy, with everything already JSON
    if isinstance(data, list):
        data = {"items": data}
    for _ in range(64):
        found = [(holder, key, items) for holder, key, items in _lists(data) if len(items) > 1]
        if not found:
            break
        holder, key, items = max(found, key=lambda f: len(_dump(f[2])))
        keep = len(items) // 2
        holder[key] = items[:keep]
        holder[f"{key}_omitted"] = holder.get(f"{key}_omitted", 0) + len(items) - keep
        payload = _dump(data)
        if len(payload) <= limit:
            return payload
    return _dump({"error": "this lookup returned too much; ask about one map or one player"})


def _tool_status(session: Session, name: str, tool_input: dict) -> str:
    """What a lookup is doing, worded here rather than by the model (no paid filler)."""
    names = []
    for key in ("team_id", "mine_id", "opponent_id", "theirs_id"):
        value = tool_input.get(key)
        if isinstance(value, int):
            team = session.get(Team, value)
            if team is not None:
                names.append(team.name)
    extra = str(tool_input.get("query") or tool_input.get("section") or "")
    return mn.assistant_status(name, names, extra)


# ------------------------------------------------------------- the chat ------
def is_configured() -> bool:
    return bool(get_settings().claude_api_key.get_secret_value())


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=get_settings().claude_api_key.get_secret_value())


# AS-5: a Round token in a reply, [R14], [R14 1:23], [R14 1:23 @<steamid>] or
# [4021.2:R14]; the page links it, and the voice reads only the round.
ROUND_TOKEN = re.compile(r"\[(?:\d+\.\d+:)?R(\d{1,2})(?: \d{1,2}:\d{2})?(?: @\d{5,20})?\]")
# The Mongolian ordinal suffix follows the vowel of the number's last word:
# нэг, дөрөв, ес and дөч take дүгээр, the rest дугаар.
_FRONT_ONES = {1, 4, 9}


def _ordinal_mn(n: int) -> str:
    front = n % 10 in _FRONT_ONES if n % 10 else n // 10 % 10 == 4
    return f"{n} {'дүгээр' if front else 'дугаар'}"


def spoken(text: str) -> str:
    """A paragraph as the voice should read it: each Round token as its round
    ("14 дүгээр Round" in Mongolian, "round 14" otherwise)."""
    mongolian = re.search("[а-яөүё]", text, re.IGNORECASE) is not None

    def say(m: re.Match) -> str:
        n = int(m.group(1))
        return f"{_ordinal_mn(n)} Round" if mongolian else f"round {n}"

    return ROUND_TOKEN.sub(say, text)


class _Voices:
    """Paragraph audio made in the background and handed out in paragraph order.

    Synthesizing takes seconds a paragraph; done inline it would hold back the
    next paragraph's text as well. So the text goes out the moment it is
    written, and each paragraph's audio follows as its own event when it is ready.
    """

    WORKERS = 2

    def __init__(self, on: bool):
        self.pool = ThreadPoolExecutor(self.WORKERS) if on and voice.is_configured() else None
        self.pending: list[tuple[int, Future]] = []
        self.chars = 0  # spoken, which ElevenLabs bills by

    def submit(self, n: int, text: str) -> None:
        if self.pool is not None:
            text = spoken(text)
            self.chars += len(text)
            self.pending.append((n, self.pool.submit(voice.synthesize, text)))

    def ready(self, wait: bool = False) -> Iterator[dict]:
        while self.pending and (wait or self.pending[0][1].done()):
            n, future = self.pending.pop(0)
            audio = future.result()
            if audio is not None:
                yield {"type": "audio", "id": n, "audio": base64.b64encode(audio).decode("ascii")}

    def close(self) -> None:
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)


def chat_events(
    session: Session,
    history: Iterable[dict],
    message: str,
    *,
    context: Context | None = None,
    voice_on: bool = True,
    usage: Usage | None = None,
    user_ref: str = "",
) -> Iterator[dict]:
    """The event sequence the chat endpoint streams, one piece at a time as it is ready.

    - ``{"type": "status", "text": ...}`` -- a tool is running, right now.
    - ``{"type": "paragraph", "id": n, "text": ...}`` -- one finished paragraph of
      the answer, the moment a blank line closes it.
    - ``{"type": "audio", "id": n, "audio": <base64 MP3>}`` -- paragraph ``n``
      spoken, in paragraph order, when voiced and the voice could be made.
    - ``{"type": "check", "id": n, "numbers": [...]}`` -- numbers in paragraph ``n``
      that no tool returned (AS-4), for the page to mark.
    - ``{"type": "done"}`` -- the turn is over.
    """
    if not is_configured():
        yield {"type": "paragraph", "id": 0, "text": mn.ASSISTANT_NOT_CONFIGURED}
        yield {"type": "done"}
        return

    voices = _Voices(voice_on)
    spent = usage if usage is not None else Usage()
    try:
        yield from _turn(
            session, list(history), message, context or Context(), voices, spent, user_ref
        )
        yield from voices.ready(wait=True)
        yield {"type": "done"}
    finally:
        spent.tts_chars = voices.chars
        voices.close()


def _turn(
    session: Session,
    history: list,
    message: str,
    ctx: Context,
    voices: _Voices,
    usage: Usage,
    user_ref: str,
) -> Iterator[dict]:
    settings = get_settings()
    client = _client()
    usage.model = settings.claude_model
    # Anthropic's abuse detection sees an opaque id per User, never a name.
    extra = {"metadata": {"user_id": user_ref}} if user_ref else {}
    note = ctx.note()
    system = [
        {"type": "text", "text": SYSTEM_PROMPT},
        *([{"type": "text", "text": note}] if note else []),
    ]
    messages: list = [
        *history,
        {"role": "user", "content": message + _language_reminder(message)},
    ]
    count = 0
    # AS-4: what the turn's numbers may come from: the question, the page, the tools.
    sources = grounding.source_numbers(message + note)

    def speak(text: str) -> Iterator[dict]:
        nonlocal count
        voices.submit(count, text)
        count += 1
        yield {"type": "paragraph", "id": count - 1, "text": text}
        loose = grounding.ungrounded(text, sources)
        if loose:
            usage.unchecked += loose
            yield {"type": "check", "id": count - 1, "numbers": loose}

    for _ in range(MAX_TOOL_ROUNDS):
        buf = ""
        with client.beta.messages.stream(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=system,
            tools=PLAYER_TOOLS if ctx.player_login is not None else TOOLS,
            messages=messages,
            output_config={"effort": settings.claude_effort},
            cache_control={"type": "ephemeral"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
            **extra,
        ) as stream:
            for delta in stream.text_stream:
                buf += delta
                while "\n\n" in buf:
                    para, buf = buf.split("\n\n", 1)
                    if para.strip():
                        yield from speak(para.strip())
                yield from voices.ready()
            final = stream.get_final_message()
        usage.add(getattr(final, "usage", None))
        if buf.strip():
            yield from speak(buf.strip())

        if final.stop_reason == "refusal":
            yield from speak(mn.ASSISTANT_REFUSED)
            return
        messages.append({"role": "assistant", "content": final.content})
        if final.stop_reason != "tool_use":
            break
        usage.tool_rounds += 1
        results = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            yield {"type": "status", "text": _tool_status(session, block.name, block.input)}
            usage.tools.append(block.name)
            content = _execute_tool(session, ctx, block.name, dict(block.input))
            sources |= grounding.source_numbers(content)
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
            yield from voices.ready()
        messages.append({"role": "user", "content": results})
    else:
        yield from speak(mn.ASSISTANT_TOO_MANY_LOOKUPS)
        return

    if not count:
        yield from speak(mn.ASSISTANT_NOTHING)
