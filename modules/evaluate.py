"""
Does the graph beat plain search?  10 hand-checked questions, two methods:

  A) GRAPH : the world model (relationships + time)
  B) SEARCH: keyword retrieval over the raw messages (top 3), then name
             extraction. It even gets a free advantage: it only sees messages
             dated on or before the question date. (Online mode: an LLM reads
             the 3 retrieved messages instead.)

Run with:   python -m modules.evaluate        (also writes results/results.csv)
"""
import csv
import re
from pathlib import Path

from .world_model import ingest
from .org_data import build_big_org, EVENTS
from .llm_layer import USE_LLM, MODEL, rewrite_online, rewrite_offline

TODAY = "2026-10-10"

# Messy messages that arrive after the structured events
MESSY = [
    ("2026-10-01", "Heads up, Gita is taking over Onboarding flow from Ben."),
    ("2026-10-03", "Payment gateway wrapped up finally!"),
    ("2026-10-05", "Esha and Hari joined the Retro yesterday."),
    ("2026-10-07", "Mobile app is stuck, waiting on Onboarding flow."),
]


def build_world():
    wm = build_big_org()
    for date, text in MESSY:
        rewrite = rewrite_online if USE_LLM else rewrite_offline
        ingest(wm, rewrite(wm, text), date, "messy")
    return wm


# The raw corpus that plain search sees (original, un-cleaned text)
CORPUS = [(d, t) for d, _, t in EVENTS] + MESSY

STOP = set("""who what which is are was were the a an of on in at to by for and or if it its
that this with from as be been has have do does did how why when where tasks task people
person attended""".split())


def tokens(s):
    return {w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP}


def search_answer(wm, question, subject, expect_type, date):
    """Baseline: top-3 keyword matches (no relationships), then extract names."""
    q = tokens(question)
    docs = [(len(q & tokens(t)), d, t) for d, t in CORPUS if d <= date]
    docs = sorted([x for x in docs if x[0] > 0], reverse=True)[:3]

    if USE_LLM:
        import anthropic
        msgs = "\n".join(f"[{d}] {t}" for _, d, t in docs)
        r = anthropic.Anthropic().messages.create(
            model=MODEL, max_tokens=200,
            system="Answer using ONLY these messages. Output only a comma-separated list of names.",
            messages=[{"role": "user", "content": f"Messages:\n{msgs}\n\nQuestion (as of {date}): {question}"}])
        return {x.strip() for x in r.content[0].text.split(",") if x.strip()}

    found = set()
    for _, d, t in docs:
        for sent in re.split(r"(?<=[.!?])\s+", t):
            if subject.lower() in sent.lower():
                for _, _, ent in wm.find_in_text(sent):
                    if ent.type == expect_type and ent.name.lower() != subject.lower():
                        found.add(ent.name)
    return found


# --------------------------------------------------------------------------
# The 10 questions: (question, date, subject, expected type, graph function, truth)
# --------------------------------------------------------------------------
def build_questions(wm):
    N = wm.names
    blocked = lambda d: [e.name for i, e in wm.entities.items()
                         if e.type == "task" and wm.attr_at(i, "status", d) == "blocked"]
    attendees = lambda m, d: [e.src for e in wm.in_edges(m, d, "attended")]
    return [
        ("Who owned API redesign on Sep 10?", "2026-09-10", "API redesign", "person",
         lambda d: N(wm.owner("t_api", d)), {"Ben"}),
        ("Who owns API redesign on Sep 20?", "2026-09-20", "API redesign", "person",
         lambda d: N(wm.owner("t_api", d)), {"Asha"}),
        ("Who owns Onboarding flow now?", TODAY, "Onboarding flow", "person",
         lambda d: N(wm.owner("t_onboard", d)), {"Gita"}),
        ("Which tasks are blocked now?", TODAY, "blocked", "task",
         lambda d: blocked(d), {"API redesign", "Onboarding flow", "Mobile app"}),
        ("If Database migration slips, which tasks are affected?", TODAY, "Database migration", "task",
         lambda d: N(wm.impact("t_db", d)), {"Auth service", "Payment gateway"}),
        ("Who attended Retro?", TODAY, "Retro", "person",
         lambda d: N(attendees("m_retro", d)), {"Ben", "Cara", "Dev", "Esha", "Hari"}),
        ("Who attended Kickoff?", TODAY, "Kickoff", "person",
         lambda d: N(attendees("m_kick", d)), {"Ben", "Asha", "Cara"}),
        ("Who authored the Security Report?", TODAY, "Security Report", "person",
         lambda d: N([e.src for e in wm.in_edges("d_sec", d, "authored")]), {"Farid"}),
        ("What open work does Dev have on Sep 20?", "2026-09-20", "Dev", "task",
         lambda d: N(wm.open_work("p_dev", d)), {"Payment gateway"}),
        ("Who attended a meeting that discussed Atlas Spec?", TODAY, "Atlas Spec", "person",
         lambda d: N([a for m in [e.src for e in wm.in_edges("d_spec", d, "discussed")]
                      for a in attendees(m, d)]), {"Ben", "Asha", "Cara"}),
    ]


def main():
    wm = build_world()
    print("Mode:", "ONLINE (Claude reads retrieved messages)" if USE_LLM
          else "OFFLINE (keyword search + name extraction)")
    rows, g_score, s_score = [], 0, 0

    for i, (q, date, subj, etype, graph_fn, truth) in enumerate(build_questions(wm), 1):
        g = set(graph_fn(date))
        s = search_answer(wm, q, subj, etype, date)
        g_ok, s_ok = g == truth, s == truth
        g_score += g_ok
        s_score += s_ok
        rows.append([i, q, sorted(truth), sorted(g), g_ok, sorted(s), s_ok])
        print(f"\nQ{i}. {q}")
        print(f"   truth : {sorted(truth)}")
        print(f"   GRAPH : {sorted(g)}  {'OK' if g_ok else 'WRONG'}")
        print(f"   SEARCH: {sorted(s)}  {'OK' if s_ok else 'WRONG'}")

    n = len(rows)
    print("\n" + "=" * 45)
    print(f"GRAPH  correct: {g_score}/{n}")
    print(f"SEARCH correct: {s_score}/{n}")

    out = Path(__file__).resolve().parent.parent / "results" / "results.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "question", "truth", "graph", "graph_correct", "search", "search_correct"])
        w.writerows(rows)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
