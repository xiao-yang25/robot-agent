"""Application-owned task state; execution authority stays in Robot Harness."""

from .handoff import HandoffTask

from .navigation import NavigationTask

__all__ = ['HandoffTask', 'NavigationTask']
