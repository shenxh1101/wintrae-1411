from dataclasses import dataclass, field
from typing import List, Dict, Any
from ..models import SubtitleFile, SubtitleCue
from .scan import format_ms


@dataclass
class HighRiskSentence:
    cue_index: int
    start_time: str
    text: str
    words_per_minute: float
    risk_level: str
    reason: str


@dataclass
class SubtitleStats:
    file: str
    total_cues: int
    total_duration_ms: int
    total_chars: int
    total_words: int
    total_lines: int
    words_per_minute: float
    chars_per_minute: float
    avg_duration_per_cue: float
    avg_words_per_cue: float
    avg_chars_per_cue: float
    avg_lines_per_cue: float
    max_duration_cue: Dict[str, Any]
    min_duration_cue: Dict[str, Any]
    max_words_cue: Dict[str, Any]
    high_risk_sentences: List[HighRiskSentence] = field(default_factory=list)
    speaker_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def calculate_words_per_minute(cue: SubtitleCue) -> float:
    if cue.duration_ms <= 0 or cue.word_count == 0:
        return 0.0
    minutes = cue.duration_ms / 60000.0
    return cue.word_count / minutes


def check_high_risk(cue: SubtitleCue, wpm_threshold: float = 200,
                    min_duration_ms: int = 300) -> HighRiskSentence:
    if cue.is_empty:
        return None
    wpm = calculate_words_per_minute(cue)
    reasons = []
    risk_level = "low"

    if wpm > wpm_threshold:
        reasons.append(f"语速过快: {wpm:.1f} 词/分钟")
        risk_level = "high"
    elif wpm > wpm_threshold * 0.8:
        reasons.append(f"语速偏快: {wpm:.1f} 词/分钟")
        risk_level = "medium"

    if cue.duration_ms < min_duration_ms:
        reasons.append(f"时长过短: {cue.duration_ms}ms")
        if risk_level == "low":
            risk_level = "medium"

    if len(cue.lines) > 3:
        reasons.append(f"行数过多: {len(cue.lines)}行")
        if risk_level == "low":
            risk_level = "medium"

    if reasons:
        return HighRiskSentence(
            cue_index=cue.index,
            start_time=format_ms(cue.start_ms),
            text=cue.text,
            words_per_minute=wpm,
            risk_level=risk_level,
            reason="; ".join(reasons)
        )
    return None


def analyze_subtitle(subfile: SubtitleFile, **options) -> SubtitleStats:
    wpm_threshold = options.get('wpm_threshold', 200)
    min_duration_ms = options.get('min_duration_ms', 300)

    total_duration_ms = subfile.total_duration_ms
    total_minutes = total_duration_ms / 60000.0 if total_duration_ms > 0 else 0

    high_risk = []
    speaker_stats = {}

    for cue in subfile.cues:
        risk = check_high_risk(cue, wpm_threshold, min_duration_ms)
        if risk:
            high_risk.append(risk)

        speaker = cue.speaker or "未知"
        if speaker not in speaker_stats:
            speaker_stats[speaker] = {
                "cue_count": 0,
                "total_words": 0,
                "total_chars": 0,
                "total_duration_ms": 0
            }
        speaker_stats[speaker]["cue_count"] += 1
        speaker_stats[speaker]["total_words"] += cue.word_count
        speaker_stats[speaker]["total_chars"] += cue.char_count
        speaker_stats[speaker]["total_duration_ms"] += cue.duration_ms

    for speaker in speaker_stats:
        stats = speaker_stats[speaker]
        duration_min = stats["total_duration_ms"] / 60000.0 if stats["total_duration_ms"] > 0 else 0
        stats["words_per_minute"] = stats["total_words"] / duration_min if duration_min > 0 else 0

    max_duration_cue = max(subfile.cues, key=lambda c: c.duration_ms) if subfile.cues else None
    min_duration_cue = min(subfile.cues, key=lambda c: c.duration_ms) if subfile.cues else None
    max_words_cue = max(subfile.cues, key=lambda c: c.word_count) if subfile.cues else None

    avg_duration = subfile.cues[-1].duration_ms if subfile.cues else 0

    return SubtitleStats(
        file=subfile.path,
        total_cues=len(subfile.cues),
        total_duration_ms=total_duration_ms,
        total_chars=subfile.total_chars,
        total_words=subfile.total_words,
        total_lines=subfile.total_lines,
        words_per_minute=subfile.total_words / total_minutes if total_minutes > 0 else 0,
        chars_per_minute=subfile.total_chars / total_minutes if total_minutes > 0 else 0,
        avg_duration_per_cue=sum(c.duration_ms for c in subfile.cues) / len(subfile.cues) if subfile.cues else 0,
        avg_words_per_cue=subfile.total_words / len(subfile.cues) if subfile.cues else 0,
        avg_chars_per_cue=subfile.total_chars / len(subfile.cues) if subfile.cues else 0,
        avg_lines_per_cue=subfile.total_lines / len(subfile.cues) if subfile.cues else 0,
        max_duration_cue={
            "index": max_duration_cue.index,
            "duration_ms": max_duration_cue.duration_ms,
            "text": max_duration_cue.text[:50]
        } if max_duration_cue else {},
        min_duration_cue={
            "index": min_duration_cue.index,
            "duration_ms": min_duration_cue.duration_ms,
            "text": min_duration_cue.text[:50]
        } if min_duration_cue else {},
        max_words_cue={
            "index": max_words_cue.index,
            "word_count": max_words_cue.word_count,
            "text": max_words_cue.text[:50]
        } if max_words_cue else {},
        high_risk_sentences=high_risk,
        speaker_stats=speaker_stats
    )


def generate_stats_report(stats_list: List[SubtitleStats]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("字幕统计报告")
    lines.append("=" * 80)
    lines.append("")

    total_files = len(stats_list)
    total_cues = sum(s.total_cues for s in stats_list)
    total_duration = sum(s.total_duration_ms for s in stats_list)
    total_words = sum(s.total_words for s in stats_list)
    total_chars = sum(s.total_chars for s in stats_list)
    total_minutes = total_duration / 60000.0 if total_duration > 0 else 0
    total_high_risk = sum(len(s.high_risk_sentences) for s in stats_list)

    lines.append(f"文件总数: {total_files}")
    lines.append(f"字幕总数: {total_cues}")
    lines.append(f"总时长: {format_ms(total_duration)} ({total_minutes:.2f} 分钟)")
    lines.append(f"总字数: {total_words} 词 / {total_chars} 字符")
    lines.append(f"平均语速: {total_words / total_minutes:.1f} 词/分钟" if total_minutes > 0 else "平均语速: N/A")
    lines.append(f"高风险句子: {total_high_risk}")
    lines.append("")

    for stats in stats_list:
        lines.append("-" * 80)
        lines.append(f"文件: {stats.file}")
        lines.append("")
        lines.append(f"  字幕数: {stats.total_cues}")
        lines.append(f"  时长: {format_ms(stats.total_duration_ms)} ({stats.total_duration_ms / 60000.0:.2f} 分钟)")
        lines.append(f"  字数: {stats.total_words} 词 / {stats.total_chars} 字符")
        lines.append(f"  行数: {stats.total_lines}")
        lines.append(f"  语速: {stats.words_per_minute:.1f} 词/分钟 | {stats.chars_per_minute:.1f} 字符/分钟")
        lines.append("")
        lines.append(f"  平均每条字幕:")
        lines.append(f"    - 时长: {stats.avg_duration_per_cue:.0f}ms")
        lines.append(f"    - 字数: {stats.avg_words_per_cue:.1f} 词")
        lines.append(f"    - 字符数: {stats.avg_chars_per_cue:.1f} 字符")
        lines.append(f"    - 行数: {stats.avg_lines_per_cue:.1f} 行")
        lines.append("")

        if stats.speaker_stats:
            lines.append("  说话人统计:")
            for speaker, sstats in stats.speaker_stats.items():
                lines.append(f"    {speaker}: {sstats['cue_count']}条, "
                             f"{sstats['total_words']}词, "
                             f"{sstats['words_per_minute']:.1f}词/分钟")
            lines.append("")

        if stats.high_risk_sentences:
            lines.append(f"  高风险句子 ({len(stats.high_risk_sentences)}):")
            for risk in stats.high_risk_sentences:
                risk_icon = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(risk.risk_level, "[?]")
                lines.append(f"    {risk_icon} #{risk.cue_index} [{risk.start_time}] - {risk.reason}")
                preview = risk.text.replace('\n', ' | ')[:60]
                lines.append(f"       {preview}...")
            lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)
