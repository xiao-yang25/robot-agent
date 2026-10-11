"""Private one-source metadata inbox, not a camera or shared-memory transport."""
from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class ObservationUpdate:
    generation: int
    sequence: int
    reference: str


class EventInbox:
    """Latest observation plus independent, irreversible control/fault latches.

    The producer owns the referenced data and its reading contract. Only bounded
    immutable metadata crosses this inbox; no borrowed frame bytes are stored.
    A new generation invalidates this task instead of silently restarting it.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.stop_requested = False
        self.failure = None
        self.latest = None
        self.identity = None

    def stop(self):
        with self.lock:
            self.stop_requested = True

    def invalidate(self, reason):
        if not isinstance(reason, str) or not 0 < len(reason) <= 256:
            raise ValueError('event invalidation needs a bounded reason')
        with self.lock:
            if self.failure is None:
                self.failure = reason

    def observe(self, generation, sequence, reference):
        if (any(type(value) is not int or not 0 <= value < 2**63
                for value in (generation, sequence))
                or not isinstance(reference, str) or not 0 < len(reference) <= 128):
            raise ValueError('invalid observation event metadata')
        with self.lock:
            if self.identity is not None:
                old_generation, old_sequence = self.identity
                if generation < old_generation or (generation == old_generation and sequence <= old_sequence):
                    return False
                if generation != old_generation:
                    if self.failure is None:
                        self.failure = 'event source generation changed'
                    return False
            if self.failure is not None or self.stop_requested:
                return False
            self.identity = generation, sequence
            self.latest = ObservationUpdate(generation, sequence, reference)
            return True

    def take(self):
        with self.lock:
            latest, self.latest = self.latest, None
            return self.stop_requested, self.failure, latest
