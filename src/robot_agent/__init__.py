"""Application-owned task state; execution authority stays in Robot Harness."""

from .handoff import HandoffTask

from .navigation import NavigationTask
from .navigation_checkpoint import CheckpointNavigationTask

__all__ = ['HandoffTask', 'NavigationTask', 'CheckpointNavigationTask']
