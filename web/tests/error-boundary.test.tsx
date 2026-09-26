import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import ErrorPage from "@/app/error";
import GlobalError from "@/app/global-error";

describe("crash boundaries", () => {
  it("shows a friendly message, not the error text, and lets the user retry", () => {
    const reset = vi.fn();
    render(<ErrorPage error={new Error("TypeError: cannot read secret idea text") } reset={reset} />);
    expect(screen.getByText(/Something went wrong/i)).toBeTruthy();
    expect(document.body.textContent).not.toContain("secret idea text");
    fireEvent.click(screen.getByRole("button", { name: /Try again/i }));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it("has a last-resort boundary for the root layout", () => {
    const html = document.createElement("div");
    render(<GlobalError error={new Error("x")} reset={() => {}} />, { container: html });
    expect(html.textContent).toContain("Something went wrong");
  });
});
