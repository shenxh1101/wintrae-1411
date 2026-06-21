from dataclasses import dataclass, field
from typing import List, Dict, Any
import re
from ..models import SubtitleFile, SubtitleCue
from ..parser import ms_to_time


@dataclass
class ScanIssue:
    type: str
    severity: str
    cue_index: int
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


def format_ms(ms: int) -> str:
    h, m, s, ms = ms_to_time(ms)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _count_words(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    if re.search(r'[\u4e00-\u9fff]', text):
        return len(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', text))
    return len(text.split())


def _count_chars(text: str) -> int:
    return len(re.sub(r'\s+', '', text))


def _estimate_high_risk(subfile: SubtitleFile, wpm_threshold: float = 200,
                         min_duration_ms: int = 300) -> int:
    count = 0
    for cue in subfile.cues:
        if cue.duration_ms <= 0 or cue.word_count == 0:
            wpm = 0.0
        else:
            minutes = cue.duration_ms / 60000.0
            wpm = cue.word_count / minutes
        is_risk = (wpm > wpm_threshold
                   or cue.duration_ms < min_duration_ms
                   or len(cue.lines) > 3)
        if is_risk and not cue.is_empty:
            count += 1
    return count


def check_overlaps(subfile: SubtitleFile) -> List[ScanIssue]:
    issues = []
    for i in range(len(subfile.cues) - 1):
        current = subfile.cues[i]
        next_cue = subfile.cues[i + 1]
        if current.end_ms > next_cue.start_ms:
            overlap_ms = current.end_ms - next_cue.start_ms
            issues.append(ScanIssue(
                type="overlap",
                severity="error",
                cue_index=current.index,
                message=f"时间轴重叠：第{current.index}条与第{next_cue.index}条重叠 {overlap_ms}ms",
                details={
                    "cue1_index": current.index,
                    "cue1_end": format_ms(current.end_ms),
                    "cue2_index": next_cue.index,
                    "cue2_start": format_ms(next_cue.start_ms),
                    "overlap_ms": overlap_ms
                }
            ))
    return issues


def check_empty_cues(subfile: SubtitleFile) -> List[ScanIssue]:
    issues = []
    for cue in subfile.cues:
        if cue.is_empty:
            issues.append(ScanIssue(
                type="empty",
                severity="warning",
                cue_index=cue.index,
                message=f"空字幕：第{cue.index}条字幕内容为空",
                details={
                    "start_time": format_ms(cue.start_ms),
                    "end_time": format_ms(cue.end_ms),
                    "duration_ms": cue.duration_ms
                }
            ))
    return issues


def check_long_lines(subfile: SubtitleFile, max_chars_per_line: int = 40, max_lines: int = 2) -> List[ScanIssue]:
    issues = []
    for cue in subfile.cues:
        lines = cue.lines
        if len(lines) > max_lines:
            issues.append(ScanIssue(
                type="long_lines",
                severity="warning",
                cue_index=cue.index,
                message=f"行数过多：第{cue.index}条有{len(lines)}行（超过{max_lines}行限制）",
                details={
                    "line_count": len(lines),
                    "max_lines": max_lines,
                    "lines": lines
                }
            ))
        for line_num, line in enumerate(lines, 1):
            if len(line) > max_chars_per_line:
                issues.append(ScanIssue(
                    type="long_line",
                    severity="warning",
                    cue_index=cue.index,
                    message=f"行过长：第{cue.index}条第{line_num}行有{len(line)}字符（超过{max_chars_per_line}限制）",
                    details={
                        "line_num": line_num,
                        "char_count": len(line),
                        "max_chars": max_chars_per_line,
                        "line_content": line
                    }
                ))
    return issues


def check_index_gaps(subfile: SubtitleFile) -> List[ScanIssue]:
    issues = []
    if not subfile.cues:
        return issues

    expected_index = 1
    for cue in subfile.cues:
        if cue.index != expected_index:
            if cue.index > expected_index:
                issues.append(ScanIssue(
                    type="index_gap",
                    severity="error",
                    cue_index=expected_index,
                    message=f"编号断裂：从{expected_index}跳到{cue.index}，缺少{cue.index - expected_index}个编号",
                    details={
                        "expected": expected_index,
                        "actual": cue.index,
                        "missing_count": cue.index - expected_index
                    }
                ))
            elif cue.index < expected_index:
                issues.append(ScanIssue(
                    type="index_duplicate",
                    severity="error",
                    cue_index=cue.index,
                    message=f"编号重复：第{cue.index}条重复出现",
                    details={
                        "index": cue.index
                    }
                ))
            expected_index = cue.index
        expected_index += 1
    return issues


def check_negative_duration(subfile: SubtitleFile) -> List[ScanIssue]:
    issues = []
    for cue in subfile.cues:
        if cue.duration_ms <= 0:
            issues.append(ScanIssue(
                type="negative_duration",
                severity="error",
                cue_index=cue.index,
                message=f"无效时长：第{cue.index}条时长为{cue.duration_ms}ms",
                details={
                    "start_time": format_ms(cue.start_ms),
                    "end_time": format_ms(cue.end_ms),
                    "duration_ms": cue.duration_ms
                }
            ))
    return issues


def check_gaps(subfile: SubtitleFile, min_gap_ms: int = 0) -> List[ScanIssue]:
    issues = []
    for i in range(len(subfile.cues) - 1):
        current = subfile.cues[i]
        next_cue = subfile.cues[i + 1]
        gap_ms = next_cue.start_ms - current.end_ms
        if gap_ms < min_gap_ms and gap_ms > 0:
            issues.append(ScanIssue(
                type="small_gap",
                severity="info",
                cue_index=current.index,
                message=f"间隔过小：第{current.index}条与第{next_cue.index}条间隔仅{gap_ms}ms",
                details={
                    "gap_ms": gap_ms,
                    "min_gap_ms": min_gap_ms
                }
            ))
    return issues


def scan_subtitle(subfile: SubtitleFile, **options) -> Dict[str, Any]:
    max_chars = options.get('max_chars_per_line', 40)
    max_lines = options.get('max_lines', 2)
    min_gap_ms = options.get('min_gap_ms', 0)
    wpm_threshold = options.get('wpm_threshold', 200)
    min_duration_ms = options.get('min_duration_ms', 300)

    all_issues = []
    all_issues.extend(check_overlaps(subfile))
    all_issues.extend(check_empty_cues(subfile))
    all_issues.extend(check_long_lines(subfile, max_chars, max_lines))
    all_issues.extend(check_index_gaps(subfile))
    all_issues.extend(check_negative_duration(subfile))
    all_issues.extend(check_gaps(subfile, min_gap_ms))

    severity_counts = {"error": 0, "warning": 0, "info": 0}
    type_counts = {}

    for issue in all_issues:
        severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        type_counts[issue.type] = type_counts.get(issue.type, 0) + 1

    total_duration_ms = subfile.total_duration_ms
    total_words = subfile.total_words
    total_chars = subfile.total_chars
    high_risk_count = _estimate_high_risk(subfile, wpm_threshold, min_duration_ms)

    return {
        "file": subfile.path,
        "total_cues": len(subfile.cues),
        "issues": all_issues,
        "total_issues": len(all_issues),
        "severity_counts": severity_counts,
        "type_counts": type_counts,
        "has_errors": severity_counts["error"] > 0,
        "total_duration_ms": total_duration_ms,
        "total_duration_str": format_ms(total_duration_ms),
        "total_words": total_words,
        "total_chars": total_chars,
        "high_risk_count": high_risk_count
    }


def generate_scan_report(results: List[Dict[str, Any]]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("字幕扫描报告")
    lines.append("=" * 80)
    lines.append("")

    total_files = len(results)
    total_cues = sum(r["total_cues"] for r in results)
    total_issues = sum(r["total_issues"] for r in results)
    files_with_errors = sum(1 for r in results if r["has_errors"])

    lines.append(f"扫描文件数: {total_files}")
    lines.append(f"总字幕条数: {total_cues}")
    lines.append(f"总问题数: {total_issues}")
    lines.append(f"有错误文件数: {files_with_errors}")
    lines.append("")

    for result in results:
        lines.append("-" * 80)
        lines.append(f"文件: {result['file']}")
        lines.append(f"字幕数: {result['total_cues']}, 问题数: {result['total_issues']}")
        lines.append(f"错误: {result['severity_counts']['error']}, "
                     f"警告: {result['severity_counts']['warning']}, "
                     f"提示: {result['severity_counts']['info']}")
        lines.append("")

        if result["issues"]:
            for issue in result["issues"]:
                severity_icon = {"error": "X", "warning": "!", "info": "i"}.get(issue.severity, "?")
                lines.append(f"  [{severity_icon}] [{issue.severity.upper()}] {issue.message}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)
