# 01 — Bank calendar

- **Branch:** `agent/calendar`
- **Phase:** 1 (parallel with 02, 03)
- **Depends on:** 00-foundation merged
- **Owns:** `src/abhiyogah/calendar/`, `tests/calendar/`, `data/calendars/`
- **Goal:** answer "is this a bank working day in state X?" and do working-day arithmetic exactly as
  RBC-CB para 71 needs (the day of receipt is excluded), reproducibly and with a version stamp.

## Checklist

- [ ] `BankCalendar` protocol: `is_working_day(d, state)`, `add_working_days(d, n, state)`,
      `working_days_between(start_exclusive, end_inclusive, state)`, `add_calendar_days(d, n)`, `version`.
- [ ] Implementation on the MIT `holidays` package (India with subdivisions) and a bank overlay: all
      Sundays, 2nd and 4th Saturdays closed, plus state-specific Negotiable Instruments Act holidays.
- [ ] Overlay data in `data/calendars/<year>/<state>.yaml`, each with a source URL. Leave years and states
      you can't source as empty files with a `TODO: source` note; never invent holiday dates.
- [ ] `version` = SHA-256 of the overlay data plus the `holidays` package version, so decision records can
      say exactly which calendar they used.
- [ ] Day-of-receipt exclusion helper used by B5: `delay_working_days(alert_received, reported, state)`.
- [ ] Hypothesis property tests: adding n working days lands on a working day; `working_days_between`
      inverts `add_working_days`; receipt day is excluded; Sundays and 2nd/4th Saturdays are never
      working days; results don't depend on time of day (IST dates only).
- [ ] Example tests with hand-checked dates (for example a report on a Friday before a 2nd Saturday).
- [ ] Docstring for each public function citing para 71 / the day-basis rule it implements.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
All properties pass with at least 500 hypothesis examples; `make check` green; no network access at runtime.

## Requests

## Log
