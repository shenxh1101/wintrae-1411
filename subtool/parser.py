import os
import re
import codecs
from typing import List, Optional

from .models import SubtitleCue, SubtitleFile


TIMESTAMP_PATTERN = re.compile(
    r'(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})'
)


def detect_encoding(file_path: str) -> str:
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000)

    if raw_data.startswith(codecs.BOM_UTF8):
        return 'utf-8-sig'
    elif raw_data.startswith(codecs.BOM_UTF16_LE):
        return 'utf-16-le'
    elif raw_data.startswith(codecs.BOM_UTF16_BE):
        return 'utf-16-be'

    try:
        raw_data.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass

    try:
        raw_data.decode('gbk')
        return 'gbk'
    except UnicodeDecodeError:
        pass

    try:
        raw_data.decode('utf-16')
        return 'utf-16'
    except UnicodeDecodeError:
        pass

    return 'utf-8'


def time_to_ms(hours: int, minutes: int, seconds: int, milliseconds: int) -> int:
    return hours * 3600000 + minutes * 60000 + seconds * 1000 + milliseconds


def ms_to_time(ms: int) -> tuple:
    hours = ms // 3600000
    ms %= 3600000
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return hours, minutes, seconds, milliseconds


def parse_srt(content: str) -> List[SubtitleCue]:
    cues = []
    blocks = re.split(r'\n\s*\n', content.strip())

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue

        index = None
        time_line_idx = 0

        try:
            index = int(lines[0].strip())
            time_line_idx = 1
        except ValueError:
            time_line_idx = 0

        if time_line_idx >= len(lines):
            continue

        time_match = TIMESTAMP_PATTERN.search(lines[time_line_idx])
        if not time_match:
            continue

        start_ms = time_to_ms(
            int(time_match.group(1)),
            int(time_match.group(2)),
            int(time_match.group(3)),
            int(time_match.group(4).ljust(3, '0')[:3])
        )
        end_ms = time_to_ms(
            int(time_match.group(5)),
            int(time_match.group(6)),
            int(time_match.group(7)),
            int(time_match.group(8).ljust(3, '0')[:3])
        )

        text_lines = lines[time_line_idx + 1:]
        text = '\n'.join(text_lines)
        text = text.rstrip('\n')

        if index is None:
            index = len(cues) + 1

        cue = SubtitleCue(index=index, start_ms=start_ms, end_ms=end_ms, text=text)
        cue.extract_speaker()
        cues.append(cue)

    return cues


def parse_vtt(content: str) -> List[SubtitleCue]:
    cues = []
    lines = content.split('\n')
    i = 0
    n = len(lines)

    while i < n and not lines[i].strip().upper().startswith('WEBVTT'):
        i += 1
    if i < n:
        i += 1

    index = 1
    while i < n:
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line.upper().startswith('NOTE'):
            i += 1
            while i < n and lines[i].strip():
                i += 1
            continue

        if line.upper().startswith('STYLE'):
            i += 1
            while i < n and lines[i].strip():
                i += 1
            continue

        if ':' in line and not TIMESTAMP_PATTERN.search(line):
            i += 1
            continue

        cue_id = None
        time_line = None

        if TIMESTAMP_PATTERN.search(line):
            time_line = line
        else:
            cue_id = line
            i += 1
            if i < n:
                time_line = lines[i].strip()

        if time_line and TIMESTAMP_PATTERN.search(time_line):
            time_match = TIMESTAMP_PATTERN.search(time_line)
            start_ms = time_to_ms(
                int(time_match.group(1)),
                int(time_match.group(2)),
                int(time_match.group(3)),
                int(time_match.group(4).ljust(3, '0')[:3])
            )
            end_ms = time_to_ms(
                int(time_match.group(5)),
                int(time_match.group(6)),
                int(time_match.group(7)),
                int(time_match.group(8).ljust(3, '0')[:3])
            )

            i += 1
            text_lines = []
            while i < n and lines[i].strip() and not TIMESTAMP_PATTERN.search(lines[i]):
                next_line = lines[i].strip()
                if next_line.upper().startswith('NOTE'):
                    break
                text_lines.append(lines[i])
                i += 1

            text = '\n'.join(text_lines)
            text = text.rstrip('\n')

            cue = SubtitleCue(index=index, start_ms=start_ms, end_ms=end_ms, text=text)
            cue.extract_speaker()
            cues.append(cue)
            index += 1
        else:
            i += 1

    return cues


def parse_subtitle(file_path: str) -> SubtitleFile:
    ext = os.path.splitext(file_path)[1].lower()
    encoding = detect_encoding(file_path)

    with open(file_path, 'r', encoding=encoding, errors='replace') as f:
        content = f.read()

    if ext == '.srt':
        cues = parse_srt(content)
        fmt = 'srt'
    elif ext == '.vtt':
        cues = parse_vtt(content)
        fmt = 'vtt'
    else:
        try:
            cues = parse_srt(content)
            fmt = 'srt'
        except Exception:
            cues = parse_vtt(content)
            fmt = 'vtt'

    return SubtitleFile(path=file_path, format=fmt, cues=cues, encoding=encoding)


def find_subtitle_files(input_dir: str, recursive: bool = True) -> List[str]:
    subtitle_exts = ['.srt', '.vtt']
    files = []

    if recursive:
        for root, _, filenames in os.walk(input_dir):
            for filename in filenames:
                if os.path.splitext(filename)[1].lower() in subtitle_exts:
                    files.append(os.path.join(root, filename))
    else:
        for filename in os.listdir(input_dir):
            if os.path.splitext(filename)[1].lower() in subtitle_exts:
                files.append(os.path.join(input_dir, filename))

    return sorted(files)
