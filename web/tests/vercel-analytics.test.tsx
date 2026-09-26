import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

const captured = vi.hoisted(() => ({ props: null as null | Record<string, unknown> }));
vi.mock("@vercel/analytics/next", () => ({
  Analytics: (props: Record<string, unknown>) => {
    captured.props = props;
    return <div data-testid="vercel-analytics" />;
  },
}));

import VercelAnalytics, { sanitizeVercelEvent } from "@/components/VercelAnalytics";

afterEach(() => {
  vi.unstubAllEnvs();
  captured.props = null;
});

describe("Vercel Analytics", () => {
  it("is rendered by default with the privacy filter attached", () => {
    const { getByTestId } = render(<VercelAnalytics />);
    expect(getByTestId("vercel-analytics")).toBeTruthy();
    expect(typeof captured.props?.beforeSend).toBe("function");
  });

  it("is turned off by NEXT_PUBLIC_ANALYTICS_ENABLED=false, like every other analytics tool", () => {
    vi.stubEnv("NEXT_PUBLIC_ANALYTICS_ENABLED", "false");
    const { queryByTestId } = render(<VercelAnalytics />);
    expect(queryByTestId("vercel-analytics")).toBeNull();
  });

  it("strips private query strings but keeps campaign attribution", () => {
    const out = sanitizeVercelEvent({ type: "pageview", url: "https://hackbench.vercel.app/?utm_source=discord&utm_campaign=launch&token=SECRET&email=a@b.c#frag" });
    expect(out.url).toBe("https://hackbench.vercel.app/?utm_source=discord&utm_campaign=launch");
    expect(JSON.stringify(out)).not.toMatch(/SECRET|a@b\.c|frag/);
  });

  it("never throws on odd input", () => {
    expect(() => sanitizeVercelEvent({ type: "pageview", url: "not a url" })).not.toThrow();
  });
});
