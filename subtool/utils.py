import os
import json
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional

from .models import SubtitleFile
from .writer import write_subtitle, backup_file
from .commands.scan import ScanIssue, format_ms
from .commands.stats import SubtitleStats


def parse_time_string(time_str: str) -> int:
    parts = time_str.replace(',', '.').split(':')
    if len(parts) == 3:
        h, m, s = parts
        h = int(h)
        m = int(m)
        if '.' in s:
            s, ms = s.split('.')
            s = int(s)
            ms = int(ms.ljust(3, '0')[:3])
        else:
            s = int(s)
            ms = 0
        return h * 3600000 + m * 60000 + s * 1000 + ms
    elif len(parts) == 2:
        m, s = parts
        m = int(m)
        if '.' in s:
            s, ms = s.split('.')
            s = int(s)
            ms = int(ms.ljust(3, '0')[:3])
        else:
            s = int(s)
            ms = 0
        return m * 60000 + s * 1000 + ms
    else:
        raise ValueError(f"Invalid time format: {time_str}")


def format_duration(ms: int) -> str:
    if ms < 0:
        return f"-{format_duration(-ms)}"
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms = ms % 1000

    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    elif m > 0:
        return f"{m}m{s:02d}s"
    elif s > 0:
        return f"{s}.{ms:03d}s"
    else:
        return f"{ms}ms"


def save_report(content: str, report_path: str, format: str = 'txt') -> str:
    os.makedirs(os.path.dirname(os.path.abspath(report_path)) or '.', exist_ok=True)

    if not report_path.endswith(f'.{format}'):
        report_path = f"{report_path}.{format}"

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return report_path


def scan_issues_to_json(scan_results: List[Dict[str, Any]]) -> str:
    serializable = []
    for result in scan_results:
        issues = []
        for issue in result['issues']:
            if isinstance(issue, ScanIssue):
                issues.append({
                    'type': issue.type,
                    'severity': issue.severity,
                    'cue_index': issue.cue_index,
                    'message': issue.message,
                    'details': issue.details
                })
            else:
                issues.append(issue)

        serializable.append({
            'file': result['file'],
            'total_cues': result['total_cues'],
            'issues': issues,
            'total_issues': result['total_issues'],
            'severity_counts': result['severity_counts'],
            'type_counts': result['type_counts'],
            'has_errors': result['has_errors']
        })
    return json.dumps(serializable, ensure_ascii=False, indent=2)


def build_unified_summary_entry(file_path: str,
                                  total_cues: int = 0,
                                  total_duration_ms: int = 0,
                                  total_words: int = 0,
                                  total_chars: int = 0,
                                  errors: int = 0,
                                  warnings: int = 0,
                                  high_risk: int = 0,
                                  status: str = 'ok') -> Dict[str, Any]:
    return {
        'file_path': file_path,
        'file_name': os.path.basename(file_path),
        'total_cues': total_cues,
        'total_duration_ms': total_duration_ms,
        'total_duration_str': format_ms(total_duration_ms),
        'total_words': total_words,
        'total_chars': total_chars,
        'errors': errors,
        'warnings': warnings,
        'high_risk': high_risk,
        'status': status
    }


def generate_scan_summary(scan_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_files = len(scan_results)
    total_cues = sum(r['total_cues'] for r in scan_results)
    total_issues = sum(r['total_issues'] for r in scan_results)
    total_errors = sum(r['severity_counts']['error'] for r in scan_results)
    total_warnings = sum(r['severity_counts']['warning'] for r in scan_results)
    total_duration = sum(r.get('total_duration_ms', 0) for r in scan_results)
    total_words = sum(r.get('total_words', 0) for r in scan_results)
    total_chars = sum(r.get('total_chars', 0) for r in scan_results)
    total_high_risk = sum(r.get('high_risk_count', 0) for r in scan_results)
    files_with_errors = sum(1 for r in scan_results if r['has_errors'])

    file_summaries = []
    for r in scan_results:
        entry = build_unified_summary_entry(
            file_path=r['file'],
            total_cues=r['total_cues'],
            total_duration_ms=r.get('total_duration_ms', 0),
            total_words=r.get('total_words', 0),
            total_chars=r.get('total_chars', 0),
            errors=r['severity_counts']['error'],
            warnings=r['severity_counts']['warning'],
            high_risk=r.get('high_risk_count', 0),
            status='error' if r['has_errors'] else 'ok'
        )
        entry['total_issues'] = r['total_issues']
        entry['infos'] = r['severity_counts']['info']
        entry['issue_types'] = r['type_counts']
        file_summaries.append(entry)

    return {
        'summary_type': 'scan',
        'total_files': total_files,
        'total_cues': total_cues,
        'total_duration_ms': total_duration,
        'total_duration_str': format_ms(total_duration),
        'total_words': total_words,
        'total_chars': total_chars,
        'total_high_risk': total_high_risk,
        'total_issues': total_issues,
        'total_errors': total_errors,
        'total_warnings': total_warnings,
        'files_with_errors': files_with_errors,
        'files_without_errors': total_files - files_with_errors,
        'files': file_summaries
    }


def generate_scan_summary_report(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("字幕扫描汇总报告")
    lines.append("=" * 80)
    lines.append("")

    lines.append(f"总文件数: {summary['total_files']}")
    lines.append(f"总字幕数: {summary['total_cues']}")
    lines.append(f"总时长: {summary['total_duration_str']}")
    lines.append(f"总字数: {summary['total_words']} 词 / {summary['total_chars']} 字符")
    lines.append(f"高风险句子总数: {summary['total_high_risk']}")
    lines.append(f"总问题数: {summary['total_issues']}")
    lines.append(f"  - 错误: {summary['total_errors']}")
    lines.append(f"  - 警告: {summary['total_warnings']}")
    lines.append(f"有错误文件: {summary['files_with_errors']}")
    lines.append(f"无错误文件: {summary['files_without_errors']}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("文件详情:")
    lines.append("")

    header = (f"{'文件名':<28} {'字幕数':>6} {'时长':>11} {'字数':>6} "
              f"{'错误':>5} {'警告':>5} {'高风险':>6} {'问题':>6} {'状态':>6}")
    lines.append(header)
    lines.append("-" * 80)

    for f in summary['files']:
        status = "有错误" if f['status'] == 'error' else "正常"
        line = (f"{f['file_name']:<28} {f['total_cues']:>6} {f['total_duration_str']:>11} "
                f"{f['total_words']:>6} {f['errors']:>5} {f['warnings']:>5} "
                f"{f['high_risk']:>6} {f['total_issues']:>6} {status:>6}")
        lines.append(line)

    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def generate_stats_summary(stats_list: List[SubtitleStats]) -> Dict[str, Any]:
    total_files = len(stats_list)
    total_cues = sum(s.total_cues for s in stats_list)
    total_duration = sum(s.total_duration_ms for s in stats_list)
    total_words = sum(s.total_words for s in stats_list)
    total_chars = sum(s.total_chars for s in stats_list)
    total_high_risk = sum(len(s.high_risk_sentences) for s in stats_list)

    total_minutes = total_duration / 60000.0 if total_duration > 0 else 0
    avg_wpm = total_words / total_minutes if total_minutes > 0 else 0

    file_summaries = []
    for s in stats_list:
        entry = build_unified_summary_entry(
            file_path=s.file,
            total_cues=s.total_cues,
            total_duration_ms=s.total_duration_ms,
            total_words=s.total_words,
            total_chars=s.total_chars,
            high_risk=len(s.high_risk_sentences),
            status='ok'
        )
        entry['words_per_minute'] = s.words_per_minute
        entry['speakers'] = list(s.speaker_stats.keys())
        file_summaries.append(entry)

    return {
        'summary_type': 'stats',
        'total_files': total_files,
        'total_cues': total_cues,
        'total_duration_ms': total_duration,
        'total_duration_str': format_ms(total_duration),
        'total_words': total_words,
        'total_chars': total_chars,
        'total_high_risk': total_high_risk,
        'avg_words_per_minute': avg_wpm,
        'files': file_summaries
    }


def generate_stats_summary_report(summary: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("字幕统计汇总报告")
    lines.append("=" * 80)
    lines.append("")

    lines.append(f"总文件数: {summary['total_files']}")
    lines.append(f"总字幕数: {summary['total_cues']}")
    lines.append(f"总时长: {summary['total_duration_str']}")
    lines.append(f"总字数: {summary['total_words']} 词 / {summary['total_chars']} 字符")
    lines.append(f"平均语速: {summary['avg_words_per_minute']:.1f} 词/分钟")
    lines.append(f"高风险句子总数: {summary['total_high_risk']}")
    lines.append("")

    lines.append("-" * 80)
    lines.append("文件详情:")
    lines.append("")

    header = (f"{'文件名':<28} {'字幕数':>6} {'时长':>11} {'字数':>6} "
              f"{'语速':>8} {'高风险':>6} {'错误':>5} {'警告':>5}")
    lines.append(header)
    lines.append("-" * 80)

    for f in summary['files']:
        wpm_str = f"{f.get('words_per_minute', 0):.1f}"
        line = (f"{f['file_name']:<28} {f['total_cues']:>6} {f['total_duration_str']:>11} "
                f"{f['total_words']:>6} {wpm_str:>8} {f['high_risk']:>6} "
                f"{f['errors']:>5} {f['warnings']:>5}")
        lines.append(line)

    lines.append("")
    lines.append("=" * 80)
    return "\n".join(lines)


def stats_to_json(stats_list: List[SubtitleStats]) -> str:
    serializable = []
    for stats in stats_list:
        serializable.append({
            'file': stats.file,
            'total_cues': stats.total_cues,
            'total_duration_ms': stats.total_duration_ms,
            'total_chars': stats.total_chars,
            'total_words': stats.total_words,
            'total_lines': stats.total_lines,
            'words_per_minute': stats.words_per_minute,
            'chars_per_minute': stats.chars_per_minute,
            'avg_duration_per_cue': stats.avg_duration_per_cue,
            'avg_words_per_cue': stats.avg_words_per_cue,
            'avg_chars_per_cue': stats.avg_chars_per_cue,
            'avg_lines_per_cue': stats.avg_lines_per_cue,
            'max_duration_cue': stats.max_duration_cue,
            'min_duration_cue': stats.min_duration_cue,
            'max_words_cue': stats.max_words_cue,
            'high_risk_sentences': [
                {
                    'cue_index': r.cue_index,
                    'start_time': r.start_time,
                    'text': r.text,
                    'words_per_minute': r.words_per_minute,
                    'risk_level': r.risk_level,
                    'reason': r.reason
                } for r in stats.high_risk_sentences
            ],
            'speaker_stats': stats.speaker_stats
        })
    return json.dumps(serializable, ensure_ascii=False, indent=2)


def build_output_path(source_path: str, output_dir: Optional[str] = None,
                      suffix: str = '', prefix: str = '',
                      use_date_subdir: bool = False,
                      target_format: str = None,
                      allow_overwrite: bool = False) -> str:
    dirname = os.path.dirname(source_path)
    basename = os.path.basename(source_path)
    name, ext = os.path.splitext(basename)

    if target_format:
        ext = f'.{target_format}'

    new_name = f"{prefix}{name}{suffix}{ext}"

    base_dir = output_dir if output_dir else dirname

    if use_date_subdir:
        date_str = datetime.now().strftime('%Y%m%d')
        base_dir = os.path.join(base_dir, date_str)

    output_path = os.path.join(base_dir, new_name)

    if not allow_overwrite and os.path.exists(output_path):
        base, ext = os.path.splitext(new_name)
        counter = 1
        while os.path.exists(os.path.join(base_dir, f"{base}_{counter}{ext}")):
            counter += 1
        output_path = os.path.join(base_dir, f"{base}_{counter}{ext}")

    return output_path


def process_output(subfile: SubtitleFile, output_dir: str = None,
                   target_format: str = None, inplace: bool = False,
                   backup_method: str = 'copy', backup_dir: str = None,
                   suffix: str = '', prefix: str = '',
                   use_date_subdir: bool = False,
                   allow_overwrite: bool = False) -> str:
    if inplace:
        backup_file(subfile.path, backup_dir, backup_method)
        output_path = subfile.path
    else:
        output_path = build_output_path(
            subfile.path,
            output_dir=output_dir,
            suffix=suffix,
            prefix=prefix,
            use_date_subdir=use_date_subdir,
            target_format=target_format,
            allow_overwrite=allow_overwrite
        )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    return write_subtitle(subfile, output_path, target_format)


def generate_filename(prefix: str, suffix: str = '', ext: str = '.txt') -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if suffix:
        return f"{prefix}_{timestamp}_{suffix}{ext}"
    return f"{prefix}_{timestamp}{ext}"
