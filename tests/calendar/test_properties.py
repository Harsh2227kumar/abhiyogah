"""Hypothesis properties of the bank calendar (para 71 day counting, weekly closures, IST dates)."""

from datetime import date, datetime, time, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from abhiyogah.calendar import (
    STATES,
    HolidaysBankCalendar,
    delay_working_days,
    is_bank_weekend,
    load_bank_calendar,
)
from abhiyogah.domain.tz import IST

CAL = load_bank_calendar()
EXAMPLES = settings(max_examples=500, deadline=None)

dates = st.dates(min_value=date(2002, 1, 1), max_value=date(2033, 12, 31))
states = st.sampled_from(sorted(STATES))
counts = st.integers(min_value=0, max_value=60)


@EXAMPLES
@given(d=dates, n=st.integers(min_value=1, max_value=60), state=states)
def test_adding_working_days_lands_on_a_working_day(d: date, n: int, state: str) -> None:
    assert CAL.is_working_day(CAL.add_working_days(d, n, state), state)


@EXAMPLES
@given(d=dates, n=counts, state=states)
def test_working_days_between_inverts_add_working_days(d: date, n: int, state: str) -> None:
    assert CAL.working_days_between(d, CAL.add_working_days(d, n, state), state) == n


@EXAMPLES
@given(d=dates, n=st.integers(min_value=1, max_value=60), state=states)
def test_add_working_days_is_the_first_date_reaching_n(d: date, n: int, state: str) -> None:
    end = CAL.add_working_days(d, n, state)
    assert CAL.working_days_between(d, end - timedelta(days=1), state) == n - 1


@EXAMPLES
@given(d=dates, state=states)
def test_receipt_day_is_excluded(d: date, state: str) -> None:
    assert CAL.working_days_between(d, d, state) == 0
    nxt = d + timedelta(days=1)
    assert CAL.working_days_between(d, nxt, state) == int(CAL.is_working_day(nxt, state))


@EXAMPLES
@given(d=dates, state=states)
def test_sundays_and_second_fourth_saturdays_are_never_working_days(d: date, state: str) -> None:
    sunday = d + timedelta(days=(6 - d.weekday()) % 7)
    assert not CAL.is_working_day(sunday, state)
    first = date(d.year, d.month, 1)
    first_saturday = first + timedelta(days=(5 - first.weekday()) % 7)
    for nth in (2, 4):
        saturday = first_saturday + timedelta(weeks=nth - 1)
        assert is_bank_weekend(saturday)
        assert not CAL.is_working_day(saturday, state)


@EXAMPLES
@given(d=dates, state=states, closed=st.sets(dates, max_size=20))
def test_overlay_only_removes_working_days(d: date, state: str, closed: set[date]) -> None:
    by_year: dict[tuple[str, int], set[date]] = {}
    for x in closed:
        by_year.setdefault((state, x.year), set()).add(x)
    overlaid = HolidaysBankCalendar(by_year, version="test")
    assert not any(overlaid.is_working_day(x, state) for x in closed)
    if overlaid.is_working_day(d, state):
        assert CAL.is_working_day(d, state)


@EXAMPLES
@given(
    received=dates,
    gap=st.integers(min_value=0, max_value=40),
    state=states,
    t1=st.times(),
    t2=st.times(),
    t3=st.times(),
    t4=st.times(),
)
def test_delay_depends_only_on_ist_dates(
    received: date, gap: int, state: str, t1: time, t2: time, t3: time, t4: time
) -> None:
    reported = received + timedelta(days=gap)

    def at(d: date, t: time) -> datetime:
        return datetime.combine(d, t, tzinfo=IST)

    a = delay_working_days(at(received, t1), at(reported, t2), state, calendar=CAL)
    b = delay_working_days(at(received, t3), at(reported, t4), state, calendar=CAL)
    assert a == b == delay_working_days(received, reported, state, calendar=CAL)
