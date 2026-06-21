import os
import shutil
from typing import List

from .models import SubtitleFile, SubtitleCue
from .parser import ms_to_time


def format_time_srt(ms: int) -> str:
    h, m, s, ms = ms_to_time(ms)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_time_vtt(ms: int) -> str:
    h, m, s, ms = ms_to_time(ms)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def write_srt(cues: List[SubtitleCue]) -> str:
    lines = []
    for cue in cues:
        lines.append(str(cue.index))
        lines.append(f"{format_time_srt(cue.start_ms)} --> {format_time_srt(cue.end_ms)}")
        lines.append(cue.text)
        lines.append('')
    return '\n'.join(lines)


def write_vtt(cues: List[SubtitleCue]) -> str:
    lines = ['WEBVTT', '']
    for cue in cues:
        lines.append(f"{format_time_vtt(cue.start_ms)} --> {format_time_vtt(cue.end_ms)}")
        lines.append(cue.text)
        lines.append('')
    return '\n'.join(lines)


def write_subtitle(subtitle_file: SubtitleFile, output_path: str, target_format: str = None) -> str:
    fmt = target_format or subtitle_file.format

    if fmt == 'srt':
        content = write_srt(subtitle_file.cues)
        if not output_path.endswith('.srt'):
            output_path = os.path.splitext(output_path)[0] + '.srt'
    elif fmt == 'vtt':
        content = write_vtt(subtitle_file.cues)
        if not output_path.endswith('.vtt'):
            output_path = os.path.splitext(output_path)[0] + '.vtt'
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w', encoding=subtitle_file.encoding) as f:
        f.write(content)

    return output_path


def backup_file(file_path: str, backup_dir: str = None, backup_method: str = 'copy') -> str:
    if backup_method == 'none':
        return ''

    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(file_path), 'backup')

    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, os.path.basename(file_path))

    base, ext = os.path.splitext(backup_path)
    counter = 1
    while os.path.exists(backup_path):
        backup_path = f"{base}_{counter}{ext}"
        counter += 1

    if backup_method == 'copy':
        shutil.copy2(file_path, backup_path)
    elif backup_method == 'move':
        shutil.move(file_path, backup_path)
    else:
        raise ValueError(f"Unsupported backup method: {backup_method}")

    return backup_path
