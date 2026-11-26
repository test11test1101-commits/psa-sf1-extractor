"""Data models for PSA document extraction and SF1 export."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class OCRBlock:
    """A single recognized text region with bounding box coordinates."""

    text: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def x_center(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @property
    def height(self) -> float:
        return max(1.0, self.y_max - self.y_min)


@dataclass
class PSADocumentRecord:
    """Extracted fields from a single PSA Birth Certificate (2007 or current format)."""

    source_file: str
    name: str = ""
    birthdate: str = ""
    sex: str = ""
    father_name: str = ""
    mother_maiden_name: str = ""
    format_detected: str = "Unknown"
    status: str = "OK"
    warnings: List[str] = field(default_factory=list)

