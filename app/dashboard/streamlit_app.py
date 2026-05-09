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

from app.dashboard.service import DashboardRunResult, analyze_uploaded_video


st.set_page_config(page_title="Postpartum Risk Dashboard", layout="wide")


STATE_COLORS = {
    "still": "#d7e8ff",
    "mixed_motion": "#ffe4b8",
    "in_place_active": "#ffd0d0",
    "relocating": "#d5f0df",
    "no_person": "#ece2ff",
    "unclassified": "#edf0f2",
}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(255, 214, 184, 0.35), transparent 26%),
                radial-gradient(circle at top right, rgba(184, 224, 255, 0.35), transparent 24%),
                linear-gradient(180deg, #f7f4ee 0%, #fbfaf7 100%);
        }
        .block-container {
            padding-top: 2.2rem;
            padding-bottom: 3rem;
            max-width: 1240px;
        }
        .hero-panel {
            border: 1px solid rgba(34, 54, 38, 0.08);
            background: rgba(255, 252, 247, 0.88);
            border-radius: 24px;
            padding: 1.4rem 1.5rem;
            box-shadow: 0 18px 45px rgba(94, 78, 55, 0.08);
            margin-bottom: 1rem;
        }
        .hero-kicker {
            font-size: 0.78rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: #8c5a35;
            font-weight: 700;
        }
        .hero-title {
            font-size: 2rem;
            line-height: 1.05;
            color: #233628;
            margin: 0.2rem 0 0.5rem 0;
            font-weight: 700;
        }
        .hero-copy {
            color: #526154;
            font-size: 0.98rem;
            margin: 0;
        }
        .summary-card {
            border-radius: 20px;
            padding: 1rem 1.1rem;
            border: 1px solid rgba(34, 54, 38, 0.08);
            background: rgba(255, 255, 255, 0.84);
            box-shadow: 0 12px 30px rgba(89, 73, 50, 0.08);
        }
        .summary-label {
            color: #6f7c71;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }
        .summary-value {
            color: #1f3525;
            font-size: 1.9rem;
            line-height: 1.1;
            font-weight: 700;
            margin-top: 0.35rem;
        }
        .status-chip {
            display: inline-block;
            border-radius: 999px;
            padding: 0.28rem 0.8rem;
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.03em;
        }
        .status-risk {
            background: #ffe0da;
            color: #9c2b22;
        }
        .status-safe {
            background: #dff3e5;
            color: #256941;
        }
        .detail-card {
            border-radius: 20px;
            padding: 1rem 1.1rem;
            border: 1px solid rgba(34, 54, 38, 0.08);
            background: rgba(255, 255, 255, 0.86);
        }
        .section-note {
            color: #627266;
            font-size: 0.92rem;
        }
        div[data-testid="stDataFrame"] {
            border-radius: 18px;
            overflow: hidden;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _save_uploaded_video(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(uploaded_file.getbuffer())
        return Path(handle.name)


def _risk_chip(risk_detected: bool) -> str:
    if risk_detected:
        return '<span class="status-chip status-risk">Risk detected</span>'
    return '<span class="status-chip status-safe">No risk</span>'


def _build_motion_figure(frame_df: pd.DataFrame, segments_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(12, 4))
    x = frame_df["timestamp_seconds"].to_numpy()
    local_motion_mean = frame_df["local_motion_mean"].to_numpy()
    centroid_displacement = frame_df["centroid_displacement"].to_numpy()
    person_presence_ratio = frame_df["person_presence_ratio"].to_numpy()

    if not segments_df.empty:
        for _, row in segments_df.iterrows():
            state = row["primitive_state"]
            color = STATE_COLORS.get(state, "#edf0f2")
            ax.axvspan(row["start_seconds"], row["end_seconds"], color=color, alpha=0.55, lw=0)

    ax.plot(x, local_motion_mean, label="local_motion_mean", color="#c96720", linewidth=1.6)
    ax.plot(x, centroid_displacement, label="centroid_displacement", color="#256fa5", linewidth=1.3)
    ax.plot(x, person_presence_ratio, label="person_presence_ratio", color="#2c8a57", linewidth=1.2)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Metric value")
    ax.set_title("Primitive timeline and motion metrics")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.18)
    fig.tight_layout()
    return fig


def _render_summary_cards(results: list[dict]) -> None:
    total = len(results)
    risky = sum(1 for item in results if item["result"].risk_detected)
    safe = total - risky
    total_events = sum(len(item["result"].events) for item in results)

    col1, col2, col3, col4 = st.columns(4)
    cards = [
        ("Uploaded Clips", total),
        ("Risk Clips", risky),
        ("Safe Clips", safe),
        ("Triggered Events", total_events),
    ]
    for column, (label, value) in zip((col1, col2, col3, col4), cards):
        column.markdown(
            f"""
            <div class="summary-card">
                <div class="summary-label">{label}</div>
                <div class="summary-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _build_overview_table(results: list[dict]) -> pd.DataFrame:
    rows = []
    for item in results:
        result: DashboardRunResult = item["result"]
        event = result.events[0] if result.events else None
        rows.append(
            {
                "video_name": item["name"],
                "risk": "Risk" if result.risk_detected else "Safe",
                "event_count": len(result.events),
                "primary_event": event.event_type if event else "-",
                "start_time_seconds": round(event.start_time_seconds, 2) if event else None,
                "duration_seconds": round(event.duration_seconds, 2) if event else None,
                "processed_frames": result.processed_frames,
            }
        )
    return pd.DataFrame(rows)


def _render_vlm_panel(result: DashboardRunResult) -> None:
    if not result.risk_detected or result.vlm_result is None:
        return

    st.markdown("### Clinical Summary")
    st.caption(f"Source: {result.vlm_result.source} | Confidence: {result.vlm_result.confidence}")

    if result.vlm_result.source != "gemini" and result.vlm_result.raw_response:
        fallback_reason = result.vlm_result.raw_response.get("fallback_reason")
        if fallback_reason:
            st.warning(f"VLM fallback reason: {fallback_reason}")

    support_needed = (
        "需要"
        if result.vlm_result.decision in {"nurse_review", "immediate_nurse_support", "Needs nurse review", "Needs immediate nurse support"}
        else "暫不需要"
    )

    left, right = st.columns(2)
    with left:
        st.markdown('<div class="detail-card">', unsafe_allow_html=True)
        st.markdown("**病人判斷**")
        st.write(result.vlm_result.patient_judgment or result.vlm_result.summary)
        st.markdown("**是否需要護理師支援**")
        st.write(support_needed)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="detail-card">', unsafe_allow_html=True)
        st.markdown("**決策理由**")
        st.write(result.vlm_result.decision_reason or result.vlm_result.summary)
        st.markdown("**建議處置**")
        st.write(result.vlm_result.recommended_action)
        st.markdown("</div>", unsafe_allow_html=True)

    if result.vlm_result.possible_situations:
        st.markdown("**可能情境**")
        for item in result.vlm_result.possible_situations:
            st.write(f"- {item}")


def _render_detail(selected_item: dict) -> None:
    result: DashboardRunResult = selected_item["result"]
    st.markdown(f"## {selected_item['name']}")
    st.markdown(_risk_chip(result.risk_detected), unsafe_allow_html=True)

    meta1, meta2, meta3 = st.columns(3)
    meta1.metric("Processed frames", result.processed_frames)
    meta2.metric("Triggered events", len(result.events))
    meta3.metric("State segments", len(result.state_segments))

    if selected_item["video"] is not None:
        with st.expander("Preview Clip", expanded=False):
            st.video(selected_item["video"])

    if result.events:
        st.markdown("### Triggered Events")
        events_df = pd.DataFrame(
            [
                {
                    "event_type": event.event_type,
                    "risk_level": event.risk_level,
                    "start_time_seconds": round(event.start_time_seconds, 2),
                    "duration_seconds": round(event.duration_seconds, 2),
                    "primitive_state": event.primitive_state,
                    "local_motion_mean": round(event.local_motion_mean, 2) if event.local_motion_mean is not None else None,
                }
                for event in result.events
            ]
        )
        st.dataframe(events_df, use_container_width=True, hide_index=True)
    else:
        st.info("No risk event was triggered for this clip.")

    if result.state_segments:
        st.markdown("### State Segments")
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
        st.dataframe(segments_df, use_container_width=True, hide_index=True)
    else:
        segments_df = pd.DataFrame()

    if result.frame_metrics_path is not None:
        frame_df = pd.read_csv(result.frame_metrics_path)
        st.markdown("### Motion Timeline")
        st.pyplot(_build_motion_figure(frame_df, segments_df), clear_figure=True)
        with st.expander("Raw Frame Metrics", expanded=False):
            st.dataframe(frame_df.tail(30), use_container_width=True, hide_index=True)

    _render_vlm_panel(result)


_inject_styles()

st.markdown(
    """
    <div class="hero-panel">
        <div class="hero-kicker">Thermal Monitoring Console</div>
        <div class="hero-title">Postpartum Night Risk Review</div>
        <p class="hero-copy">
            Upload one or more thermal clips, run the current primitive-and-episode pipeline,
            and review the risk summary with clip-level detail.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Batch Inputs")
    room_id = st.text_input("Room ID", value="demo-room")
    bed_occupied = st.radio("Patient in bed?", options=[True, False], format_func=lambda value: "Yes" if value else "No")
    start_seconds = st.number_input("Start second", min_value=0.0, value=0.0, step=0.5)
    end_seconds = st.number_input("End second", min_value=0.0, value=9.0, step=0.5)

    with st.expander("Detection Parameters", expanded=False):
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

uploaded_videos = st.file_uploader(
    "Thermal videos (.mp4/.mov/.avi)",
    type=["mp4", "mov", "avi"],
    accept_multiple_files=True,
)

if uploaded_videos:
    names = ", ".join(file.name for file in uploaded_videos[:4])
    extra = "" if len(uploaded_videos) <= 4 else f" +{len(uploaded_videos) - 4} more"
    st.markdown(f'<p class="section-note">{len(uploaded_videos)} clip(s) ready: {names}{extra}</p>', unsafe_allow_html=True)

run_clicked = st.button("Run Batch Analysis", type="primary", disabled=not uploaded_videos)

if run_clicked and uploaded_videos:
    results: list[dict] = []
    progress = st.progress(0.0, text="Preparing analysis...")

    for index, uploaded_video in enumerate(uploaded_videos, start=1):
        video_path = _save_uploaded_video(uploaded_video)
        progress.progress((index - 1) / len(uploaded_videos), text=f"Analyzing {uploaded_video.name} ({index}/{len(uploaded_videos)})")
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
        results.append({"name": uploaded_video.name, "result": result, "video": uploaded_video})

    progress.progress(1.0, text="Batch analysis complete.")
    st.session_state["dashboard_batch_results"] = results

results = st.session_state.get("dashboard_batch_results", [])

if results:
    _render_summary_cards(results)
    st.markdown("### Batch Overview")
    st.dataframe(_build_overview_table(results), use_container_width=True, hide_index=True)

    detail_names = [item["name"] for item in results]
    default_index = next((idx for idx, item in enumerate(results) if item["result"].risk_detected), 0)
    selected_name = st.selectbox("Detailed clip view", detail_names, index=default_index)
    selected_item = next(item for item in results if item["name"] == selected_name)
    _render_detail(selected_item)

st.markdown(
    """
    <div class="section-note" style="margin-top: 1.25rem;">
        Run locally with <code>streamlit run app/dashboard/streamlit_app.py</code>
    </div>
    """,
    unsafe_allow_html=True,
)
