from dataclasses import dataclass
from typing import Optional

@dataclass
class TrackMetadata:
    title: str
    artist: str
    duration_ms: int
    cover_url: Optional[str] = None
    album: Optional[str] = None
    platform_id: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.artist} - {self.title}"

    @property
    def duration_seconds(self) -> float:
        return self.duration_ms / 1000
