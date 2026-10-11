"""Private inspection history/health and immutable frame reads; no ROS transport."""
from dataclasses import dataclass, replace
import math
import threading
import time

from ._task_events import EventInbox

SITES = {'A': (.7, -.5), 'B': (-1.5, -.5)}


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True)
class SourceProfile:
    window_seconds: float = 5.
    health_seconds: float = 1.
    frame_seconds: float = 1.
    rate_hz: float = 5.
    maximum_samples: int = 25
    minimum_samples: int = 3

    def __post_init__(self):
        for value, ceiling in ((self.window_seconds, 5.), (self.health_seconds, 1.),
                               (self.frame_seconds, 1.), (self.rate_hz, 5.)):
            if not _finite_number(value) or not 0 < value <= ceiling:
                raise ValueError('unsupported inspection source limit')
        if (type(self.maximum_samples) is not int or type(self.minimum_samples) is not int
                or not 3 <= self.minimum_samples <= self.maximum_samples <= 25):
            raise ValueError('invalid inspection sample limits')


@dataclass(frozen=True)
class Frame:
    generation: int
    sequence: int
    site: str
    target: str
    acquired: float
    received: float
    map_xy: tuple
    pixels: bytes
    frame_id: str = 'inspection_optical'
    width: int = 640
    height: int = 480
    encoding: str = 'rgb8'


@dataclass(frozen=True)
class CheckRecord:
    reference: str
    generation: int
    site: str
    target: str
    acquired_first: float | None
    acquired_last: float | None
    samples: int
    classification: str


class _SourceEvents(EventInbox):
    def __init__(self, refresh):
        super().__init__()
        self.refresh = refresh

    def take(self):
        # Expiry is observed on caller turns even when the publisher goes silent.
        self.refresh()
        return super().take()


class FrameRead:
    def __init__(self, source, frame, window, expires):
        self._source, self._frame = source, frame
        self._window, self._expires = window, expires

    def read(self):
        """Return immutable owned bytes after checking the current read deadline.

        Bytes already returned cannot be revoked. They are never reused or mutated;
        consumers must not represent a retained copy as a fresh observation.
        """
        return self._source.read(self)

    def release(self):
        self._source.release(self)


class InspectionSource:
    """One latest frame + one reader + at most two pixel-free window records.

    Adapter supplies actual same-clock image stamps, local monotonic receive time,
    image-time map pose and registered target identity. Image interpretation owns
    the classification; this source does not reclassify pixels or admit actions.
    A single lock owns source state; source-to-inbox is the only nested lock order.
    No producer is started here. Its caller owns startup, ready health and shutdown.
    """
    def __init__(self, generation, *, profile=SourceProfile(), clock=time.monotonic):
        if type(generation) is not int or not 0 <= generation < 2**63:
            raise ValueError('invalid source generation')
        self.generation, self.profile, self.now = generation, profile, clock
        self._lock = threading.Lock()
        self.events = _SourceEvents(self.refresh)
        self._clock = self._health_at = self._progress_at = None
        self._sequence = -1
        self._last_sample_stamp = None
        self._latest = self._reader = self._window = None
        self._outcomes, self._records = [], []
        self._closed = False

    def _fail(self, reason):
        self.events.invalidate(reason)
        self._latest = None
        with self.events.lock:
            self.events.latest = None

    def _ready(self, now):
        if self._closed:
            self._fail('inspection source closed')
        elif self._health_at is None:
            self._fail('inspection source health unknown')
        elif (not 0 <= now-self._health_at <= self.profile.health_seconds
              or not 0 <= now-self._progress_at <= self.profile.health_seconds):
            self._fail('inspection source health or clock expired')
        with self.events.lock:
            return not self.events.stop_requested and self.events.failure is None

    def refresh(self):
        with self._lock:
            return self._ready(self.now())

    def health(self, generation, clock_value, *, healthy=True):
        with self._lock:
            now = self.now()
            if type(generation) is not int or generation != self.generation:
                self._fail('inspection source generation changed')
                return False
            if healthy is not True or not _finite_number(clock_value) or clock_value < 0:
                self._fail('inspection source health invalid')
                return False
            # Never let a late heartbeat erase a period of missing evidence.
            if self._health_at is not None and not self._ready(now):
                return False
            if self._clock is not None and clock_value < self._clock:
                self._fail('inspection source clock rolled back')
                return False
            if self._clock is None or clock_value > self._clock:
                self._progress_at = now
            self._clock, self._health_at = clock_value, now
            return self._ready(now)

    def open_window(self, site, target):
        if site not in SITES or not isinstance(target, str) or not 0 < len(target) <= 64:
            raise ValueError('invalid registered inspection target')
        with self._lock:
            now = self.now()
            if not self._ready(now):
                raise RuntimeError('inspection source unavailable')
            if self._window is not None or len(self._records) >= 2:
                raise RuntimeError('inspection window already open or budget exhausted')
            reference = f'inspection-{len(self._records)+1}'
            self._window = (reference, site, target, now+self.profile.window_seconds,
                            self._clock, now)
            self._outcomes, self._latest, self._last_sample_stamp = [], None, None
            return reference

    def ingest(self, frame):
        with self._lock:
            now = self.now()
            if not self._ready(now):
                return False
            if not isinstance(frame, Frame):
                self._fail('inspection sample association invalid')
                return False
            if type(frame.generation) is not int or frame.generation != self.generation:
                self._fail('inspection source generation changed')
                return False
            if type(frame.sequence) is not int or not 0 <= frame.sequence < 2**63:
                self._fail('inspection sample identity invalid')
                return False
            if frame.sequence <= self._sequence:
                return False
            self._sequence = frame.sequence
            if self._window is None or now >= self._window[3]:
                return False
            # Validate and publish the same owned metadata, never the producer's
            # mutable pose list. The producer retains pixels until ingest returns.
            try:
                frame = replace(frame, map_xy=tuple(frame.map_xy))
            except TypeError:
                self._fail('inspection sample association invalid')
                return False
            _, site, target, _, opened_clock, opened_local = self._window
            if (frame.site != site or frame.target != target
                    or frame.frame_id != 'inspection_optical' or frame.width != 640
                    or frame.height != 480 or frame.encoding != 'rgb8'
                    or len(frame.map_xy) != 2
                    or not all(_finite_number(v) for v in frame.map_xy)
                    or math.dist(frame.map_xy, SITES[site]) > .3):
                self._fail('inspection sample association invalid')
                return False
            if not isinstance(frame.pixels, (bytes, bytearray)) or len(frame.pixels) != 640*480*3:
                self._fail('inspection pixel layout invalid')
                return False
            if not all(_finite_number(value) for value in (frame.acquired, frame.received)):
                self._fail('inspection timestamp invalid')
                return False
            if not self._fresh(frame, now):
                return False
            if frame.acquired < opened_clock or frame.received < opened_local:
                return False
            if (self._last_sample_stamp is not None
                    and frame.acquired-self._last_sample_stamp < 1/self.profile.rate_hz-1e-9):
                return False
            # Copy mutable producer memory before publication; borrowed bytes stay immutable.
            frame = replace(frame, pixels=bytes(frame.pixels))
            self._latest, self._last_sample_stamp = frame, frame.acquired
            return self.events.observe(frame.generation, frame.sequence, str(frame.sequence))

    def _fresh(self, frame, now):
        return (all(_finite_number(v) for v in (frame.acquired, frame.received))
                and 0 <= self._clock-frame.acquired <= self.profile.frame_seconds
                and 0 <= now-frame.received <= self.profile.frame_seconds)

    def borrow(self, reference):
        with self._lock:
            now = self.now()
            if self._reader is not None:
                raise RuntimeError('previous frame read must be released')
            if (not self._ready(now) or self._latest is None or str(self._latest.sequence) != reference
                    or not self._fresh(self._latest, now)):
                raise RuntimeError('inspection frame unavailable or stale')
            self._reader = FrameRead(self, self._latest, self._window[0],
                                     self._latest.received+self.profile.frame_seconds)
            return self._reader

    def read(self, reader):
        with self._lock:
            now = self.now()
            if (self._reader is not reader or not self._ready(now)
                    or now > reader._expires or not self._fresh(reader._frame, now)):
                raise RuntimeError('inspection frame read expired or released')
            return reader._frame

    def release(self, reader):
        with self._lock:
            if self._reader is reader:
                self._reader = None
                reader._frame = None

    def record(self, reader, classification):
        if classification not in ('normal', 'abnormal', 'unknown'):
            raise ValueError('invalid inspection classification')
        frame = reader.read()
        with self._lock:
            now = self.now()
            if (not self._ready(now) or self._reader is not reader or self._window is None
                    or reader._window != self._window[0] or now >= self._window[3]
                    or not self._fresh(frame, now)):
                raise RuntimeError('inspection result no longer associated')
            if len(self._outcomes) >= self.profile.maximum_samples:
                return False
            if self._outcomes and frame.acquired <= self._outcomes[-1][0]:
                return False
            self._outcomes.append((frame.acquired, classification))
            return True

    def finish_window(self):
        with self._lock:
            if self._window is None or self.now() < self._window[3]:
                raise RuntimeError('inspection window has not ended')
            reference, site, target, _, _, _ = self._window
            classes = {status for _, status in self._outcomes}
            classification = next(iter(classes)) if (len(self._outcomes) >= self.profile.minimum_samples
                and classes in ({'normal'}, {'abnormal'})) else 'unknown'
            if not self._ready(self.now()):
                classification = 'unknown'
            result = CheckRecord(reference, self.generation, site, target,
                self._outcomes[0][0] if self._outcomes else None,
                self._outcomes[-1][0] if self._outcomes else None,
                len(self._outcomes), classification)
            self._records.append(result)
            self._window, self._latest, self._outcomes = None, None, []
            with self.events.lock:
                self.events.latest = None
            return result

    def applicable(self, record):
        """Source/record validity only; task permission and native reuse are separate."""
        with self._lock:
            return (self._ready(self.now()) and any(record is known for known in self._records)
                    and record.classification != 'unknown')

    def close(self):
        with self._lock:
            self._closed = True
            self._fail('inspection source closed')
            self._window, self._latest, self._outcomes = None, None, []
