import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "@/app/page";

describe("home page", () => {
  it("renders the console title", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { name: "Abhiyogah console" })).toBeDefined();
  });
});
