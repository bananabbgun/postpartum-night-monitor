from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.dashboard.service import analyze_uploaded_video


st.set_page_config(page_title="Postpartum Risk Dashboard", layout="wide")


def _save_uploaded_video(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(uploaded_file.getbuffer())
        return Path(handle.name)


def _risk_label(risk_detected: bool) -> str:
    return "Risk detected" if risk_detected else "No risk detected"


STATE_COLORS = {
    "still": "#d9ecff",
    "mixed_motion": "#fff1cc",
    "in_place_active": "#ffd6d6",
    "relocating": "#d8f3dc",
    "no_person": "#efe3ff",
    "unclassified": "#f1f3f5",
}


def _build_motion_figure(frame_df: pd.DataFrame, segments_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(12, 4))
    x = frame_df["timestamp_seconds"].to_numpy()
    local_motion_mean = frame_df["local_motion_mean"].to_numpy()
    centroid_displacement = frame_df["centroid_displacement"].to_numpy()
    person_presence_ratio = frame_df["person_presence_ratio"].to_numpy()

    if not segments_df.empty:
        for _, row in segments_df.iterrows():
            state = row["primitive_state"]
            color = STATE_COLORS.get(state, "#f1f3f5")
            ax.axvspan(row["start_seconds"], row["end_seconds"], color=color, alpha=0.55, lw=0)

    ax.plot(
        x,
        local_motion_mean,
        label="local_motion_mean",
        color="#e67e22",
        linewidth=1.5,
    )
    ax.plot(
        x,
        centroid_displacement,
        label="centroid_displacement",
        color="#2980b9",
        linewidth=1.2,
    )
    ax.plot(
        x,
        person_presence_ratio,
        label="person_presence_ratio",
        color="#27ae60",
        linewidth=1.2,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Metric value")
    ax.set_title("Motion metrics with window-state timeline")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    return fig


st.title("Postpartum Night Monitoring Dashboard")
st.caption("Upload a thermal video, choose bed status and time range, then run the risk check.")

with st.sidebar:
    st.subheader("Basic Inputs")
    room_id = st.text_input("Room ID", value="demo-room")
    bed_occupied = st.radio("Patient in bed?", options=[True, False], format_func=lambda value: "Yes" if value else "No")
    start_seconds = st.number_input("Start second", min_value=0.0, value=0.0, step=0.5)
    end_seconds = st.number_input("End second", min_value=0.0, value=9.0, step=0.5)

    with st.expander("Advanced Parameters", expanded=False):
        smooth_window_seconds = st.number_input("Short window (seconds)", min_value=0.5, value=1.0, step=0.5)
        motion_low_threshold = st.number_input("Motion low threshold", min_value=0.1, value=4.0, step=0.1)
        centroid_low_threshold = st.number_input("Centroid low threshold", min_value=0.1, value=30.0, step=0.5)
        centroid_high_threshold = st.number_input("Centroid high threshold", min_value=0.1, value=70.0, step=0.5)
        mixed_motion_tolerance_seconds = st.number_input("Mixed-motion tolerance (seconds)", min_value=0.0, value=0.5, step=0.1)
        still_tolerance_seconds = st.number_input("Still tolerance (seconds)", min_value=0.0, value=0.5, step=0.1)
        in_bed_active_alert_seconds = st.number_input("In-bed active alert (seconds)", min_value=0.5, value=4.0, step=0.5)
        out_of_bed_still_alert_seconds = st.number_input("Out-of-bed still alert (seconds)", min_value=0.5, value=3.0, step=0.5)
        grace_period_seconds = st.number_input("Out-of-bed grace period (seconds)", min_value=0.0, value=0.0, step=1.0)

    with st.expander("Optional VLM", expanded=False):
        openai_api_key = st.text_input("Gemini API key", type="password")
        openai_model = st.text_input("Gemini model", value="gemini-2.5-flash")

uploaded_video = st.file_uploader("Thermal video (.mp4)", type=["mp4", "mov", "avi"])

if uploaded_video is not None:
    st.video(uploaded_video)

if st.button("Run Analysis", type="primary", disabled=uploaded_video is None):
    video_path = _save_uploaded_video(uploaded_video)
    with st.spinner("Analyzing video..."):
        result = analyze_uploaded_video(
            video_path=video_path,
            room_id=room_id,
            bed_occupied=bed_occupied,
            start_seconds=start_seconds,
            end_seconds=end_seconds if end_seconds > start_seconds else None,
            smooth_window_seconds=smooth_window_seconds,
            motion_low_threshold=motion_low_threshold,
            centroid_low_threshold=centroid_low_threshold,
            centroid_high_threshold=centroid_high_threshold,
            mixed_motion_tolerance_seconds=mixed_motion_tolerance_seconds,
            still_tolerance_seconds=still_tolerance_seconds,
            in_bed_active_alert_seconds=in_bed_active_alert_seconds,
            out_of_bed_still_alert_seconds=out_of_bed_still_alert_seconds,
            out_of_bed_no_person_alert_seconds=None,
            grace_period_seconds=grace_period_seconds,
            grayscale_threshold=90,
            area_threshold=5,
            openai_api_key=openai_api_key or None,
            openai_model=openai_model,
        )

    st.subheader("Result")
    col1, col2 = st.columns(2)
    col1.metric("Risk", _risk_label(result.risk_detected))
    col2.metric("Processed frames", result.processed_frames)

    if result.events:
        st.subheader("Triggered Events")
        events_df = pd.DataFrame(
            [
                {
                    "event_type": event.event_type,
                    "risk_level": event.risk_level,
                    "start_time_seconds": event.start_time_seconds,
                    "duration_seconds": event.duration_seconds,
                    "primitive_state": event.primitive_state,
                    "local_motion_mean": event.local_motion_mean,
                }
                for event in result.events
            ]
        )
        st.dataframe(events_df, use_container_width=True)
    else:
        st.info("No risk event was triggered for this segment.")

    if result.state_segments:
        st.subheader("State Segments")
        segments_df = pd.DataFrame(
            [
                {
                    "primitive_state": segment.primitive_state,
                    "start_seconds": round(segment.start_seconds, 2),
                    "end_seconds": round(segment.end_seconds, 2),
                    "duration_seconds": round(segment.duration_seconds, 2),
                    "frame_count": segment.frame_count,
                }
                for segment in result.state_segments
            ]
        )
        st.dataframe(segments_df, use_container_width=True)
    else:
        segments_df = pd.DataFrame()

    if result.frame_metrics_path is not None:
        frame_df = pd.read_csv(result.frame_metrics_path)
        st.subheader("Motion Chart")
        st.pyplot(_build_motion_figure(frame_df, segments_df), clear_figure=True)
        with st.expander("Raw Frame Metrics", expanded=False):
            st.dataframe(frame_df.tail(20), use_container_width=True)

    if result.risk_detected and result.vlm_result is not None:
        st.subheader("VLM Assessment")
        st.caption(f"Source: {result.vlm_result.source} | Confidence: {result.vlm_result.confidence}")

        if result.vlm_result.source != "gemini" and result.vlm_result.raw_response:
            fallback_reason = result.vlm_result.raw_response.get("fallback_reason")
            if fallback_reason:
                st.warning(f"VLM fallback reason: {fallback_reason}")

        support_needed = "Yes" if result.vlm_result.decision in {"nurse_review", "immediate_nurse_support", "Needs nurse review", "Needs immediate nurse support"} else "No / monitor"

        card_left, card_right = st.columns(2)
        with card_left:
            st.markdown("**Patient Judgment**")
            st.info(result.vlm_result.patient_judgment or result.vlm_result.summary)

            st.markdown("**Nurse Support Needed**")
            st.warning(support_needed)

        with card_right:
            st.markdown("**Decision Reason**")
            st.write(result.vlm_result.decision_reason or result.vlm_result.summary)

            st.markdown("**Recommended Action**")
            st.success(result.vlm_result.recommended_action)

        if result.vlm_result.possible_situations:
            st.markdown("**Possible Situations**")
            for item in result.vlm_result.possible_situations:
                st.write(f"- {item}")

st.markdown(
    """
Run locally with:

```bash
streamlit run app/dashboard/streamlit_app.py
```
"""
)
