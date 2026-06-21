from typing import List
from copy import deepcopy
from ..models import SubtitleFile, SubtitleCue


def merge_subtitles(subfiles: List[SubtitleFile], output_path: str,
                    renumber: bool = True, gap_ms: int = 0) -> SubtitleFile:
    all_cues = []
    time_offset = 0

    for subfile in subfiles:
        if not subfile.cues:
            continue

        file_start = subfile.cues[0].start_ms
        file_end = subfile.cues[-1].end_ms
        file_duration = file_end - file_start

        for cue in subfile.cues:
            new_cue = deepcopy(cue)
            new_cue.start_ms = time_offset + (cue.start_ms - file_start)
            new_cue.end_ms = time_offset + (cue.end_ms - file_start)
            all_cues.append(new_cue)

        time_offset += file_duration + gap_ms

    merged = SubtitleFile(
        path=output_path,
        format=subfiles[0].format if subfiles else 'srt',
        cues=all_cues,
        encoding=subfiles[0].encoding if subfiles else 'utf-8'
    )

    if renumber:
        merged.renumber()

    return merged
