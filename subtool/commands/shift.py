from typing import Optional
from ..models import SubtitleFile


def shift_all(subfile: SubtitleFile, offset_ms: int) -> SubtitleFile:
    for cue in subfile.cues:
        cue.start_ms += offset_ms
        cue.end_ms += offset_ms
        if cue.start_ms < 0:
            cue.start_ms = 0
        if cue.end_ms < 0:
            cue.end_ms = 0
    return subfile


def shift_range(subfile: SubtitleFile, offset_ms: int,
                start_ms: Optional[int] = None, end_ms: Optional[int] = None,
                cue_start: Optional[int] = None, cue_end: Optional[int] = None) -> SubtitleFile:
    for i, cue in enumerate(subfile.cues):
        in_time_range = True
        in_cue_range = True

        if start_ms is not None and end_ms is not None:
            in_time_range = (cue.start_ms >= start_ms and cue.start_ms < end_ms) or \
                            (cue.end_ms > start_ms and cue.end_ms <= end_ms)
        elif start_ms is not None:
            in_time_range = cue.start_ms >= start_ms
        elif end_ms is not None:
            in_time_range = cue.start_ms < end_ms

        if cue_start is not None and cue_end is not None:
            in_cue_range = cue_start <= cue.index <= cue_end
        elif cue_start is not None:
            in_cue_range = cue.index >= cue_start
        elif cue_end is not None:
            in_cue_range = cue.index <= cue_end

        if in_time_range and in_cue_range:
            cue.start_ms += offset_ms
            cue.end_ms += offset_ms
            if cue.start_ms < 0:
                cue.start_ms = 0
            if cue.end_ms < 0:
                cue.end_ms = 0

    return subfile


def shift_subtitle(subfile: SubtitleFile, offset_ms: int, **options) -> SubtitleFile:
    start_ms = options.get('start_ms')
    end_ms = options.get('end_ms')
    cue_start = options.get('cue_start')
    cue_end = options.get('cue_end')

    if start_ms is None and end_ms is None and cue_start is None and cue_end is None:
        return shift_all(subfile, offset_ms)
    else:
        return shift_range(subfile, offset_ms, start_ms, end_ms, cue_start, cue_end)
