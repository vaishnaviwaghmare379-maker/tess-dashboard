"""
The LLM layer.

Two jobs for the LLM:
  1. UNDERSTAND messy human messages -> simple sentences -> graph updates
  2. ANSWER questions                -> from graph context, not raw documents

Two modes:
  * OFFLINE (default): a small rule-based stand-in. No key needed.
  * ONLINE: put ANTHROPIC_API_KEY in a .env file (see .env.example) and
    `pip install anthropic`. The real LLM is then used automatically.

Run the demo with:   python -m modules.llm_layer
"""
import os
import re

from .world_model import WorldModel, ingest
from .org_data import build_big_org

def _load_env():
    """Read KEY=value lines from a .env file in the project root (if present)."""
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
USE_LLM = bool(os.environ.get("ANTHROPIC_API_KEY"))
MODEL = "claude-sonnet-5-5"

FORMS = """Allowed sentence forms (use exact entity names from the list):
  <task> assigned to <person>.
  <task> reassigned to <person>.
  <task> is blocked.  /  <task> is done.  /  <task> in progress.
  <person> attended <meeting>.
  <person> authored <document>.
  <task> depends on <task>."""


# --------------------------------------------------------------------------
# 1. Messy text -> clean sentences
# --------------------------------------------------------------------------
def rewrite_online(wm: WorldModel, text: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    names = ", ".join(e.name for e in wm.entities.values())
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=(f"You convert messy workplace messages into simple sentences.\n{FORMS}\n"
                f"Known entities: {names}\n"
                "Output ONLY the sentences, one per line. If nothing applies, output nothing."),
        messages=[{"role": "user", "content": text}],
    )
    return resp.content[0].text.strip()


def rewrite_offline(wm: WorldModel, text: str) -> str:
    """Tiny stand-in for an LLM: handles a few common messy phrasings."""
    out = []
    for s in re.split(r"(?<=[.!?])\s+", text.strip()):
        low = s.lower()
        hits = [h[2] for h in wm.find_in_text(s)]
        people = [e for e in hits if e.type == "person"]
        tasks = [e for e in hits if e.type == "task"]
        meetings = [e for e in hits if e.type == "meeting"]

        if tasks and people and re.search(r"taking over|took over|picked up|will handle|now owns", low):
            out.append(f"{tasks[0].name} reassigned to {people[0].name}.")
        elif tasks and re.search(r"stuck|blocked|on hold|waiting on", low):
            out.append(f"{tasks[0].name} is blocked.")
        elif tasks and re.search(r"finished|wrapped up|completed|shipped|\bdone\b", low):
            out.append(f"{tasks[0].name} is done.")
        elif tasks and re.search(r"started|began|working on", low):
            out.append(f"{tasks[0].name} in progress.")
        elif meetings and people and re.search(r"joined|was in|came to|showed up|attended", low):
            out += [f"{p.name} attended {meetings[0].name}." for p in people]
        else:
            out.append(s)  # unchanged
    return " ".join(out)


def smart_ingest(wm: WorldModel, text: str, date: str, source: str = ""):
    clean = rewrite_online(wm, text) if USE_LLM else rewrite_offline(wm, text)
    print(f"  [{date}] {text!r}\n        -> {clean!r}")
    ingest(wm, clean.replace("\n", " "), date, source)


# --------------------------------------------------------------------------
# 2. Answer questions from graph context
# --------------------------------------------------------------------------
def answer(wm: WorldModel, question: str, entity_id: str, date: str) -> str:
    context = wm.llm_context(entity_id, date)
    if not USE_LLM:
        return ("(offline mode - no LLM key set. This is the context an LLM would receive:)\n"
                + context)
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=("You are TESS, an enterprise assistant. Answer ONLY from the graph facts given. "
                "Reason about relationships and recent changes. If the facts do not say, say so. Be concise."),
        messages=[{"role": "user", "content": f"Facts as of {date}:\n{context}\n\nQuestion: {question}"}],
    )
    return resp.content[0].text.strip()


# --------------------------------------------------------------------------
# Demo
# --------------------------------------------------------------------------
if __name__ == "__main__":
    print("Mode:", "ONLINE (Claude)" if USE_LLM else "OFFLINE (rule-based stand-in)")
    wm = build_big_org()

    print("\n--- Reading messy messages ---")
    smart_ingest(wm, "Heads up, Gita is taking over Onboarding flow from Ben.", "2026-10-01", "slack")
    smart_ingest(wm, "Payment gateway wrapped up finally!", "2026-10-03", "slack")
    smart_ingest(wm, "Esha and Hari joined the Retro yesterday.", "2026-10-05", "calendar")
    smart_ingest(wm, "Mobile app is stuck, waiting on Onboarding flow.", "2026-10-07", "slack")

    print("\n--- What the graph now says (Oct 10) ---")
    print("Onboarding flow owner:", wm.names(wm.owner("t_onboard", "2026-10-10")))
    print("Payment gateway status:", wm.attr_at("t_pay", "status", "2026-10-10"))
    print("Mobile app status:", wm.attr_at("t_mobile", "status", "2026-10-10"))
    print("Retro attendees:", wm.names([e.src for e in wm.in_edges("m_retro", "2026-10-10", "attended")]))

    print("\n--- Ask TESS ---")
    q = "Why is the Beta release at risk?"
    print("Q:", q)
    print(answer(wm, q, "t_beta", "2026-10-10"))

    wm.save("tess_world_big.json")
