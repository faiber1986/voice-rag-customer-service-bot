"""Reads logs/latency.jsonl and produces the Phase 3 before/after comparison:
Phase 2 (pipeline="sequential") vs Phase 3 (pipeline="streaming").

The headline number is "time to first audio": for sequential, that's the sum
of every stage's full duration up to and including tts's completion (no
audio exists until everything is done); for streaming, that's stt.duration +
retrieval.duration + tts.time_to_first_partial (the first sentence chunk is
audible while the LLM and remaining TTS chunks are still in flight).

Run as: python -m scripts.latency_report
"""

import json
from pathlib import Path
from statistics import mean

from app.config import settings

OUT_DIR = Path("docs/latency")


def _load_records() -> list[dict]:
    path = Path(settings.latency_log_path)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _group_by_request(records: list[dict], pipeline: str) -> dict[str, dict[str, dict]]:
    by_request: dict[str, dict[str, dict]] = {}
    for r in records:
        if r.get("pipeline") != pipeline:
            continue
        by_request.setdefault(r["request_id"], {})[r["stage"]] = r
    return by_request


def _time_to_first_audio_sequential(stages: dict[str, dict]) -> float | None:
    required = ("stt", "retrieval", "llm", "tts")
    if not all(s in stages for s in required):
        return None
    return sum(stages[s]["duration_ms"] for s in required)


def _time_to_first_audio_streaming(stages: dict[str, dict]) -> float | None:
    if not all(s in stages for s in ("stt", "retrieval", "tts")):
        return None
    tts = stages["tts"]
    if "time_to_first_partial_ms" not in tts:
        return None
    return stages["stt"]["duration_ms"] + stages["retrieval"]["duration_ms"] + tts["time_to_first_partial_ms"]


def _per_stage_avg(by_request: dict[str, dict[str, dict]], stage: str) -> float | None:
    values = [r[stage]["duration_ms"] for r in by_request.values() if stage in r]
    return mean(values) if values else None


def _internal_overlap_stats(
    by_request: dict[str, dict[str, dict]], stage: str
) -> tuple[float, float, float] | None:
    """For streaming requests: mean(full stage duration), mean(time to first
    partial), and the % reduction between them. This isolates the overlap
    benefit (first output vs. waiting for the whole stage to finish) without
    the STT double-transcription confound described in the report notes.
    """
    durations, firsts = [], []
    for stages in by_request.values():
        record = stages.get(stage)
        if record and "time_to_first_partial_ms" in record:
            durations.append(record["duration_ms"])
            firsts.append(record["time_to_first_partial_ms"])
    if not durations:
        return None
    mean_duration, mean_first = mean(durations), mean(firsts)
    reduction_pct = (1 - mean_first / mean_duration) * 100 if mean_duration else 0
    return mean_duration, mean_first, reduction_pct


def build_report() -> str:
    records = _load_records()
    sequential = _group_by_request(records, "sequential")
    streaming = _group_by_request(records, "streaming")

    seq_ttfa = [v for r in sequential.values() if (v := _time_to_first_audio_sequential(r)) is not None]
    stream_ttfa = [v for r in streaming.values() if (v := _time_to_first_audio_streaming(r)) is not None]

    lines = ["# Latency Report: Sequential (Phase 2) vs Streaming (Phase 3)", ""]
    lines.append(f"Sample size: {len(seq_ttfa)} sequential requests, {len(stream_ttfa)} streaming requests.")
    lines.append("")

    lines.append("## Time to first audio byte (perceived latency, SM-1)")
    lines.append("")
    lines.append("| Pipeline | Mean (ms) | Min (ms) | Max (ms) |")
    lines.append("| --- | --- | --- | --- |")
    if seq_ttfa:
        lines.append(f"| Sequential (Phase 2) | {mean(seq_ttfa):.0f} | {min(seq_ttfa):.0f} | {max(seq_ttfa):.0f} |")
    if stream_ttfa:
        lines.append(f"| Streaming (Phase 3) | {mean(stream_ttfa):.0f} | {min(stream_ttfa):.0f} | {max(stream_ttfa):.0f} |")
    lines.append("")

    if seq_ttfa and stream_ttfa:
        seq_mean, stream_mean = mean(seq_ttfa), mean(stream_ttfa)
        reduction_pct = (1 - stream_mean / seq_mean) * 100 if seq_mean else 0
        lines.append(
            f"**Streaming reduced average time-to-first-audio by {reduction_pct:.1f}% "
            f"({seq_mean:.0f}ms -> {stream_mean:.0f}ms).**"
        )
        lines.append("")

    lines.append("## Per-stage average duration (ms)")
    lines.append("")
    lines.append("| Stage | Sequential | Streaming |")
    lines.append("| --- | --- | --- |")
    for stage in ("stt", "retrieval", "llm", "tts"):
        seq_avg = _per_stage_avg(sequential, stage)
        stream_avg = _per_stage_avg(streaming, stage)
        seq_str = f"{seq_avg:.0f}" if seq_avg is not None else "n/a"
        stream_str = f"{stream_avg:.0f}" if stream_avg is not None else "n/a"
        lines.append(f"| {stage} | {seq_str} | {stream_str} |")
    lines.append("")

    lines.append(
        "SM-1 target: <1500ms perceived latency. Real numbers above are reported "
        "as measured on this local CPU-only stack, whether or not they meet the "
        "target (Constitution Principle III)."
    )
    lines.append("")

    llm_overlap = _internal_overlap_stats(streaming, "llm")
    tts_overlap = _internal_overlap_stats(streaming, "tts")

    lines.append("## Streaming's internal overlap (isolated from the STT confound)")
    lines.append("")
    lines.append(
        "The top-line time-to-first-audio comparison above is confounded by "
        "this project's streaming STT approach (periodic re-transcription of a "
        "growing buffer, since faster-whisper has no incremental decoder — see "
        "specs/003-streaming-e2e/plan.md Complexity Tracking): on this "
        "project's short (~2s) test questions, re-transcribing twice roughly "
        "doubles STT cost, which can outweigh the LLM/TTS overlap savings for "
        "single-sentence answers. The metrics below isolate the actual claim — "
        "does streaming reduce the wait for *some* output vs. the *complete* "
        "output — independent of STT."
    )
    lines.append("")
    lines.append("| Stage | Mean full duration (ms) | Mean time-to-first-output (ms) | Reduction |")
    lines.append("| --- | --- | --- | --- |")
    if llm_overlap:
        d, f, pct = llm_overlap
        lines.append(f"| LLM (first token vs. full answer) | {d:.0f} | {f:.0f} | {pct:.1f}% |")
    if tts_overlap:
        d, f, pct = tts_overlap
        lines.append(f"| TTS (first audio chunk vs. all chunks) | {d:.0f} | {f:.0f} | {pct:.1f}% |")
    lines.append("")
    lines.append(
        "These numbers answer \"why does streaming matter?\" directly: the user "
        "hears the first words/audio well before the full answer exists — this "
        "is the streaming benefit demonstrated with this project's own data "
        "(SPEC section 11)."
    )
    lines.append("")

    return "\n".join(lines), seq_ttfa, stream_ttfa


def _write_chart(seq_ttfa: list[float], stream_ttfa: list[float]) -> Path | None:
    if not seq_ttfa or not stream_ttfa:
        return None

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5, 4))
    labels = ["Sequential\n(Phase 2)", "Streaming\n(Phase 3)"]
    values = [mean(seq_ttfa), mean(stream_ttfa)]
    colors = ["#94a3b8", "#2563eb"]
    ax.bar(labels, values, color=colors)
    ax.set_ylabel("Time to first audio byte (ms)")
    ax.set_title("Perceived latency: sequential vs. streaming")
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.0f}ms", ha="center", va="bottom")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    chart_path = OUT_DIR / "comparison.png"
    fig.tight_layout()
    fig.savefig(chart_path, dpi=150)
    plt.close(fig)
    return chart_path


def main() -> None:
    report_text, seq_ttfa, stream_ttfa = build_report()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "report.md"
    report_path.write_text(report_text, encoding="utf-8")

    chart_path = _write_chart(seq_ttfa, stream_ttfa)

    print(f"Wrote {report_path}")
    if chart_path:
        print(f"Wrote {chart_path}")
    else:
        print("No chart written (insufficient data in one or both pipelines).")


if __name__ == "__main__":
    main()
