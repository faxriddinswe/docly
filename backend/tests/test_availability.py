from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.availability import Interval, compute_slots

TASH = ZoneInfo("Asia/Tashkent")  # UTC+5, no DST
DAY = date(2030, 3, 4)  # Monday
WORK = [(time(9), time(13)), (time(14), time(18))]  # lunch 13-14
LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)
M30 = timedelta(minutes=30)


def slots(**kw):  # type: ignore[no-untyped-def]
    base = dict(
        day=DAY,
        tz=TASH,
        working=WORK,
        time_off=[],
        busy=[],
        duration=M30,
        now=LONG_AGO,
        min_notice=timedelta(0),
    )
    return compute_slots(**{**base, **kw})


def local(h: int, m: int = 0, tz: ZoneInfo = TASH) -> datetime:
    return datetime(2030, 3, 4, h, m, tzinfo=tz).astimezone(UTC)


def test_lunch_break_has_no_slots() -> None:
    s = slots()
    assert local(12, 30) in s and local(14) in s
    assert not any(local(13) <= x < local(14) for x in s)
    assert len(s) == 8 + 8


def test_slot_crossing_break_is_excluded() -> None:
    s = slots(duration=timedelta(minutes=45))
    assert local(12) in s  # 12:00-12:45 fits before lunch
    assert local(14) in s  # grid restarts at the afternoon interval start
    assert all(x + timedelta(minutes=45) <= local(13) or x >= local(14) for x in s)
    assert local(12, 45) not in s  # 12:45-13:30 would cross lunch


def test_results_are_utc_and_use_clinic_timezone() -> None:
    first = slots()[0]
    assert first.tzinfo == UTC and first == datetime(2030, 3, 4, 4, 0, tzinfo=UTC)  # 09:00+05


def test_other_timezone_with_dst() -> None:
    ny = ZoneInfo("America/New_York")
    # 2030-03-10 is DST start day in the US; 09:00 local is EDT (UTC-4)
    s = compute_slots(
        day=date(2030, 3, 10),
        tz=ny,
        working=[(time(9), time(10))],
        time_off=[],
        busy=[],
        duration=M30,
        now=LONG_AGO,
        min_notice=timedelta(0),
    )
    assert s == [
        datetime(2030, 3, 10, 13, 0, tzinfo=UTC),
        datetime(2030, 3, 10, 13, 30, tzinfo=UTC),
    ]


def test_busy_and_time_off_block_overlapping_slots() -> None:
    busy = [Interval(local(9), local(9, 30))]
    off = [Interval(local(10, 15), local(11))]
    s = slots(busy=busy, time_off=off)
    assert local(9) not in s and local(9, 30) in s
    assert local(10) not in s  # 10:00-10:30 overlaps the 10:15 time off
    assert local(10, 30) not in s and local(11) in s


def test_adjacent_intervals_do_not_overlap() -> None:
    s = slots(busy=[Interval(local(9, 30), local(10))])
    assert local(9) in s and local(10) in s


def test_past_slots_hidden_and_minimum_notice() -> None:
    now = local(10, 10)
    s = slots(now=now)
    assert local(10) not in s and local(10, 30) in s
    s = slots(now=now, min_notice=timedelta(hours=1))
    assert local(11, 0) not in s and local(11, 30) in s  # 11:10 earliest -> first slot 11:30


def test_no_working_hours_means_no_slots() -> None:
    assert slots(working=[]) == []


def test_invalid_duration() -> None:
    with pytest.raises(ValueError):
        slots(duration=timedelta(0))
