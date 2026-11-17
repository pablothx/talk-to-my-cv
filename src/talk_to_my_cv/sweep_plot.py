"""PNG of the threshold sweep: the picture that explains step 5 at a glance."""

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

from talk_to_my_cv.evaluation import SweepRow  # noqa: E402

SURFACE, INK, INK_2, MUTED, GRID, AXIS = (
    "#fcfcfb",
    "#0b0b0b",
    "#52514e",
    "#898781",
    "#e1e0d9",
    "#c3c2b7",
)
REFUSALS, PASSING = "#2a78d6", "#eb6834"  # categorical slots 1 and 2 (validated, CVD-safe)


def plot_sweep(
    rows: Sequence[SweepRow], gate_best: float, configured: float, model: str, out: Path
) -> Path:
    xs = [r.threshold for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    series = [
        ("Unanswerable questions refused", REFUSALS, [r.correct_refusals for r in rows]),
        ("Answerable questions passing", PASSING, [r.answerable_passing for r in rows]),
    ]
    for label, color, ys in series:
        ax.plot(xs, ys, color=color, linewidth=2, label=label, drawstyle="steps-post")
        ax.annotate(
            label,
            (xs[-1], ys[-1]),
            xytext=(6, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK_2,
        )

    # (x, label, line style, label side): labels sit on the free side of their line.
    markers = [
        (gate_best, f"gate-only best {gate_best:.2f}", (0, (4, 3)), "left"),
        (configured, f"configured {configured:.2f}\n(best with the LLM)", "solid", "right"),
    ]
    for x, label, style, side in markers:
        ax.axvline(x, color=INK_2, linewidth=1, linestyle=style)
        ax.annotate(
            label,
            (x, 0.12),
            xytext=(6 if side == "left" else -6, 0),
            textcoords="offset points",
            xycoords=("data", "axes fraction"),
            ha=side,
            fontsize=9,
            color=INK,
        )

    ax.set_xlim(xs[0], xs[-1])
    ax.set_ylim(-0.03, 1.03)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("Relevance threshold (top-1 cosine similarity)", color=INK_2, fontsize=10)
    ax.set_title(
        f"Relevance gate sweep · {model} · traps excluded",
        loc="left",
        color=INK,
        fontsize=12,
        pad=22,
    )
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.0),
        ncol=2,
        frameon=False,
        fontsize=9,
        labelcolor=INK_2,
        borderaxespad=0.2,
        handlelength=1.6,
    )

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    return out
