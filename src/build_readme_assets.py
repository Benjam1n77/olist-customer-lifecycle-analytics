"""生成 GitHub README 使用的真实项目视觉素材。

流程图来自项目实际建模步骤；用户分层图来自已验证的 Tableau 导出数据。
本模块不会生成或模拟 Tableau Dashboard 截图。
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from src.config import PROJECT_ROOT


OUTPUT_DIR = PROJECT_ROOT / "docs" / "images"
SEGMENT_SOURCE = PROJECT_ROOT / "outputs" / "tableau" / "customer_segment_dashboard.csv"

COLORS = {
    "navy": "#17324D",
    "blue": "#2F6B9A",
    "teal": "#2A9D8F",
    "gold": "#E9C46A",
    "orange": "#F4A261",
    "red": "#E76F51",
    "ink": "#263238",
    "muted": "#607D8B",
    "line": "#B0BEC5",
    "surface": "#F7FAFC",
    "white": "#FFFFFF",
}


def _add_box(
    axis,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    body: str,
    color: str,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        linewidth=1.6,
        edgecolor=color,
        facecolor=COLORS["white"],
    )
    axis.add_patch(patch)
    axis.text(
        x + width / 2,
        y + height * 0.69,
        title,
        ha="center",
        va="center",
        fontsize=15,
        fontweight="bold",
        color=color,
    )
    axis.text(
        x + width / 2,
        y + height * 0.36,
        body,
        ha="center",
        va="center",
        fontsize=10.5,
        color=COLORS["muted"],
        linespacing=1.35,
    )


def _add_arrow(axis, start: tuple[float, float], end: tuple[float, float]) -> None:
    axis.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=18,
            linewidth=1.8,
            color=COLORS["line"],
            shrinkA=4,
            shrinkB=4,
        )
    )


def build_project_architecture() -> Path:
    """生成项目分层架构图。"""
    fig, axis = plt.subplots(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(COLORS["surface"])
    axis.set_facecolor(COLORS["surface"])
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    axis.text(
        0.5,
        0.91,
        "Olist Customer Lifecycle Analytics — Project Architecture",
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color=COLORS["navy"],
    )
    axis.text(
        0.5,
        0.86,
        "Traceable data layers from public transactions to operational decision outputs",
        ha="center",
        va="center",
        fontsize=12,
        color=COLORS["muted"],
    )

    boxes = [
        (0.04, "Data Sources", "9 Olist CSV tables\ncustomers · orders · items\npayments · reviews · products", COLORS["blue"]),
        (0.28, "SQL Modeling", "Order-level aggregation\nmart_order_summary\nmart_customer_features", COLORS["teal"]),
        (0.52, "Python Analysis", "Quality validation\nCohort · delivery analysis\nvisualization · export", COLORS["orange"]),
        (0.76, "Decision Outputs", "Customer segments\ncampaign targets\nTableau-ready datasets", COLORS["red"]),
    ]
    for x, title, body, color in boxes:
        _add_box(axis, x, 0.38, 0.2, 0.34, title, body, color)
    for x in (0.24, 0.48, 0.72):
        _add_arrow(axis, (x, 0.55), (x + 0.04, 0.55))

    axis.text(
        0.5,
        0.23,
        "Key control: aggregate one-to-many tables to order_id before JOIN",
        ha="center",
        va="center",
        fontsize=14,
        color=COLORS["ink"],
        bbox={
            "boxstyle": "round,pad=0.55",
            "facecolor": COLORS["white"],
            "edgecolor": COLORS["line"],
        },
    )
    axis.text(
        0.5,
        0.12,
        "SQL modeling  →  Python validation  →  Tableau and operational delivery",
        ha="center",
        va="center",
        fontsize=12,
        color=COLORS["muted"],
    )

    output_path = OUTPUT_DIR / "project_architecture.png"
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def build_pipeline_preview() -> Path:
    """生成与 README Mermaid 一致的数据处理流程图。"""
    fig, axis = plt.subplots(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(COLORS["surface"])
    axis.set_facecolor(COLORS["surface"])
    axis.set_xlim(0, 1)
    axis.set_ylim(0, 1)
    axis.axis("off")

    axis.text(
        0.5,
        0.91,
        "End-to-End Data Pipeline",
        ha="center",
        va="center",
        fontsize=26,
        fontweight="bold",
        color=COLORS["navy"],
    )
    axis.text(
        0.5,
        0.86,
        "From raw business tables to audience activation and Tableau",
        ha="center",
        va="center",
        fontsize=12,
        color=COLORS["muted"],
    )

    steps = [
        (0.05, 0.58, "01", "Raw business\ntables", COLORS["blue"]),
        (0.29, 0.58, "02", "Data quality\nchecks", COLORS["blue"]),
        (0.53, 0.58, "03", "Order-level\nmart", COLORS["teal"]),
        (0.77, 0.58, "04", "Customer-level\nmart", COLORS["teal"]),
        (0.77, 0.25, "05", "RFM customer\ntagging", COLORS["orange"]),
        (0.53, 0.25, "06", "Lifecycle\nanalysis", COLORS["orange"]),
        (0.29, 0.25, "07", "Campaign\ntargeting", COLORS["red"]),
        (0.05, 0.25, "08", "Tableau\nDashboard", COLORS["red"]),
    ]
    for x, y, number, title, color in steps:
        _add_box(axis, x, y, 0.18, 0.2, f"{number}  {title}", "", color)

    for start_x, end_x in [(0.23, 0.29), (0.47, 0.53), (0.71, 0.77)]:
        _add_arrow(axis, (start_x, 0.68), (end_x, 0.68))
    _add_arrow(axis, (0.86, 0.58), (0.86, 0.45))
    for start_x, end_x in [(0.77, 0.71), (0.53, 0.47), (0.29, 0.23)]:
        _add_arrow(axis, (start_x, 0.35), (end_x, 0.35))

    axis.text(
        0.5,
        0.12,
        "Each analytical output is derived from project tables or generated charts — no synthetic results",
        ha="center",
        va="center",
        fontsize=12,
        color=COLORS["muted"],
    )

    output_path = OUTPUT_DIR / "pipeline_preview.png"
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def build_customer_segmentation_preview() -> Path:
    """从真实用户分层 Dashboard CSV 生成 GitHub 预览图。"""
    if not SEGMENT_SOURCE.exists():
        raise FileNotFoundError(f"缺少真实用户分层数据：{SEGMENT_SOURCE}")

    with SEGMENT_SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    if not rows:
        raise ValueError("用户分层数据为空，无法生成预览图")

    label_map = {
        "其他普通客户": "Other customers",
        "首购未复购客户": "First-purchase only",
        "低价值长期沉默客户": "Low-value dormant",
        "高价值已流失客户": "High-value churned",
        "履约受损客户": "Fulfillment-damaged",
        "高价值流失风险客户": "High-value at risk",
        "高价值活跃客户": "High-value active",
        "重复购买成长客户": "Repeat-growth",
    }
    rows.sort(key=lambda row: int(row["customer_count"]))
    labels = [label_map.get(row["segment"], row["segment"]) for row in rows]
    counts = [int(row["customer_count"]) for row in rows]
    total_customers = sum(counts)
    bar_colors = []
    for label in labels:
        if label == "Fulfillment-damaged":
            bar_colors.append(COLORS["red"])
        elif label == "High-value churned":
            bar_colors.append(COLORS["orange"])
        else:
            bar_colors.append(COLORS["blue"])

    fig, axis = plt.subplots(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor(COLORS["white"])
    bars = axis.barh(labels, counts, color=bar_colors, height=0.64)
    axis.set_title(
        f"Customer Segmentation Preview ({total_customers:,} customers)",
        fontsize=23,
        fontweight="bold",
        color=COLORS["navy"],
        pad=22,
    )
    axis.set_xlabel("Customer count", fontsize=12, color=COLORS["ink"])
    axis.grid(axis="x", color=COLORS["line"], linewidth=0.8, alpha=0.45)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(axis="y", labelsize=11, length=0)
    axis.tick_params(axis="x", labelsize=10, colors=COLORS["muted"])
    axis.set_xlim(0, max(counts) * 1.16)
    for bar, count in zip(bars, counts):
        axis.text(
            count + max(counts) * 0.012,
            bar.get_y() + bar.get_height() / 2,
            f"{count:,}",
            va="center",
            fontsize=11,
            color=COLORS["ink"],
        )
    axis.text(
        0,
        -0.13,
        "Source: outputs/tableau/customer_segment_dashboard.csv",
        transform=axis.transAxes,
        fontsize=10,
        color=COLORS["muted"],
    )
    fig.subplots_adjust(left=0.23, right=0.95, top=0.88, bottom=0.14)

    output_path = OUTPUT_DIR / "customer_segmentation_preview.png"
    fig.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = [
        build_project_architecture(),
        build_customer_segmentation_preview(),
        build_pipeline_preview(),
    ]
    for output in outputs:
        print(output.relative_to(PROJECT_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
