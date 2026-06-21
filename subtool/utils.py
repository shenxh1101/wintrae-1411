import os
import json
import csv
from datetime import datetime
from typing import List, Dict, Any

from .models import SubtitleFile
from .writer import write_subtitle, backup_file
from .commands.scan import ScanIssue
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


def process_output(subfile: SubtitleFile, output_dir: str = None,
                   target_format: str = None, inplace: bool = False,
                   backup_method: str = 'copy', backup_dir: str = None) -> str:
    if inplace:
        backup_path = backup_file(subfile.path, backup_dir, backup_method)
        output_path = subfile.path
    elif output_dir:
        filename = os.path.basename(subfile.path)
        output_path = os.path.join(output_dir, filename)
    else:
        base, ext = os.path.splitext(subfile.path)
        output_path = f"{base}_processed{ext}"

    return write_subtitle(subfile, output_path, target_format)


def generate_filename(prefix: str, suffix: str = '', ext: str = '.txt') -> str:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if suffix:
        return f"{prefix}_{timestamp}_{suffix}{ext}"
    return f"{prefix}_{timestamp}{ext}"
