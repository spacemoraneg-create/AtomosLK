"""
Atomos Extractor Module (Fold 1)

Extracts tournament data from Tabbycat instances:
- Tournament metadata and rounds
- Team Tab standings and team popovers
- Speaker Tab and Replies Tab
- Participants and institutions
- Round results and atomic debate scoresheets (speeches, components, totals)
- Raw provenance preservation
"""

from atomos.extractor.tabbycat import TabbycatExtractor

__all__ = ["TabbycatExtractor"]
