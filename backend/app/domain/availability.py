"""Pure availability algorithm (no I/O): working_hours - time_off - appointments.

All inputs/outputs are timezone-aware UTC datetimes; working hours are local wall-clock
times in the clinic timezone. Intervals are half-open [start, end).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


def local_to_utc(day: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, t, tzinfo=tz).astimezone(UTC)


def compute_slots(
    *,
    day: date,
    tz: ZoneInfo,
    working: Sequence[tuple[time, time]],
    time_off: Sequence[Interval],
    busy: Sequence[Interval],
    duration: timedelta,
    now: datetime,
    min_notice: timedelta,
) -> list[datetime]:
    """Return UTC start times of bookable slots on local date `day`.

    Slots sit on a grid of `duration` starting at each working interval's start, must fit
    entirely inside one working interval (so a slot never crosses a lunch break), must not
    overlap time off or an active appointment, and must start after now + min_notice.
    """
    if duration <= timedelta(0):
        raise ValueError("duration must be positive")
    earliest = now + min_notice
    blockers = [*time_off, *busy]
    slots: list[datetime] = []
    for w_start, w_end in sorted(working):
        cursor = local_to_utc(day, w_start, tz)
        end = local_to_utc(day, w_end, tz)
        while cursor + duration <= end:
            candidate = Interval(cursor, cursor + duration)
            if cursor >= earliest and not any(candidate.overlaps(b) for b in blockers):
                slots.append(cursor)
            cursor += duration
    return slots
