"""Regulatory clocks: start, optional pauses, stop, day basis and IST dates.

A ``Clock`` answers three questions for one obligation on one complaint: when is it due
(``due_date``), what state is it in at a moment (``state``), and how many days are left
(``days_remaining``). All arithmetic is on Asia/Kolkata calendar dates.

Rounding is explicit and has exactly three rules:

1. An instant rounds down to its Asia/Kolkata calendar date (``clock_date``). Time of day
   never matters.
2. The start day is not counted: ``n`` calendar days from ``s`` is ``s + n``; ``n`` working days
   from ``s`` is the ``n``-th working day after ``s`` (RBC-CB para 71 excludes the receipt day).
3. A calendar-day due date that falls on a holiday is **not** moved. No researched clause says it
   should be, so the engine does not assume it.

``due_date`` is the last day on which the stop is on time (``rules/scenarios/_schema.md``).

Pauses are supported but no obligation may use one until open question Q3 is resolved by the owner
(CLAUDE.md hard rule 3). A pause from ``p`` to ``r`` pushes the due date out by the days in
``(p, r]`` counted on the clock's basis; an open pause runs to ``as_of``, and the clock cannot
breach while paused.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from abhiyogah.clocks.calendar import BankCalendar
from abhiyogah.clocks.errors import ClockError, ClockSpecError, MissingFactError
from abhiyogah.domain.complaint import EVENT_DATE_FACTS, ComplaintFacts, Fact
from abhiyogah.domain.enums import BasisStatus, DayBasis
from abhiyogah.domain.events import ComplaintEvent, EventType
from abhiyogah.domain.tz import ist_date
from abhiyogah.registry.schema import ClockPause, ClockSpec

__all__ = [
    "Clock",
    "ClockState",
    "Pause",
    "build_clock",
    "clock_date",
    "pauses_from_events",
    "start_fact_name",
    "stop_fact_names",
]


class ClockState(StrEnum):
    """State of a clock at a moment. Values match ``DecisionResult`` members of the same name."""

    RUNNING = "RUNNING"
    STOPPED_ON_TIME = "STOPPED_ON_TIME"
    STOPPED_LATE = "STOPPED_LATE"
    BREACHED = "BREACHED"


def clock_date(moment: date | datetime) -> date:
    """Round a moment down to its Asia/Kolkata date (rounding rule 1); a ``date`` is kept as is."""
    if isinstance(moment, datetime):
        return ist_date(moment)
    return moment


@dataclass(frozen=True, slots=True)
class Pause:
    """A pause from ``paused_on`` to ``resumed_on`` (``None``: still paused)."""

    paused_on: date
    resumed_on: date | None = None

    def __post_init__(self) -> None:
        """A pause cannot resume before it starts."""
        if self.resumed_on is not None and self.resumed_on < self.paused_on:
            raise ClockError(f"pause resumes {self.resumed_on} before it starts {self.paused_on}")


@dataclass(frozen=True, slots=True)
class Clock:
    """One running or stopped regulatory clock. See the module docstring for the rules."""

    start_date: date
    duration_days: int
    basis: DayBasis
    basis_status: BasisStatus
    calendar: BankCalendar
    home_state: str | None = None
    stop_date: date | None = None
    pauses: tuple[Pause, ...] = ()

    def __post_init__(self) -> None:
        """Reject impossible clocks instead of computing nonsense."""
        if self.duration_days < 0:
            raise ClockError(f"negative duration {self.duration_days}")
        if self.basis is DayBasis.WORKING and not self.home_state:
            raise MissingFactError("home_branch_state")
        if self.stop_date is not None and self.stop_date < self.start_date:
            raise ClockError(f"stop {self.stop_date} is before start {self.start_date}")
        for p in self.pauses:
            if p.paused_on < self.start_date:
                raise ClockError(f"pause {p.paused_on} is before start {self.start_date}")

    def _add(self, d: date, n: int) -> date:
        """``d`` plus ``n`` days on this clock's basis (start day excluded)."""
        if self.basis is DayBasis.WORKING:
            assert self.home_state is not None  # noqa: S101 - enforced in __post_init__
            return self.calendar.add_working_days(d, n, self.home_state)
        return self.calendar.add_calendar_days(d, n)

    def _between(self, start_exclusive: date, end_inclusive: date) -> int:
        """Days in ``(start_exclusive, end_inclusive]`` on this clock's basis; 0 if empty."""
        if end_inclusive <= start_exclusive:
            return 0
        if self.basis is DayBasis.WORKING:
            assert self.home_state is not None  # noqa: S101 - enforced in __post_init__
            return self.calendar.working_days_between(
                start_exclusive, end_inclusive, self.home_state
            )
        return (end_inclusive - start_exclusive).days

    def _cutoff(self, as_of: date | None) -> date | None:
        """The day after which nothing counts: the stop, else ``as_of``."""
        if self.stop_date is not None and (as_of is None or self.stop_date <= as_of):
            return self.stop_date
        return as_of

    def _open_pause(self, as_of: date) -> bool:
        """True if a pause that began on time is still open at ``as_of``."""
        due = self.due_date(as_of)
        return any(
            p.paused_on <= min(as_of, due) and (p.resumed_on is None or p.resumed_on > as_of)
            for p in self.pauses
        )

    def due_date(self, as_of: date | datetime | None = None) -> date:
        """Last day on which stopping is on time, as known at ``as_of``.

        Without pauses ``as_of`` is irrelevant. With an open pause it is required, because the due
        date keeps moving while the clock is paused.
        """
        day = None if as_of is None else clock_date(as_of)
        cutoff = self._cutoff(day)
        due = self._add(self.start_date, self.duration_days)
        for p in sorted(self.pauses, key=lambda p: p.paused_on):
            if p.paused_on > due or (cutoff is not None and p.paused_on >= cutoff):
                continue  # paused after the clock had already run out or stopped
            end = p.resumed_on
            if cutoff is not None and (end is None or end > cutoff):
                end = cutoff
            if end is None:
                raise ClockError("an open pause needs as_of to compute the due date")
            due = self._add(due, self._between(p.paused_on, end))
        return due

    def stop_known(self, as_of: date | datetime) -> date | None:
        """The stop date if it happened on or before ``as_of``."""
        day = clock_date(as_of)
        return self.stop_date if self.stop_date is not None and self.stop_date <= day else None

    def state(self, as_of: date | datetime) -> ClockState:
        """``RUNNING``, ``STOPPED_ON_TIME``, ``STOPPED_LATE`` or ``BREACHED`` at ``as_of``."""
        day = clock_date(as_of)
        due = self.due_date(day)
        stop = self.stop_known(day)
        if stop is not None:
            return ClockState.STOPPED_ON_TIME if stop <= due else ClockState.STOPPED_LATE
        if day > due and not self._open_pause(day):
            return ClockState.BREACHED
        return ClockState.RUNNING

    def days_remaining(self, as_of: date | datetime) -> int:
        """Days from ``as_of`` to the due date on the clock's basis; negative once overdue.

        Overdue is always at least -1, even when no working day has passed since the due date (for
        example on the Sunday after a Saturday due date), so the sign always matches the state.
        """
        day = clock_date(as_of)
        due = self.due_date(day)
        if due >= day:
            return self._between(day, due)
        return -max(1, self._between(due, day))

    def days_late(self, as_of: date | datetime) -> int:
        """Calendar days past due at the stop (if late) or at ``as_of`` (if breached); else 0."""
        day = clock_date(as_of)
        due = self.due_date(day)
        stop = self.stop_known(day)
        if stop is not None:
            return max(0, (stop - due).days)
        if self.state(day) is ClockState.BREACHED:
            return (day - due).days
        return 0


def start_fact_name(spec: ClockSpec) -> str:
    """The ``ComplaintFacts`` date field that holds the clock's start."""
    if isinstance(spec.start, EventType):
        name = EVENT_DATE_FACTS.get(spec.start)
        if name is None:
            raise ClockSpecError(f"start event {spec.start} sets no date fact")
        return name
    return spec.start


def stop_fact_names(spec: ClockSpec) -> list[str]:
    """The ``ComplaintFacts`` date fields that hold the clock's stop events, in spec order."""
    names = []
    for ev in spec.stop:
        name = EVENT_DATE_FACTS.get(ev)
        if name is None:
            raise ClockSpecError(f"stop event {ev} sets no date fact")
        names.append(name)
    return names


def _date_fact(facts: ComplaintFacts, name: str) -> Fact[date] | None:
    """Read a date fact by field name."""
    value: Fact[date] | None = getattr(facts, name)
    return value


def build_clock(
    spec: ClockSpec,
    facts: ComplaintFacts,
    duration_days: int,
    calendar: BankCalendar,
    pauses: Sequence[Pause] = (),
    default_state: str | None = None,
) -> Clock:
    """Build a clock from an obligation's clock spec and a complaint's folded facts.

    The start is the start fact; the stop is the earliest of the stop facts that are known. The
    home-branch state is the ``home_branch_state`` fact, else ``default_state``; it is required only
    for working-day clocks.
    """
    start_name = start_fact_name(spec)
    start = _date_fact(facts, start_name)
    if start is None:
        raise MissingFactError(start_name)
    stops = [f.value for n in stop_fact_names(spec) if (f := _date_fact(facts, n)) is not None]
    if pauses and spec.pause is None:
        raise ClockSpecError("pauses given for a clock spec without a pause rule")
    state = facts.home_branch_state.value if facts.home_branch_state is not None else default_state
    return Clock(
        start_date=start.value,
        duration_days=duration_days,
        basis=spec.basis,
        basis_status=spec.basis_status,
        calendar=calendar,
        home_state=state,
        stop_date=min(stops) if stops else None,
        pauses=tuple(pauses),
    )


def pauses_from_events(rule: ClockPause, events: Iterable[ComplaintEvent]) -> list[Pause]:
    """Pair each ``rule.on`` event with the next ``rule.resume`` event, in business-time order."""
    pauses: list[Pause] = []
    open_on: date | None = None
    for ev in sorted(events, key=lambda e: (e.occurred_at, e.recorded_at, e.event_id)):
        if ev.type is rule.on and open_on is None:
            open_on = ist_date(ev.occurred_at)
        elif ev.type is rule.resume and open_on is not None:
            pauses.append(Pause(open_on, ist_date(ev.occurred_at)))
            open_on = None
    if open_on is not None:
        pauses.append(Pause(open_on))
    return pauses
