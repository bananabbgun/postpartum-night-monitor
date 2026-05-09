from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean

import matplotlib.pyplot as plt

from app.config import AppConfig, ROOT_DIR
from app.main import run_pipeline


VIDEO_DIR = ROOT_DIR / "Thermal camera video-20260502T062433Z-3-001" / "Thermal camera video"
ANALYSIS_DIR = ROOT_DIR / "outputs" / "analysis"

DEFAULT_CLIPS = [
    {"name": "moving", "file": "moving.mp4", "start": 5.0, "end": 9.0},
    {"name": "standing", "file": "standing.mp4", "start": 3.0, "end": 8.0},
    {"name": "standing_moving", "file": "standing_moving.mp4", "start": 0.0, "end": 10.0},
    {"name": "sitting_large_moving", "file": "sitting_large_moving.mp4", "start": 0.0, "end": 12.0},
    {"name": "inbedscrolling_up", "file": "inbedscrolling上.mp4", "start": 0.0, "end": 15.0},
    {"name": "inbedscrolling_down", "file": "inbedscrolling下.mp4", "start": 0.0, "end": 15.0},
]

STATE_ORDER = ["still", "minor_motion", "high_motion", "relocating", "no_person", ""]
STATE_COLORS = {
    "still": "#4c78a8",
    "minor_motion": "#f58518",
    "high_motion": "#e45756",
    "relocating": "#72b7b2",
    "no_person": "#b279a2",
    "": "#bab0ac",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze window-state thresholds across thermal clips.")
    parser.add_argument("--smooth-window-seconds", type=float, default=3.0)
    parser.add_argument("--local-motion-threshold", type=float, default=5.0)
    parser.add_argument("--high-motion-persistence-ratio", type=float, default=0.75)
    parser.add_argument("--centroid-motion-threshold", type=float, default=60.0)
    parser.add_argument("--centroid-motion-consistency-threshold", type=float, default=0.75)
    parser.add_argument("--person-presence-ratio-threshold", type=float, default=0.4)
    parser.add_argument("--grayscale-threshold", type=int, default=180)
    parser.add_argument("--area-threshold", type=int, default=5)
    return parser.parse_args()


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_float(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "")
    if value in ("", "None", None):
        return None
    return float(value)


def summarize_rows(clip_name: str, rows: list[dict[str, str]]) -> dict[str, object]:
    states: dict[str, int] = {}
    local_means = []
    centroid_disp = []
    persistence = []
    consistency = []
    presence = []

    for row in rows:
        state = row["window_state"]
        states[state] = states.get(state, 0) + 1
        for target, key in (
            (local_means, "local_motion_mean"),
            (centroid_disp, "centroid_displacement"),
            (persistence, "local_motion_persistence"),
            (consistency, "centroid_motion_consistency"),
            (presence, "person_presence_ratio"),
        ):
            value = parse_float(row, key)
            if value is not None:
                target.append(value)

    return {
        "clip_name": clip_name,
        "frames": len(rows),
        "start_seconds": rows[0]["timestamp_seconds"] if rows else "",
        "end_seconds": rows[-1]["timestamp_seconds"] if rows else "",
        "state_counts": states,
        "local_motion_avg": mean(local_means) if local_means else None,
        "local_motion_max": max(local_means) if local_means else None,
        "centroid_disp_avg": mean(centroid_disp) if centroid_disp else None,
        "centroid_disp_max": max(centroid_disp) if centroid_disp else None,
        "persistence_avg": mean(persistence) if persistence else None,
        "persistence_max": max(persistence) if persistence else None,
        "consistency_avg": mean(consistency) if consistency else None,
        "consistency_max": max(consistency) if consistency else None,
        "presence_avg": mean(presence) if presence else None,
        "presence_max": max(presence) if presence else None,
    }


def plot_clip(clip_name: str, rows: list[dict[str, str]], output_path: Path, config: AppConfig) -> None:
    timestamps = [float(row["timestamp_seconds"]) for row in rows]
    local_means = [parse_float(row, "local_motion_mean") for row in rows]
    centroid_disp = [parse_float(row, "centroid_displacement") for row in rows]
    persistence = [parse_float(row, "local_motion_persistence") for row in rows]
    consistency = [parse_float(row, "centroid_motion_consistency") for row in rows]
    presence = [parse_float(row, "person_presence_ratio") for row in rows]
    states = [row["window_state"] for row in rows]

    fig, axes = plt.subplots(5, 1, figsize=(12, 12), sharex=True)
    fig.suptitle(f"{clip_name} threshold analysis", fontsize=14)

    axes[0].plot(timestamps, local_means, color="#f58518", label="local_motion_mean")
    axes[0].axhline(config.local_motion_threshold, color="#e45756", linestyle="--", label="local_motion_threshold")
    axes[0].set_ylabel("Local")
    axes[0].legend(loc="upper right")

    axes[1].plot(timestamps, persistence, color="#54a24b", label="local_motion_persistence")
    axes[1].axhline(config.high_motion_persistence_ratio, color="#e45756", linestyle="--", label="persistence_threshold")
    axes[1].set_ylabel("Persistence")
    axes[1].legend(loc="upper right")

    axes[2].plot(timestamps, centroid_disp, color="#4c78a8", label="centroid_displacement")
    axes[2].axhline(config.centroid_motion_threshold, color="#e45756", linestyle="--", label="displacement_threshold")
    axes[2].plot(timestamps, consistency, color="#b279a2", label="centroid_consistency")
    axes[2].axhline(
        config.centroid_motion_consistency_threshold,
        color="#9d755d",
        linestyle=":",
        label="consistency_threshold",
    )
    axes[2].set_ylabel("Centroid")
    axes[2].legend(loc="upper right")

    axes[3].plot(timestamps, presence, color="#72b7b2", label="person_presence_ratio")
    axes[3].axhline(
        config.person_presence_ratio_threshold,
        color="#e45756",
        linestyle="--",
        label="presence_threshold",
    )
    axes[3].set_ylabel("Presence")
    axes[3].legend(loc="upper right")

    state_to_y = {"still": 0, "minor_motion": 1, "high_motion": 2, "relocating": 3, "no_person": 4, "": -1}
    axes[4].scatter(timestamps, [state_to_y[state] for state in states], c=[STATE_COLORS[state] for state in states], s=14)
    axes[4].set_yticks([0, 1, 2, 3, 4])
    axes[4].set_yticklabels(["still", "minor", "high", "reloc", "no_person"])
    axes[4].set_xlabel("Time (s)")
    axes[4].set_ylabel("State")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_state_distribution(summaries: list[dict[str, object]], output_path: Path) -> None:
    labels = [summary["clip_name"] for summary in summaries]
    fig, ax = plt.subplots(figsize=(12, 6))
    bottoms = [0] * len(labels)
    for state in STATE_ORDER:
        counts = [summary["state_counts"].get(state, 0) for summary in summaries]
        ax.bar(labels, counts, bottom=bottoms, color=STATE_COLORS[state], label=state or "unclassified")
        bottoms = [bottom + count for bottom, count in zip(bottoms, counts)]
    ax.set_ylabel("Frame count")
    ax.set_title("Window state distribution by clip")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def write_summary_csv(summaries: list[dict[str, object]], output_path: Path) -> None:
    fieldnames = [
        "clip_name",
        "frames",
        "start_seconds",
        "end_seconds",
        "local_motion_avg",
        "local_motion_max",
        "centroid_disp_avg",
        "centroid_disp_max",
        "persistence_avg",
        "persistence_max",
        "consistency_avg",
        "consistency_max",
        "presence_avg",
        "presence_max",
        "still_frames",
        "minor_motion_frames",
        "high_motion_frames",
        "relocating_frames",
        "no_person_frames",
        "unclassified_frames",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(
                {
                    "clip_name": summary["clip_name"],
                    "frames": summary["frames"],
                    "start_seconds": summary["start_seconds"],
                    "end_seconds": summary["end_seconds"],
                    "local_motion_avg": summary["local_motion_avg"],
                    "local_motion_max": summary["local_motion_max"],
                    "centroid_disp_avg": summary["centroid_disp_avg"],
                    "centroid_disp_max": summary["centroid_disp_max"],
                    "persistence_avg": summary["persistence_avg"],
                    "persistence_max": summary["persistence_max"],
                    "consistency_avg": summary["consistency_avg"],
                    "consistency_max": summary["consistency_max"],
                    "presence_avg": summary["presence_avg"],
                    "presence_max": summary["presence_max"],
                    "still_frames": summary["state_counts"].get("still", 0),
                    "minor_motion_frames": summary["state_counts"].get("minor_motion", 0),
                    "high_motion_frames": summary["state_counts"].get("high_motion", 0),
                    "relocating_frames": summary["state_counts"].get("relocating", 0),
                    "no_person_frames": summary["state_counts"].get("no_person", 0),
                    "unclassified_frames": summary["state_counts"].get("", 0),
                }
            )


def main() -> None:
    args = parse_args()
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    config_kwargs = {
        "smooth_window_seconds": args.smooth_window_seconds,
        "local_motion_threshold": args.local_motion_threshold,
        "high_motion_persistence_ratio": args.high_motion_persistence_ratio,
        "centroid_motion_threshold": args.centroid_motion_threshold,
        "centroid_motion_consistency_threshold": args.centroid_motion_consistency_threshold,
        "person_presence_ratio_threshold": args.person_presence_ratio_threshold,
        "grayscale_threshold": args.grayscale_threshold,
        "area_threshold": args.area_threshold,
        "max_frames": None,
    }

    summaries = []
    for clip in DEFAULT_CLIPS:
        clip_output_dir = ANALYSIS_DIR / clip["name"]
        config = AppConfig(
            video_path=VIDEO_DIR / clip["file"],
            output_dir=clip_output_dir,
            start_seconds=clip["start"],
            end_seconds=clip["end"],
            room_id=clip["name"],
            **config_kwargs,
        )
        run_pipeline(config)
        rows = load_rows(clip_output_dir / "frame_metrics.csv")
        summaries.append(summarize_rows(clip["name"], rows))
        plot_clip(clip["name"], rows, clip_output_dir / "threshold_plot.png", config)

    write_summary_csv(summaries, ANALYSIS_DIR / "threshold_summary.csv")
    plot_state_distribution(summaries, ANALYSIS_DIR / "state_distribution.png")

    print(f"Analysis written to: {ANALYSIS_DIR}")
    for summary in summaries:
        print(
            f"{summary['clip_name']}: "
            f"still={summary['state_counts'].get('still', 0)}, "
            f"minor={summary['state_counts'].get('minor_motion', 0)}, "
            f"high={summary['state_counts'].get('high_motion', 0)}, "
            f"reloc={summary['state_counts'].get('relocating', 0)}, "
            f"no_person={summary['state_counts'].get('no_person', 0)}"
        )


if __name__ == "__main__":
    main()
