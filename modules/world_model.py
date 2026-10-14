"""
Temporal knowledge graph: the core of the TESS Enterprise World Model.

A structured representation of an organisation (people, projects, tasks,
documents, meetings) where every relationship has a validity interval
[valid_from, valid_to) and every attribute keeps its history.

  * ingest()       turns text events (slack, calendar, notes) into graph updates
  * owner(), open_work(), path(), impact(), diff()   answer questions "as of" a date
  * llm_context()  serialises a sub-graph so an LLM can reason over it

Run a small console demo with:   python -m modules.world_model
"""
import json
import re
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

# Relations where an entity can have only ONE active target at a time.
# Adding a new one automatically closes the old one (e.g. reassignment).
EXCLUSIVE_RELS = {"assigned_to"}


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class Entity:
    id: str
    type: str                      # person | project | task | document | meeting
    name: str
    aliases: list = field(default_factory=list)
    # attribute -> list of (value, valid_from)  (append-only history)
    attrs: dict = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    rel: str
    dst: str
    valid_from: str
    valid_to: Optional[str] = None
    source: str = ""               # where we learned this (slack, calendar...)

    def active(self, date: str) -> bool:
        return self.valid_from <= date and (self.valid_to is None or date < self.valid_to)


# --------------------------------------------------------------------------
# World model
# --------------------------------------------------------------------------
class WorldModel:
    def __init__(self):
        self.entities: dict[str, Entity] = {}
        self.edges: list[Edge] = []
        self.log: list[dict] = []  # raw ingested events (provenance)

    # ---- building ---------------------------------------------------------
    def add_entity(self, id, type, name, aliases=None):
        self.entities[id] = Entity(id, type, name, aliases or [])
        return self.entities[id]

    def find(self, text: str) -> Optional[Entity]:
        """Resolve a name/alias/id to an entity (case-insensitive)."""
        t = text.strip().lower()
        for e in self.entities.values():
            if t == e.id.lower() or t == e.name.lower() or t in (a.lower() for a in e.aliases):
                return e
        return None

    def find_in_text(self, text: str):
        """Return [(start, end, entity)] for every known entity mentioned, longest first."""
        hits = []
        for e in self.entities.values():
            for label in [e.name] + e.aliases:
                for m in re.finditer(r"\b" + re.escape(label) + r"\b", text, re.I):
                    hits.append((m.start(), m.end(), e))
        hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
        out, last_end = [], -1
        for s, e_, ent in hits:                    # drop overlaps
            if s >= last_end:
                out.append((s, e_, ent)); last_end = e_
        return out

    def add_edge(self, src, rel, dst, date, source=""):
        # skip if the identical edge is already active
        for e in self.edges:
            if (e.src, e.rel, e.dst) == (src, rel, dst) and e.active(date):
                return None
        if rel in EXCLUSIVE_RELS:                  # close previous owner
            for e in self.edges:
                if e.src == src and e.rel == rel and e.active(date):
                    e.valid_to = date
        edge = Edge(src, rel, dst, date, None, source)
        self.edges.append(edge)
        return edge

    def set_attr(self, id, key, value, date):
        hist = self.entities[id].attrs.setdefault(key, [])
        if not hist or hist[-1][0] != value:
            hist.append((value, date))

    def attr_at(self, id, key, date):
        val = None
        for v, d in self.entities[id].attrs.get(key, []):
            if d <= date:
                val = v
        return val

    # ---- queries (all "as of" a date) ------------------------------------
    def out_edges(self, id, date, rel=None):
        return [e for e in self.edges if e.src == id and e.active(date) and (rel is None or e.rel == rel)]

    def in_edges(self, id, date, rel=None):
        return [e for e in self.edges if e.dst == id and e.active(date) and (rel is None or e.rel == rel)]

    def owner(self, task_id, date):
        """Who owns this task on `date`? -> list of person ids."""
        return [e.dst for e in self.out_edges(task_id, date, "assigned_to")]

    def open_work(self, person_id, date):
        """Tasks assigned to a person on `date` that are not done."""
        tasks = [e.src for e in self.in_edges(person_id, date, "assigned_to")]
        return [t for t in tasks if self.attr_at(t, "status", date) != "done"]

    def path(self, a_id, b_id, date):
        """Shortest relationship path (edges treated as undirected). Returns list of hop strings."""
        if a_id not in self.entities or b_id not in self.entities:
            return None
        prev = {a_id: None}
        q = deque([a_id])
        while q:
            cur = q.popleft()
            if cur == b_id:
                break
            for e in self.edges:
                if not e.active(date):
                    continue
                if e.src == cur:   nxt, arrow = e.dst, f"{self._n(e.src)} --{e.rel}--> {self._n(e.dst)}"
                elif e.dst == cur: nxt, arrow = e.src, f"{self._n(e.src)} --{e.rel}--> {self._n(e.dst)}"
                else: continue
                if nxt not in prev:
                    prev[nxt] = (cur, arrow)
                    q.append(nxt)
        if b_id not in prev:
            return None
        hops, node = [], b_id
        while prev[node] is not None:
            parent, arrow = prev[node]
            hops.append(arrow)
            node = parent
        return hops[::-1]

    def impact(self, task_id, date):
        """Everything downstream that depends (transitively) on this task."""
        seen, q = set(), deque([task_id])
        while q:
            cur = q.popleft()
            for e in self.in_edges(cur, date, "depends_on"):
                if e.src not in seen:
                    seen.add(e.src); q.append(e.src)
        return sorted(seen)

    def snapshot(self, date):
        edges = {(e.src, e.rel, e.dst) for e in self.edges if e.active(date)}
        attrs = {(i, k, self.attr_at(i, k, date))
                 for i, ent in self.entities.items() for k in ent.attrs}
        return edges, attrs

    def diff(self, d1, d2):
        """What changed between two dates? Returns list of change tuples."""
        e1, a1 = self.snapshot(d1)
        e2, a2 = self.snapshot(d2)
        changes = []
        for s, r, d in sorted(e2 - e1): changes.append(("+", s, r, d))
        for s, r, d in sorted(e1 - e2): changes.append(("-", s, r, d))
        old = {(i, k): v for i, k, v in a1}
        for i, k, v in sorted(a2, key=str):
            if old.get((i, k)) != v:
                changes.append(("~", i, k, old.get((i, k)), v))
        return changes

    # ---- LLM context ------------------------------------------------------
    def llm_context(self, id, date, hops=2):
        """Serialise the neighbourhood of an entity as compact text for an LLM prompt."""
        seen, frontier, lines = {id}, [id], []
        for _ in range(hops):
            nxt = []
            for cur in frontier:
                ent = self.entities[cur]
                attrs = {k: self.attr_at(cur, k, date) for k in ent.attrs}
                attrs = {k: v for k, v in attrs.items() if v is not None}
                lines.append(f"{ent.type}:{ent.name} {json.dumps(attrs)}")
                for e in self.out_edges(cur, date):
                    lines.append(f"  {self._n(e.src)} --{e.rel}--> {self._n(e.dst)}")
                    if e.dst not in seen: seen.add(e.dst); nxt.append(e.dst)
                for e in self.in_edges(cur, date):
                    if e.src not in seen: seen.add(e.src); nxt.append(e.src)
            frontier = nxt
        for cur in frontier:                      # leaf nodes of the last hop
            ent = self.entities[cur]
            attrs = {k: self.attr_at(cur, k, date) for k in ent.attrs}
            attrs = {k: v for k, v in attrs.items() if v is not None}
            lines.append(f"{ent.type}:{ent.name} {json.dumps(attrs)}")
        return "\n".join(lines)

    # ---- helpers / persistence -------------------------------------------
    def _n(self, id):
        return self.entities[id].name if id in self.entities else id

    def names(self, ids):
        return [self._n(i) for i in ids]

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "entities": [asdict(e) for e in self.entities.values()],
                "edges": [asdict(e) for e in self.edges],
                "log": self.log,
            }, f, indent=2)

    @classmethod
    def load(cls, path):
        wm = cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for e in data["entities"]:
            wm.entities[e["id"]] = Entity(**e)
        wm.edges = [Edge(**e) for e in data["edges"]]
        wm.log = data.get("log", [])
        return wm


# --------------------------------------------------------------------------
# Ingestion: text event -> graph updates
# --------------------------------------------------------------------------
# (regex over the sentence with entity names replaced by placeholders)
# Placeholders: {A} = first entity, {B} = second entity
RULES = [
    (r"\{A\} (?:was |is )?re-?assigned to \{B\}", "assigned_to", "A->B"),
    (r"\{A\} (?:was |is )?assigned to \{B\}",      "assigned_to", "A->B"),
    (r"\{A\} attended \{B\}",                      "attended",    "A->B"),
    (r"\{A\} (?:wrote|authored|created) \{B\}",    "authored",    "A->B"),
    (r"\{A\} depends on \{B\}",                    "depends_on",  "A->B"),
    (r"\{A\} (?:is )?about \{B\}",                 "about",       "A->B"),
    (r"\{A\} (?:is )?part of \{B\}",               "about",       "A->B"),
    (r"\{A\} discussed \{B\}",                     "discussed",   "A->B"),
]
STATUS_RULES = [
    (r"\{A\} (?:is|was) blocked", "blocked"),
    (r"\{A\} (?:is|was) (?:done|completed|finished)", "done"),
    (r"\{A\} (?:is )?(?:in progress|started)", "in_progress"),
]


def ingest(wm: WorldModel, text: str, date: str, source: str = ""):
    """Rule-based extractor. Swap/extend with `llm_extract` for free-form text."""
    wm.log.append({"text": text, "date": date, "source": source})
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        hits = wm.find_in_text(sentence)
        if not hits:
            continue
        # replace entity mentions by placeholders, left to right
        masked, offset, order = sentence, 0, []
        for (s, e, ent), ph in zip(hits, "AB"):
            masked = masked[:s + offset] + "{" + ph + "}" + masked[e + offset:]
            offset += len("{" + ph + "}") - (e - s)
            order.append(ent)
        masked = masked.rstrip(".!? ")
        matched = False
        for pat, rel, _ in RULES:
            if len(order) >= 2 and re.fullmatch(pat, masked, re.I):
                wm.add_edge(order[0].id, rel, order[1].id, date, source)
                matched = True
                break
        if matched:
            continue
        for pat, status in STATUS_RULES:
            if order and re.fullmatch(pat, masked, re.I):
                wm.set_attr(order[0].id, "status", status, date)
                matched = True
                break
        if not matched:
            print(f"  [ingest] could not parse: {sentence!r}")


def llm_extract(text: str):
    """OPTIONAL: use an LLM for free-form text. Should return a list of
    (subject_name, relation, object_name) triples, which you then add with
    wm.add_edge(). Left as a stub so the program runs offline."""
    raise NotImplementedError


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------
def build_org() -> WorldModel:
    wm = WorldModel()
    for id, name in [("p_asha", "Asha"), ("p_ben", "Ben"), ("p_cara", "Cara")]:
        wm.add_entity(id, "person", name)
    wm.add_entity("pr_atlas", "project", "Atlas")
    wm.add_entity("t_api", "task", "API redesign")
    wm.add_entity("t_ui", "task", "UI refresh")
    wm.add_entity("t_launch", "task", "Launch")
    wm.add_entity("d_spec", "document", "Atlas Spec")
    wm.add_entity("m_kick", "meeting", "Kickoff")
    return wm


def demo():
    wm = build_org()

    # structural facts
    ingest(wm, "API redesign is part of Atlas. UI refresh is part of Atlas.", "2026-09-01", "plan")
    ingest(wm, "Launch depends on API redesign. Launch depends on UI refresh.", "2026-09-01", "plan")
    ingest(wm, "Cara authored Atlas Spec. Atlas Spec is about Atlas.", "2026-09-02", "docs")
    ingest(wm, "Kickoff discussed Atlas Spec.", "2026-09-03", "calendar")

    # events over time
    ingest(wm, "API redesign assigned to Ben. UI refresh assigned to Cara", "2026-09-05", "email")
    ingest(wm, "Ben attended Kickoff. Asha attended Kickoff", "2026-09-06", "calendar")
    ingest(wm, "API redesign is blocked", "2026-09-12", "slack")
    ingest(wm, "API redesign reassigned to Asha", "2026-09-15", "meeting notes")

    print("Path Cara -> Atlas Spec (Sep 20):")
    for hop in wm.path("p_cara", "d_spec", "2026-09-20") or []:
        print("  ", hop)

    print("\nWho owns the API task?")
    for d in ("2026-09-10", "2026-09-20"):
        print(f"  {d[5:]}: {wm.names(wm.owner('t_api', d))}")

    print("\nImpact if API redesign slips:", wm.names(wm.impact("t_api", "2026-09-20")))
    print("Asha's open work:", wm.names(wm.open_work("p_asha", "2026-09-20")))

    print("\nWhat changed Sep 10 -> Sep 20:")
    for c in wm.diff("2026-09-10", "2026-09-20"):
        if c[0] == "~":
            print(f"  ~ {wm._n(c[1])}.{c[2]}: {c[3]} -> {c[4]}")
        else:
            print(f"  {c[0]} {wm._n(c[1])} --{c[2]}--> {wm._n(c[3])}")

    print("\nLLM context for 'Launch':")
    print(wm.llm_context("t_launch", "2026-09-20"))

    wm.save("tess_world.json")
    print("\nSaved to tess_world.json")


if __name__ == "__main__":
    demo()
