"""Scene spec for v2 reels/carousels: one persistent animated diagram that changes state per beat.

Gemini writes a `SceneSpec` (diagram + 5-7 voiced beats + cheat sheet); a second pass reviews it
for technical accuracy and the draft is rewritten once with the issues. The same spec renders
the reel (src.reel_v2.render) and the carousel (cover, one slide per carousel beat, cheat sheet).

Usage:
    python -m src.reel_v2.spec "Blue-Green Deployment" --category SystemDesign --out spec.json
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.config import load_brand
from src.llm import generate_json
from src.logger import get_logger

log = get_logger("reel_v2.spec")

Tone = Literal["blue", "green", "cyan", "amber", "red", "purple", "gray", "white"]
Icon = Literal["users", "client", "phone", "server", "router", "balancer", "service", "database",
               "cache", "queue", "storage", "cloud", "lock", "key", "brain", "doc", "gear", "globe",
               "cpu", "memory", "code", "container", "shield", "clock"]
NodeState = Literal["idle", "live", "ok", "busy", "boot", "error", "testing", "empty", "off"]
# live = actively serving traffic (glows), busy = overloaded (amber), ok = healthy but not serving,
# idle = standby, boot = starting, testing = being checked, error = failing, empty = not deployed, off = stopped

MAX_WORDS = 75          # ~30s with the brand voices at +6% (95 words came out at ~35s)
MAX_WORDS_HI = 60       # Hinglish: the Hindi voices speak ~2.3 words/s vs ~2.8 (docs/specs/hinglish-narration-plan.md §7)
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
TRIGGER_STRIP = ".,?!'\"।"   # Hindi sentences end in । (danda)


def max_words(language: str = "en") -> int:
    return MAX_WORDS_HI if language == "hi" else MAX_WORDS
MAX_ROW_NODES = 6


class TitlePart(BaseModel):
    text: str
    tone: Tone = "white"


class Group(BaseModel):
    id: str = Field(description="Short id, e.g. 'blue'")
    label: str = Field(description="Group title shown on its box, max 12 chars, e.g. 'BLUE'")
    sub: str = Field(default="", description="Tiny version/detail after the label, max 8 chars, e.g. 'v1.0'")
    tone: Tone


class Node(BaseModel):
    id: str = Field(description="Short unique id, e.g. 'lb', 'db1'")
    label: str = Field(description="Label under/inside the node, max 12 chars, e.g. 'USERS', 'srv-1', 'Redis'")
    icon: Icon
    row: int = Field(description="0 = top. Rows 0-3. Traffic normally flows top to bottom")
    group: str = Field(default="", description="Group id if the node sits inside a group box, else empty")


class Edge(BaseModel):
    src: str = Field(description="Node id")
    dst: str = Field(description="Node id")


class Flow(BaseModel):
    src: str = Field(description="Node id the dots start at (must be an edge, either direction)")
    dst: str = Field(description="Node id the dots travel to")
    tone: Tone = Field(description="Dot color: usually the color of the system that is serving")
    bad: bool = Field(default=False, description="True if these requests fail (dots turn red at the end)")


class StateChange(BaseModel):
    node: str = Field(description="Node id")
    state: NodeState = Field(description="live=serving traffic now (glows), busy=overloaded, ok=healthy not serving, idle=standby, boot, testing, error, empty=not deployed, off")
    note: str = Field(default="", description="Tiny status under the node, max 9 chars, e.g. 'HTTP 500', '✓ 200', 'idle', '62%'")


class Counter(BaseModel):
    label: str = Field(description="Max 10 chars, uppercase, e.g. 'LIVE', 'DOWNTIME', 'HIT RATE'")
    value: str = Field(description="Max 9 chars, e.g. 'BLUE v1', '0.0s', '48,200', '99%'")
    tone: Tone


class Beat(BaseModel):
    narration: str = Field(description="Spoken text for this beat, 1-2 short sentences, max 16 words")
    trigger: str = Field(description="ONE word from the narration; the diagram changes exactly when it is spoken")
    heading: str = Field(description="On-screen beat heading, UPPERCASE, max 20 chars, e.g. 'FLIP THE SWITCH'")
    tone: Tone = Field(description="Heading color: amber=in progress, green=success, red=problem, blue/cyan=info")
    caption: str = Field(description="One-line on-screen caption, max 40 chars. Wrap 1-3 key words in *asterisks*")
    term: str = Field(default="", description="Optional terminal command typed on screen, max 32 chars, no leading $")
    flows: list[Flow] = Field(description="Edges carrying traffic AFTER the trigger (full list, not a diff)")
    states: list[StateChange] = Field(default_factory=list, description="Only nodes whose state changes at the trigger")
    counters: list[Counter] = Field(description="Exactly 3 counters, same labels in every beat, values after the trigger")
    on_carousel: bool = Field(description="True if this moment gets its own carousel slide (4-5 beats)")
    slide_title: str = Field(default="", description="Carousel slide title if on_carousel, max 34 chars, *emphasis* allowed")
    slide_text: str = Field(default="", description="Carousel slide paragraph if on_carousel, max 26 words, *emphasis* allowed")


class Compare(BaseModel):
    headers: list[str] = Field(description="Exactly 4 short column headers, first is the option name, e.g. STRATEGY, DOWNTIME, ROLLBACK, COST")
    rows: list[list[str]] = Field(description="3-4 rows of 4 cells (max 13 chars each, full words). The topic itself is the LAST row")


class Cheat(BaseModel):
    use_when: list[str] = Field(description="Exactly 3 bullets, max 6 words each")
    tradeoffs: list[str] = Field(description="Exactly 3 bullets, max 6 words each")
    code_title: str = Field(description="UPPERCASE, max 30 chars, e.g. 'THE SWITCH IN KUBERNETES'")
    code: str = Field(description="Real, correct snippet (or, for non-code topics, a short template), 1-4 lines, max 46 chars per line")
    compare: Compare


class SceneSpec(BaseModel):
    topic: str
    title: list[TitlePart] = Field(description="Reel/cover title split into colored parts, max 22 chars total, e.g. [Blue/blue, -/white, Green/green]")
    subtitle: str = Field(description="Second title line, max 18 chars, e.g. 'Deployment'")
    cover_lead: str = Field(description="Carousel cover line, max 18 words, *emphasis* allowed")
    groups: list[Group] = Field(default_factory=list)
    nodes: list[Node] = Field(description="4-12 nodes")
    edges: list[Edge]
    initial: list[StateChange] = Field(description="State of EVERY node at the start")
    beats: list[Beat] = Field(description="5-8 beats: hook, the story (one change per beat), last beat = payoff + follow CTA")
    payoff: list[TitlePart] = Field(description="Exactly 2 short payoff lines (max 16 chars each), e.g. 'Zero downtime.'/green, 'Instant rollback.'/blue")
    payoff_sub: str = Field(description="Mono summary under the payoff, max 40 chars, e.g. '1 switch · 0s down · rollback in 1s'")
    cheat: Cheat
    caption: str = Field(description="Instagram caption without hashtags, 60-150 words, ends with a question")
    hashtags: list[str] = Field(description="10-15 hashtags, each starting with #")


class Review(BaseModel):
    ok: bool = Field(description="True only if there are no factual/technical errors")
    issues: list[str] = Field(description="Each concrete error or misleading claim, with the fix")


SYSTEM = """You design short animated explainer videos for a tech education Instagram account.
Everything happens on ONE diagram that stays on screen; the story is told by changing which
connections carry traffic, node states (live/boot/error...), and 3 live counters. Text on screen
is minimal: a beat heading, one caption line, optionally a terminal command. You are technically
precise, never invent statistics or benchmarks, and keep it beginner-friendly."""


# How the one-diagram format maps onto categories that aren't about live systems.
CATEGORY_GUIDE = {
    "DSA": """CATEGORY NOTES (DSA)
- The diagram is the data structure or the algorithm's state: array cells, pointers, hash buckets,
  stack/queue slots, tree or graph nodes (icons: memory, cpu, code, database, gear, clock).
  Rows hold levels (tree depth, input -> work -> output).
- Flows are data moving or a pointer/visit step (e.g. left -> mid, node -> child). States show the
  algorithm: testing = being compared, live = current element, ok = done/found, off = discarded.
- Counters track the algorithm, e.g. STEPS, COMPARES, TIME (Big-O), SPACE. Use a real worked example
  with small concrete inputs; counts must be exactly what that example produces.
- `term` lines are real code or a trace (e.g. 'mid = (lo + hi) // 2'). The cheat snippet is real
  working code; the comparison table compares alternative approaches by time/space complexity.""",
    "Interview": """CATEGORY NOTES (Interview)
- The diagram is a process, not a server stack: e.g. candidate -> recruiter -> rounds -> offer, or the
  structure of a good answer (question -> clarify -> approach -> trade-offs -> result)
  (icons: users, client, doc, brain, clock, key, shield, gear).
- Flows are the candidate or the answer moving through the stages. States: live = current stage,
  ok = passed, error = a common mistake, testing = being evaluated.
- Counters are qualitative or count stages, e.g. STAGE, SIGNAL, TIME LEFT. Never invent pass
  rates, salaries or hiring statistics.
- Leave `term` empty: it renders as a shell prompt, and these beats have no commands.
- The cheat snippet is a reusable template (an answer outline or a short script to say), labelled as
  such; the comparison table compares approaches (e.g. answer styles or prep strategies).""",
}


HINGLISH = """NARRATION LANGUAGE: HINGLISH
- Only `narration` is Hinglish: conversational Hindi the way Indian tech creators talk, with English tech terms.
  Write Hindi words in Devanagari and keep tech terms, product names, commands and numbers in Latin script,
  e.g. "सोचो, हर request सीधा database पे जाए तो क्या होगा? यहीं cache काम आता है।"
  Never write Hindi in Latin letters ("socho, har request..."): the Hindi voice mispronounces it.
- EVERYTHING ELSE STAYS ENGLISH, with no Devanagari: title, subtitle, cover_lead, headings, captions, terms,
  slide titles and text, node and group labels, counters, notes, payoff, cheat sheet, Instagram caption, hashtags.
- `trigger` is one word copied exactly from the narration; prefer the English tech word ("cache", "crash").
- Short sentences ending in । or ?. Say symbols in words ("O of log n").
- Last beat ends with the follow CTA in Hinglish, e.g. 'ऐसे और explainers के लिए follow करो {handle}।'.
"""


def _prompt(topic: str, category: str, angle: str, brand: dict, feedback: str = "", language: str = "en") -> str:
    extra = f"\n\nFix these problems from the previous draft:\n{feedback}" if feedback else ""
    guide = f"\n\n{CATEGORY_GUIDE[category]}" if category in CATEGORY_GUIDE else ""
    if language == "hi":
        guide += "\n\n" + HINGLISH.format(handle=brand["handle"])
    return f"""Design one reel + carousel for {brand['handle']}.

Topic: {topic}
Category: {category}
Angle: {angle or 'explain how it works and why it matters'}

DIAGRAM
- 6-10 nodes is ideal, in rows 0-3 (row 0 at the top, traffic flows down). Max {MAX_ROW_NODES} per row.
  A busy diagram looks real: use groups of 2-3 identical nodes (srv-1..3, worker-1..3, replicas)
  instead of one box, and give traffic several parallel paths.
- Use groups for environments/clusters/regions that matter to the story (e.g. BLUE and GREEN boxes,
  each with 2-3 server nodes). Nodes of one group must share a row.
- Edges are the wires that exist. Flows are the wires carrying traffic right now.
- Show the problem AND the fix on the same diagram (e.g. a node goes error, then traffic is
  rerouted, a cache starts answering, a queue absorbs a spike...).

BEATS (5-8) — total narration MAX {max_words(language)} words, the reel must be at most 30 seconds
- Beat 1 is the hook: a curiosity question + the topic name. It must already have flows (motion
  from the first frame).
- Middle beats: ONE change each (short beats are fine), the trigger word is the verb that causes
  it (flip, crash, cache...). Two changes in a row = two beats (e.g. 'Found a bug?' then 'Flip back.').
- Last beat: payoff + "Follow {brand['handle']} for more ..." (it shows the payoff card).
- Counters: exactly 3, identical labels in every beat, values reflect the moment (e.g. LIVE,
  REQUESTS, DOWNTIME / HIT RATE, LATENCY, DB LOAD). A counter changes only in the beat whose
  action causes it (latency drops when hits START, not while the cache is being filled).
  Values are illustrative but must be plausible and consistent with each other.
- Give most beats a `term`: a real command or log line for that moment (e.g. 'redis-cli GET user:42',
  'kubectl get pods'). It types itself on screen and adds motion.
- Payoff lines and payoff_sub state the mechanism or benefit, never precise invented numbers
  (good: 'Fewer DB reads.', '1 switch · 0 downtime'; bad: 'Sub-ms reads', '99% faster').
  No absolutes that aren't literally true ('infinite', 'zero errors', 'never fails', 'instant').
- Spell out symbols in narration only ("O of n"); on-screen text uses normal notation.
- Mark 4-5 beats on_carousel (not the hook or the payoff) with a slide_title and slide_text.
  The first carousel beat should show the problem / the naive way.

CHEAT SHEET: when to use, trade-offs, one real snippet (CLI/config/code), and a comparison with
2-3 alternatives (topic itself last). Table cells are plain words, no abbreviations like 'Wr-Thru'.

CAPTION: 60-150 words, hook first line, value in the middle, question at the end. No hashtags.
HASHTAGS: 10-15; include a few of: {' '.join(brand['hashtags'])}.{guide}{extra}"""


def on_screen_text(s: SceneSpec) -> list[str]:
    """Every string the reel/carousel shows or publishes (narration and ids excluded)."""
    c = s.cheat
    out = [p.text for p in s.title + s.payoff] + [s.subtitle, s.cover_lead, s.payoff_sub, s.caption, *s.hashtags]
    out += [x for g in s.groups for x in (g.label, g.sub)] + [n.label for n in s.nodes]
    out += [st.note for st in s.initial]
    for b in s.beats:
        out += [b.heading, b.caption, b.term, b.slide_title, b.slide_text]
        out += [x for k in b.counters for x in (k.label, k.value)] + [st.note for st in b.states]
    out += [*c.use_when, *c.tradeoffs, c.code_title, c.code, *c.compare.headers, *(x for r in c.compare.rows for x in r)]
    return out


def validate(s: SceneSpec, language: str = "en") -> list[str]:
    """Structural checks the renderer relies on (accuracy is the reviewer's job)."""
    p: list[str] = []
    ids = {n.id for n in s.nodes}
    groups = {g.id for g in s.groups}
    if len(ids) != len(s.nodes):
        p.append("node ids must be unique")
    if not 4 <= len(s.nodes) <= 12:
        p.append(f"need 4-12 nodes, got {len(s.nodes)}")
    rows: dict[int, int] = {}
    for n in s.nodes:
        if not 0 <= n.row <= 3:
            p.append(f"node {n.id}: row must be 0-3")
        rows[n.row] = rows.get(n.row, 0) + 1
        if n.group and n.group not in groups:
            p.append(f"node {n.id}: unknown group {n.group}")
        if len(n.label) > 14:
            p.append(f"node {n.id}: label too long (max 12)")
    p += [f"row {r} has {c} nodes (max {MAX_ROW_NODES})" for r, c in rows.items() if c > MAX_ROW_NODES]
    for g in s.groups:
        grows = {n.row for n in s.nodes if n.group == g.id}
        if len(grows) > 1:
            p.append(f"group {g.id}: its nodes must share one row")
        if not grows:
            p.append(f"group {g.id} has no nodes")
    pairs = set()
    for e in s.edges:
        if e.src not in ids or e.dst not in ids:
            p.append(f"edge {e.src}->{e.dst}: unknown node")
        pairs.add((e.src, e.dst))
    if not 5 <= len(s.beats) <= 8:
        p.append(f"need 5-8 beats, got {len(s.beats)}")
    words = sum(len(b.narration.split()) for b in s.beats)
    if words > (cap := max_words(language)):
        p.append(f"narration is {words} words; max {cap} so the reel stays under 30 seconds")
    labels = None
    for i, b in enumerate(s.beats, 1):
        if b.trigger.lower().strip(TRIGGER_STRIP) not in [w.lower().strip(TRIGGER_STRIP) for w in b.narration.split()]:
            p.append(f"beat {i}: trigger {b.trigger!r} is not a word of its narration")
        for f in b.flows:
            if (f.src, f.dst) not in pairs and (f.dst, f.src) not in pairs:
                p.append(f"beat {i}: flow {f.src}->{f.dst} is not an edge")
        p += [f"beat {i}: state for unknown node {c.node}" for c in b.states if c.node not in ids]
        if len(b.counters) != 3:
            p.append(f"beat {i}: needs exactly 3 counters")
        ls = [c.label for c in b.counters]
        labels = labels or ls
        if ls != labels:
            p.append(f"beat {i}: counter labels must match beat 1 {labels}")
        if len(b.heading) > 22 or len(b.caption.replace('*', '')) > 44 or len(b.term) > 34:
            p.append(f"beat {i}: heading/caption/term too long")
        if b.on_carousel and not (b.slide_title and b.slide_text):
            p.append(f"beat {i}: carousel beats need slide_title and slide_text")
    if s.beats and not s.beats[0].flows:
        p.append("beat 1 must have flows (motion from the first frame)")
    nc = sum(b.on_carousel for b in s.beats)
    if not 3 <= nc <= 5:
        p.append(f"mark 4-5 beats on_carousel, got {nc}")
    if len(s.payoff) != 2:
        p.append("payoff needs exactly 2 lines")
    c = s.cheat
    if len(c.compare.headers) != 4 or any(len(r) != 4 for r in c.compare.rows):
        p.append("cheat.compare needs 4 headers and 4 cells per row")
    if any(len(l) > 52 for l in c.code.splitlines()) or len(c.code.splitlines()) > 5:
        p.append("cheat.code: max 4 lines of 46 chars")
    if language == "hi":
        p += [f"beat {i}: narration must be Hinglish in Devanagari (with English tech terms), not Latin script"
              for i, b in enumerate(s.beats, 1) if not DEVANAGARI.search(b.narration)]
        if hindi := [t for t in on_screen_text(s) if DEVANAGARI.search(t)]:
            p.append(f"only the narration is Hinglish; keep on-screen text and the caption English: {hindi[:3]}")
    return p


def _review_prompt(s: SceneSpec, language: str = "en") -> str:
    hinglish = ("\nThe narration is Hinglish (Hindi in Devanagari with English tech terms); the rest is English. "
                "Check that each beat's narration says the same thing as its on-screen text and is technically "
                "correct.\n") if language == "hi" else ""
    return f"""You are a strict senior engineer reviewing an animated explainer for technical accuracy.
Check every claim in narration, captions, terminal commands, the cheat sheet snippet and the
comparison table. Does the diagram story (which node fails, where traffic goes) match how the
real system behaves? Flag exaggerated or absolute claims (infinite, zero, never, instant) that are
not literally true, especially in the payoff. Ignore style. Flag only real errors or misleading
statements.{hinglish}

{s.model_dump_json(indent=2)}"""


def generate(topic: str, category: str = "", angle: str = "", feedback: str = "", language: str = "en") -> SceneSpec:
    brand = load_brand()
    spec = generate_json(_prompt(topic, category, angle, brand, feedback, language), SceneSpec, system=SYSTEM)
    problems = validate(spec, language)
    review = generate_json(_review_prompt(spec, language), Review, temperature=0.2)
    issues = problems + ([] if review.ok else review.issues)
    if issues:
        log.info("rewriting draft: %s", "; ".join(issues))
        fix = "\n".join(f"- {i}" for i in issues)
        spec = generate_json(_prompt(topic, category, angle, brand, (feedback + "\n" + fix).strip(), language),
                             SceneSpec, system=SYSTEM)
        left = validate(spec, language)
        if left:
            raise ValueError("scene spec still invalid: " + "; ".join(left))
    return spec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate a v2 scene spec with Gemini")
    ap.add_argument("topic")
    ap.add_argument("--category", default="")
    ap.add_argument("--angle", default="")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    spec = generate(args.topic, args.category, args.angle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(spec.model_dump_json(indent=1), encoding="utf-8")
    log.info("spec → %s (%d beats, %d words)", args.out, len(spec.beats),
             sum(len(b.narration.split()) for b in spec.beats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
