from __future__ import annotations

import argparse

from app.config import AppConfig
from app.main import describe_result, run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the postpartum monitoring MVP scaffold.")
    parser.add_argument("--mode", choices=["video", "image_sequence"], default="video")
    parser.add_argument("--max-frames", type=int, default=300)
    parser.add_argument("--room-id", default="demo-room")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--end-seconds", type=float, default=None)
    parser.add_argument("--smooth-window-seconds", type=float, default=3.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig(
        input_mode=args.mode,
        max_frames=args.max_frames,
        room_id=args.room_id,
        start_seconds=args.start_seconds,
        end_seconds=args.end_seconds,
        smooth_window_seconds=args.smooth_window_seconds,
    )
    result = run_pipeline(config)
    print(describe_result(result))


if __name__ == "__main__":
    main()
