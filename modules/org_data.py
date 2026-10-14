"""
A synthetic organisation: 8 people, 3 projects, 10 tasks, 4 documents,
4 meetings and about 30 dated events over two months.

Run the 6 demo questions with:   python -m modules.org_data
"""
from .world_model import WorldModel, ingest

# (date, source, text) -- all events in time order
EVENTS = [
    # structure
    ("2026-08-01", "plan", "API redesign is part of Atlas. UI refresh is part of Atlas. Launch is part of Atlas."),
    ("2026-08-01", "plan", "Database migration is part of Beacon. Auth service is part of Beacon. Payment gateway is part of Beacon."),
    ("2026-08-01", "plan", "Mobile app is part of Cedar. Onboarding flow is part of Cedar. Testing is part of Cedar."),
    ("2026-08-02", "plan", "Launch depends on API redesign. Launch depends on UI refresh."),
    ("2026-08-02", "plan", "Payment gateway depends on Auth service. Auth service depends on Database migration."),
    ("2026-08-02", "plan", "Beta release depends on Mobile app. Mobile app depends on Onboarding flow."),
    # documents
    ("2026-08-03", "docs", "Cara authored Atlas Spec. Atlas Spec is about Atlas."),
    ("2026-08-04", "docs", "Dev authored Beacon Plan. Beacon Plan is about Beacon."),
    ("2026-08-05", "docs", "Gita authored Cedar Brief. Cedar Brief is about Cedar."),
    ("2026-08-20", "docs", "Farid authored Security Report. Security Report is about Beacon."),
    # meetings
    ("2026-08-06", "calendar", "Ben attended Kickoff. Asha attended Kickoff. Cara attended Kickoff."),
    ("2026-08-06", "calendar", "Kickoff discussed Atlas Spec."),
    ("2026-08-25", "calendar", "Dev attended Sprint Review. Esha attended Sprint Review. Gita attended Sprint Review."),
    ("2026-09-08", "calendar", "Hari attended Budget Meeting. Asha attended Budget Meeting."),
    ("2026-09-18", "calendar", "Ben attended Retro. Cara attended Retro. Dev attended Retro."),
    # assignments
    ("2026-08-07", "email", "API redesign assigned to Ben. UI refresh assigned to Cara. Launch assigned to Asha."),
    ("2026-08-08", "email", "Database migration assigned to Dev. Auth service assigned to Esha."),
    ("2026-08-09", "email", "Payment gateway assigned to Farid. Mobile app assigned to Gita."),
    ("2026-08-10", "email", "Onboarding flow assigned to Hari. Testing assigned to Gita."),
    # progress / changes
    ("2026-08-15", "slack", "Database migration in progress. API redesign in progress."),
    ("2026-08-28", "slack", "Database migration is done."),
    ("2026-09-02", "slack", "Auth service in progress. UI refresh in progress."),
    ("2026-09-06", "slack", "UI refresh is done."),
    ("2026-09-09", "slack", "Payment gateway is blocked."),
    ("2026-09-12", "slack", "API redesign is blocked."),
    ("2026-09-15", "meeting notes", "API redesign reassigned to Asha."),
    ("2026-09-16", "meeting notes", "Payment gateway reassigned to Dev."),
    ("2026-09-20", "slack", "Auth service is done."),
    ("2026-09-22", "slack", "Payment gateway in progress."),
    ("2026-09-25", "slack", "Onboarding flow is blocked."),
    ("2026-09-28", "meeting notes", "Onboarding flow reassigned to Ben."),
]


def build_big_org() -> WorldModel:
    wm = WorldModel()
    for id, name in [("p_asha", "Asha"), ("p_ben", "Ben"), ("p_cara", "Cara"), ("p_dev", "Dev"),
                     ("p_esha", "Esha"), ("p_farid", "Farid"), ("p_gita", "Gita"), ("p_hari", "Hari")]:
        wm.add_entity(id, "person", name)
    for id, name in [("pr_atlas", "Atlas"), ("pr_beacon", "Beacon"), ("pr_cedar", "Cedar")]:
        wm.add_entity(id, "project", name)
    for id, name in [("t_api", "API redesign"), ("t_ui", "UI refresh"), ("t_launch", "Launch"),
                     ("t_db", "Database migration"), ("t_auth", "Auth service"),
                     ("t_pay", "Payment gateway"), ("t_mobile", "Mobile app"),
                     ("t_onboard", "Onboarding flow"), ("t_test", "Testing"),
                     ("t_beta", "Beta release")]:
        wm.add_entity(id, "task", name)
    for id, name in [("d_spec", "Atlas Spec"), ("d_plan", "Beacon Plan"),
                     ("d_brief", "Cedar Brief"), ("d_sec", "Security Report")]:
        wm.add_entity(id, "document", name)
    for id, name in [("m_kick", "Kickoff"), ("m_sprint", "Sprint Review"),
                     ("m_budget", "Budget Meeting"), ("m_retro", "Retro")]:
        wm.add_entity(id, "meeting", name)

    for date, source, text in EVENTS:
        ingest(wm, text, date, source)
    return wm


def ask_questions(wm: WorldModel):
    print("=" * 55)
    print("Q1. Who owned the Payment gateway on Sep 10, and on Sep 20?")
    for d in ("2026-09-10", "2026-09-20"):
        print(f"    {d}: {wm.names(wm.owner('t_pay', d))}")

    print("\nQ2. If Database migration slips, what is affected?")
    print("   ", wm.names(wm.impact("t_db", "2026-09-20")))

    print("\nQ3. What is Dev working on (not done) on Sep 20?")
    print("   ", wm.names(wm.open_work("p_dev", "2026-09-20")))

    print("\nQ4. How is Hari connected to Atlas Spec?")
    path = wm.path("p_hari", "d_spec", "2026-09-20")
    for hop in path or ["no connection found"]:
        print("    ", hop)

    print("\nQ5. What changed between Sep 10 and Sep 30?")
    for c in wm.diff("2026-09-10", "2026-09-30"):
        if c[0] == "~":
            print(f"     ~ {wm._n(c[1])}.{c[2]}: {c[3]} -> {c[4]}")
        else:
            print(f"     {c[0]} {wm._n(c[1])} --{c[2]}--> {wm._n(c[3])}")

    print("\nQ6. Which tasks are blocked on Sep 30?")
    blocked = [e.name for i, e in wm.entities.items()
               if e.type == "task" and wm.attr_at(i, "status", "2026-09-30") == "blocked"]
    print("   ", blocked)


if __name__ == "__main__":
    wm = build_big_org()
    ask_questions(wm)
    wm.save("tess_world_big.json")
    print("\nSaved to tess_world_big.json")
