# 01 — Bank calendar

- **Issue:** #3 (sub-issue of #1)
- **Branch:** `agent/calendar`
- **Phase:** 1 (parallel with 02, 03)
- **Depends on:** 00-foundation merged
- **Owns:** `src/abhiyogah/calendar/`, `tests/calendar/`, `data/calendars/`
- **Goal:** answer "is this a bank working day in state X?" and do working-day arithmetic exactly as
  RBC-CB para 71 needs (the day of receipt is excluded), reproducibly and with a version stamp.

## Checklist

- [x] `BankCalendar` protocol: `is_working_day(d, state)`, `add_working_days(d, n, state)`,
      `working_days_between(start_exclusive, end_inclusive, state)`, `add_calendar_days(d, n)`, `version`.
- [x] Implementation on the MIT `holidays` package (India with subdivisions) and a bank overlay: all
      Sundays, 2nd and 4th Saturdays closed, plus state-specific Negotiable Instruments Act holidays.
- [x] Overlay data in `data/calendars/<year>/<state>.yaml`, each with a source URL. Leave years and states
      you can't source as empty files with a `TODO: source` note; never invent holiday dates.
- [x] `version` = SHA-256 of the overlay data plus the `holidays` package version, so decision records can
      say exactly which calendar they used.
- [x] Day-of-receipt exclusion helper used by B5: `delay_working_days(alert_received, reported, state)`.
- [x] Hypothesis property tests: adding n working days lands on a working day; `working_days_between`
      inverts `add_working_days`; receipt day is excluded; Sundays and 2nd/4th Saturdays are never
      working days; results don't depend on time of day (IST dates only).
- [x] Example tests with hand-checked dates (for example a report on a Friday before a 2nd Saturday).
- [ ] Docstring for each public function citing para 71 / the day-basis rule it implements.
- [ ] Write `STREAM COMPLETE`.

## Definition of done
All properties pass with at least 500 hypothesis examples; `make check` green; no network access at runtime.

## Requests

- `docs/open-questions.md` (owner/integrator): add Q14 "Do `holidays` package public holidays match NI Act bank holidays; may a sourced overlay remove or replace them; primary citation for 2nd/4th Saturday closures" (issue #13). Until answered, the calendar closes the union of package holidays and overlay dates.

## Log
- 2026-10-19 · item 1 done · `BankCalendar` protocol in `calendar/protocol.py` with runtime-checkable test · next: item 2 (holidays + bank overlay implementation)
- 2026-10-19 · item 2 done · `HolidaysBankCalendar` (Sundays, 2nd/4th Saturdays, `holidays` India subdivisions, per-state overlay); years without package lunar data raise `CalendarRangeError` · next: item 3 (overlay data files)
- 2026-10-19 · item 3 done · overlay loader `calendar/overlay.py` + `data/calendars/{2026,2027}/<state>.yaml` for all 36 subdivisions, all `TODO: source` (RBI holiday matrix unreachable from container) · next: item 4 (version hash)
- 2026-10-19 · item 4 done · `calendar_version()` = `sha256:` over overlay bytes digest + `holidays` version; `load_bank_calendar()` stamps it · next: item 5 (`delay_working_days`)
- 2026-10-19 · item 5 done · `delay_working_days(alert_received, reported, state, *, calendar)` on IST dates, receipt day excluded · next: item 6 (hypothesis properties)
- 2026-10-19 · item 6 done · `tests/calendar/test_properties.py`: 7 properties at 500 examples each over all 36 states, 2002-2033 · next: item 7 (hand-checked example tests)
- 2026-10-19 · item 7 done · `tests/calendar/test_examples.py`: Friday before 2nd Saturday, 1st Saturday open, Republic Day + 4th Saturday, Christmas, state-only holiday · next: item 8 (docstring pass)
