# Postpartum Monitoring MVP Scaffold

This repository now includes a first-pass rule-based scaffold for the postpartum night monitoring MVP.

## What is implemented

- Unified input pipeline for `mp4` videos and PNG image sequences
- Mock `bed_occupied` label loader from CSV
- Thermal grayscale thresholding for `person_detected`
- Frame-difference movement score
- Sliding-window smoothing
- Motion state classification: `still`, `minor_motion`, `high_motion`, `relocating`
- Rule-based event detection for:
  - `bed_high_motion`
  - `out_of_bed_stillness`
  - `out_of_bed_unknown_location`
- Debug outputs:
  - `outputs/frame_metrics.csv`
  - `outputs/events.jsonl`

## Run

```bash
python -m scripts.run_demo --mode video --start-seconds 5 --end-seconds 9 --smooth-window-seconds 3
```

Or with the image dataset:

```bash
python -m scripts.run_demo --mode image_sequence --max-frames 300 --smooth-window-seconds 3
```

Threshold analysis:

```bash
python -m scripts.analyze_thresholds
```

Dashboard:

```bash
streamlit run app/dashboard/streamlit_app.py
```

## Notes

- `high_motion` now means: centroid stays roughly in place, but local motion persists through most of the window.
- `relocating` now means: centroid drifts far enough in a consistent direction, so the person is treated as moving position rather than agitated in place.
- `python -m scripts.analyze_thresholds` writes per-clip plots plus `outputs/analysis/threshold_summary.csv` for threshold tuning.
- `streamlit run app/dashboard/streamlit_app.py` launches a local dashboard for uploaded videos, manual bed-status input, and optional VLM assessment on risky events.
- This is an architecture scaffold, not a clinically valid detector.
- The current thresholds are placeholders and should be recalibrated once real bedside thermal data is available.
- `app/mocks/sample_bed_labels.csv` is only for pipeline validation.
