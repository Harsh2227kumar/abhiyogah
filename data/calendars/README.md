# Bank holiday overlay

`<year>/<state>.yaml` lists the Negotiable Instruments Act bank holidays of one state or union
territory in one year, on top of what `abhiyogah.calendar` already closes: Sundays, 2nd and 4th
Saturdays, and the public holidays the `holidays` package lists for that subdivision. State codes are
the `holidays` package's India subdivision codes (`MH`, `KA`, `DL`, ...).

```yaml
state: MH
year: 2026
source_url: https://...        # primary source the dates were copied from
todo: null                     # or a note while the file is not yet sourced
holidays:
  - date: 2026-01-26
    name: Republic Day
```

Rules (CLAUDE.md hard rule 2):

- Never invent a date. Every date comes from the file's `source_url`.
- A file that could not be sourced keeps `source_url: null`, a `todo` note and `holidays: []`.
  The loader rejects dates without a source. `Overlay.unsourced()` lists these files.
- Every file feeds the calendar `version` hash, so any edit changes the version recorded in decisions.

All 2026 and 2027 files are currently `TODO: source`: the RBI holiday matrix was not reachable from
the build environment.
