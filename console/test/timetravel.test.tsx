import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fromIstInput, shiftDays, toIstInput } from "@/lib/asof";

const nav = vi.hoisted(() => ({ push: vi.fn(), search: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push }),
  usePathname: () => "/complaints/CMP-2026-000101",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

import { TimeTravel } from "@/components/TimeTravel";

describe("IST input helpers", () => {
  it("round-trips a datetime-local value as IST", () => {
    expect(toIstInput("2026-10-19T12:30:00Z")).toBe("2026-10-19T18:00");
    expect(fromIstInput("2026-10-19T18:00")).toBe("2026-10-19T18:00:00+05:30");
    expect(fromIstInput("")).toBeUndefined();
  });

  it("moves by whole days", () => {
    expect(shiftDays("2026-10-19T18:00:00+05:30", 2)).toBe("2026-10-21T18:00:00+05:30");
    expect(shiftDays(undefined, 1, () => Date.parse("2026-10-19T00:00:00Z"))).toBe("2026-10-20T05:30:00+05:30");
  });
});

describe("time-travel control", () => {
  beforeEach(() => {
    nav.push.mockReset();
    nav.search = "";
  });

  it("sets as_of on the current page", () => {
    render(<TimeTravel />);
    expect(screen.getByRole("status").textContent).toBe("Live");
    fireEvent.change(screen.getByLabelText("As of (IST)"), { target: { value: "2026-10-21T18:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(nav.push).toHaveBeenCalledWith("/complaints/CMP-2026-000101?as_of=2026-10-21T18%3A00%3A00%2B05%3A30");
  });

  it("shows the active moment, steps a day and returns to now", () => {
    nav.search = "as_of=2026-10-19T18:00:00%2B05:30&x=1";
    render(<TimeTravel />);
    expect(screen.getByRole("status").textContent).toBe("Time travel: viewing as of 19-10-2026 18:00 IST");
    fireEvent.click(screen.getByRole("button", { name: "+1 day" }));
    expect(nav.push).toHaveBeenLastCalledWith("/complaints/CMP-2026-000101?as_of=2026-10-20T18%3A00%3A00%2B05%3A30&x=1");
    fireEvent.click(screen.getByRole("button", { name: "Now" }));
    expect(nav.push).toHaveBeenLastCalledWith("/complaints/CMP-2026-000101?x=1");
  });

  it("refuses an empty time", () => {
    render(<TimeTravel />);
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.getByRole("status").textContent).toBe("Enter a date and time");
  });
});
