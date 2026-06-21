import os
from typing import List, Optional
from copy import deepcopy
from ..models import SubtitleFile, SubtitleCue


def split_by_duration(subfile: SubtitleFile, max_duration_ms: int) -> List[SubtitleFile]:
    parts = []
    current_cues = []
    current_duration = 0
    part_num = 1

    for cue in subfile.cues:
        cue_duration = cue.duration_ms
        if current_duration + cue_duration > max_duration_ms and current_cues:
            part = SubtitleFile(
                path=f"{os.path.splitext(subfile.path)[0]}_part{part_num}{os.path.splitext(subfile.path)[1]}",
                format=subfile.format,
                cues=deepcopy(current_cues),
                encoding=subfile.encoding
            )
            part.renumber()
            parts.append(part)
            current_cues = []
            current_duration = 0
            part_num += 1

        current_cues.append(cue)
        current_duration += cue_duration

    if current_cues:
        part = SubtitleFile(
            path=f"{os.path.splitext(subfile.path)[0]}_part{part_num}{os.path.splitext(subfile.path)[1]}",
            format=subfile.format,
            cues=deepcopy(current_cues),
            encoding=subfile.encoding
        )
        part.renumber()
        parts.append(part)

    return parts


def split_by_cue_count(subfile: SubtitleFile, max_cues: int) -> List[SubtitleFile]:
    parts = []
    for i in range(0, len(subfile.cues), max_cues):
        part_num = i // max_cues + 1
        cues_chunk = subfile.cues[i:i + max_cues]
        part = SubtitleFile(
            path=f"{os.path.splitext(subfile.path)[0]}_part{part_num}{os.path.splitext(subfile.path)[1]}",
            format=subfile.format,
            cues=deepcopy(cues_chunk),
            encoding=subfile.encoding
        )
        part.renumber()
        parts.append(part)
    return parts


def split_by_line_count(subfile: SubtitleFile, max_lines: int) -> List[SubtitleFile]:
    parts = []
    current_cues = []
    current_lines = 0
    part_num = 1

    for cue in subfile.cues:
        cue_lines = len(cue.lines)
        if current_lines + cue_lines > max_lines and current_cues:
            part = SubtitleFile(
                path=f"{os.path.splitext(subfile.path)[0]}_part{part_num}{os.path.splitext(subfile.path)[1]}",
                format=subfile.format,
                cues=deepcopy(current_cues),
                encoding=subfile.encoding
            )
            part.renumber()
            parts.append(part)
            current_cues = []
            current_lines = 0
            part_num += 1

        current_cues.append(cue)
        current_lines += cue_lines

    if current_cues:
        part = SubtitleFile(
            path=f"{os.path.splitext(subfile.path)[0]}_part{part_num}{os.path.splitext(subfile.path)[1]}",
            format=subfile.format,
            cues=deepcopy(current_cues),
            encoding=subfile.encoding
        )
        part.renumber()
        parts.append(part)

    return parts


def split_by_speaker(subfile: SubtitleFile) -> List[SubtitleFile]:
    speaker_cues = {}
    for cue in subfile.cues:
        speaker = cue.speaker or "未知"
        if speaker not in speaker_cues:
            speaker_cues[speaker] = []
        speaker_cues[speaker].append(cue)

    parts = []
    for speaker, cues in speaker_cues.items():
        safe_speaker = "".join(c for c in speaker if c.isalnum() or c in ('_', '-'))
        part = SubtitleFile(
            path=f"{os.path.splitext(subfile.path)[0]}_{safe_speaker}{os.path.splitext(subfile.path)[1]}",
            format=subfile.format,
            cues=deepcopy(cues),
            encoding=subfile.encoding
        )
        part.renumber()
        parts.append(part)

    return parts


def split_subtitle(subfile: SubtitleFile, **options) -> List[SubtitleFile]:
    method = options.get('method', 'cue_count')

    if method == 'duration':
        max_duration_ms = options.get('max_duration_ms', 10 * 60 * 1000)
        return split_by_duration(subfile, max_duration_ms)
    elif method == 'cue_count':
        max_cues = options.get('max_cues', 100)
        return split_by_cue_count(subfile, max_cues)
    elif method == 'line_count':
        max_lines = options.get('max_lines', 200)
        return split_by_line_count(subfile, max_lines)
    elif method == 'speaker':
        return split_by_speaker(subfile)
    else:
        raise ValueError(f"Unsupported split method: {method}")
