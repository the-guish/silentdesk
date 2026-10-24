"""Rules about Google Tasks."""

from __future__ import annotations

from ..domain.tasks import GoogleTask


def is_open(task: GoogleTask) -> bool:
    raise NotImplementedError
