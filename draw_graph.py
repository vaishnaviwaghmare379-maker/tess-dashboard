"""
Optional: draw who-owns-what at two dates, side by side (needs matplotlib).

    pip install matplotlib
    python draw_graph.py
"""
import matplotlib
matplotlib.use("Agg")  # saves to a file; delete this line to get a pop-up window instead
import matplotlib.pyplot as plt
from matplotlib.patches import Patch, FancyBboxPatch

from modules.evaluate import build_world

DATE_A, DATE_B = "2026-09-10", "2026-10-10"
STATUS_COLOR = {"blocked": "#ef6f6c", "in_progress": "#ffd166", "done": "#8fd694", None: "#dddddd"}

PEOPLE = ["p_asha", "p_ben", "p_cara", "p_dev", "p_esha", "p_farid", "p_gita", "p_hari"]
TASKS = ["t_api", "t_ui", "t_launch", "t_db", "t_auth", "t_pay",
         "t_mobile", "t_onboard", "t_test", "t_beta"]


def owners(wm, date):
    return {(e.src, e.dst) for e in wm.edges if e.rel == "assigned_to" and e.active(date)}


def draw_panel(ax, wm, date, other_date):
    here, other = owners(wm, date), owners(wm, other_date)
    ypos_p = {p: len(PEOPLE) - i for i, p in enumerate(PEOPLE)}
    ypos_t = {t: (len(TASKS) - i) * (len(PEOPLE) / len(TASKS)) for i, t in enumerate(TASKS)}

    for task, person in here:                                 # arrows first (behind boxes)
        new = (task, person) not in other
        ax.annotate("", xy=(1.1, ypos_p[person]), xytext=(2.9, ypos_t[task]),
                    arrowprops=dict(arrowstyle="->", color="#d62828" if new else "#7a7a7a",
                                    lw=3 if new else 1.3))
    for p in PEOPLE:
        ax.add_patch(FancyBboxPatch((0.1, ypos_p[p] - 0.28), 1.0, 0.56, boxstyle="round,pad=0.02",
                                    fc="#f4a261", ec="#555", zorder=3))
        ax.text(0.6, ypos_p[p], wm.entities[p].name, ha="center", va="center", fontsize=11, zorder=4)
    for t in TASKS:
        status = wm.attr_at(t, "status", date)
        ax.add_patch(FancyBboxPatch((2.9, ypos_t[t] - 0.25), 1.6, 0.5, boxstyle="round,pad=0.02",
                                    fc=STATUS_COLOR[status], ec="#555", zorder=3))
        ax.text(3.7, ypos_t[t], wm.entities[t].name, ha="center", va="center", fontsize=10, zorder=4)
    ax.set_xlim(0, 4.7)
    ax.set_ylim(0.2, len(PEOPLE) + 0.8)
    ax.set_title(date, fontsize=15, fontweight="bold")
    ax.axis("off")


def main():
    wm = build_world()
    fig, axes = plt.subplots(1, 2, figsize=(15, 7.5))
    draw_panel(axes[0], wm, DATE_A, DATE_B)
    draw_panel(axes[1], wm, DATE_B, DATE_A)
    fig.suptitle("TESS world model: who owns what, and how it changed", fontsize=17)
    fig.legend(handles=[Patch(fc=c, ec="#555", label=l) for l, c in
                        [("blocked", STATUS_COLOR["blocked"]), ("in progress", STATUS_COLOR["in_progress"]),
                         ("done", STATUS_COLOR["done"]), ("no status yet", STATUS_COLOR[None])]],
               loc="lower center", ncol=4, fontsize=11, frameon=False)
    fig.text(0.5, 0.075, "Red arrow = ownership that changed since the other date",
             ha="center", fontsize=11, color="#d62828")
    plt.tight_layout(rect=[0, 0.11, 1, 0.95])
    from pathlib import Path
    out = Path(__file__).resolve().parent / "docs" / "screenshots" / "graph_before_after.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
