from dataclasses import dataclass, field
from typing import List, Optional
import re


@dataclass
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str
    speaker: Optional[str] = None

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    @property
    def lines(self) -> List[str]:
        return [line for line in self.text.split('\n') if line.strip()]

    @property
    def char_count(self) -> int:
        return len(re.sub(r'\s+', '', self.text))

    @property
    def word_count(self) -> int:
        text = self.text.strip()
        if not text:
            return 0
        if re.search(r'[\u4e00-\u9fff]', text):
            return len(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9]+', text))
        return len(text.split())

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def extract_speaker(self) -> Optional[str]:
        match = re.match(r'^([A-Za-z\u4e00-\u9fff]+)\s*[:：]\s*', self.text)
        if match:
            self.speaker = match.group(1)
        return self.speaker


@dataclass
class SubtitleFile:
    path: str
    format: str
    cues: List[SubtitleCue] = field(default_factory=list)
    encoding: str = "utf-8"

    @property
    def total_duration_ms(self) -> int:
        if not self.cues:
            return 0
        return self.cues[-1].end_ms - self.cues[0].start_ms

    @property
    def total_chars(self) -> int:
        return sum(cue.char_count for cue in self.cues)

    @property
    def total_words(self) -> int:
        return sum(cue.word_count for cue in self.cues)

    @property
    def total_lines(self) -> int:
        return sum(len(cue.lines) for cue in self.cues)

    def renumber(self) -> None:
        for i, cue in enumerate(self.cues, 1):
            cue.index = i
