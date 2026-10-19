import { describe, expect, it } from "vitest";
import { parseAsOf, withAsOf } from "@/lib/asof";
import { daysBetween, formatDate, formatDateTime, formatInr, groupIndian, humanize, istDate, localizeDates } from "@/lib/format";

describe("dates", () => {
  it("uses the IST calendar date, not the host zone", () => {
    expect(istDate("2026-10-19T20:00:00Z")).toBe("2026-10-20");
    expect(istDate("2026-10-19T18:00:00+05:30")).toBe("2026-10-19");
  });

  it("formats DD-MM-YYYY and IST times", () => {
    expect(formatDate("2026-08-03")).toBe("03-08-2026");
    expect(formatDateTime("2026-10-19T12:30:00Z")).toBe("19-10-2026 18:00 IST");
  });

  it("counts calendar days across months", () => {
    expect(daysBetween("2026-09-29", "2026-10-19")).toBe(20);
    expect(daysBetween("2026-10-21", "2026-10-19")).toBe(-2);
  });

  it("humanizes enum codes", () => {
    expect(humanize("WHOLLY_REJECTED")).toBe("Wholly rejected");
    expect(humanize("UPI_P2P")).toBe("UPI P2P");
  });
});

describe("as_of parameter", () => {
  it("accepts only offset instants", () => {
    expect(parseAsOf("2026-10-19T18:00:00+05:30")).toBe("2026-10-19T18:00:00+05:30");
    expect(parseAsOf("2026-10-19")).toBeUndefined();
    expect(parseAsOf(["2026-10-19T12:00Z"])).toBe("2026-10-19T12:00Z");
    expect(parseAsOf(undefined)).toBeUndefined();
  });

  it("keeps as_of on links", () => {
    expect(withAsOf("/x", undefined)).toBe("/x");
    expect(withAsOf("/x?a=1", "2026-10-19T18:00:00+05:30")).toBe("/x?a=1&as_of=2026-10-19T18%3A00%3A00%2B05%3A30");
  });
});

describe("money", () => {
  it("groups rupees in lakh and crore like the engine's format_inr", () => {
    expect(formatInr(17_300_000_00)).toBe("₹1,73,00,000.00");
    expect(formatInr(95_00_000_00)).toBe("₹95,00,000.00");
    expect(formatInr(10000)).toBe("₹100.00");
    expect(formatInr(99)).toBe("₹0.99");
    expect(formatInr(-123456789)).toBe("-₹12,34,567.89");
    expect(groupIndian("1234567")).toBe("12,34,567");
    expect(groupIndian("999")).toBe("999");
  });

  it("refuses non-integer paise", () => {
    expect(() => formatInr(1.5)).toThrow(RangeError);
  });

  it("localizes dates inside engine prose", () => {
    expect(localizeDates("as_of = 2026-10-21; due 2026-10-19")).toBe("as_of = 21-10-2026; due 19-10-2026");
  });
});

describe("ISO dates inside identifiers", () => {
  it("leaves obligation IDs alone", () => {
    expect(localizeDates("IO-CB-2026-14-11-12 and RBIOS-2026-10-1-f on 2026-10-01")).toBe(
      "IO-CB-2026-14-11-12 and RBIOS-2026-10-1-f on 01-10-2026",
    );
  });
});
