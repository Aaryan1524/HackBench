import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const posthog = vi.hoisted(() => ({ init: vi.fn(), capture: vi.fn() }));
vi.mock("posthog-js", () => ({ default: posthog }));

import Home from "@/app/page";
import { _resetAnalyticsForTests, initAnalytics } from "@/lib/analytics";

const SECRET_IDEA = "ZEBRA-PRIVATE-IDEA a voice agent for the clinic chain of Mr Smith";
const SECRET_DESC = "PRIVATE-DESCRIPTION quokka analytics";
const SECRET_REPO = "https://github.com/private-owner/private-repo-name?token=abc123";

const ideaResult = {
  analysis_id: "an_1",
  analysis_mode: "idea",
  project: { name: "Idea", tagline: "" },
  judge_surface: {},
  historical_comparison: { sample_sizes: { historical_winners: 1, strong_non_winners: 1, total_analyzed: 2 }, dimensions: {} },
  criteria_alignment: { target_award: "Best Overall", criteria_summary: "x", alignment_level: "moderate" },
  prize_fits: {
    targeting_mode: "auto", evaluated_count: 3, insufficient_criteria_count: 0, summary: "",
    top_fits: [
      { prize_id: "a", award_title: "Best Overall", prize_type: "overall", fit_level: "strong", fit_label: "Strong fit", why_it_fits: "w", why_it_may_not_fit: "m", documented_requirements: [], what_must_be_demonstrated: ["Demo"], biggest_missing_requirement: "", sponsor_tech_role: "not_applicable", insufficient_criteria: false },
      { prize_id: "b", award_title: "Other", prize_type: "sponsor", fit_level: "weak", fit_label: "Weak fit", why_it_fits: "w", why_it_may_not_fit: "m", documented_requirements: [], what_must_be_demonstrated: [], biggest_missing_requirement: "", sponsor_tech_role: "absent", insufficient_criteria: false },
    ],
  },
  recommendations: {
    summary: "s", main_gap_headline: "Clear.\nSharpen.", strengths: [{ title: "T", evidence: "E", historical_context: "" }],
    gaps: [{ title: "G", evidence: "E", historical_context: "" }], next_actions: [{ priority: 1, action: "Do", reason: "R" }],
    limitations: [], build_first: "A → B → C", dont_build_yet: [],
  },
  notes: [],
  telemetry: { jev_used: false, gemini_used: true, fallback_used: false, result_quality: "full" },
};
const projectResult = { ...ideaResult, analysis_mode: "project", prize_fits: undefined, engineering: { status: "accessible", approx_loc: 1, primary_languages: [], frontend_frameworks: [], backend_frameworks: [], databases: [], model_providers: [], test_files_count: 0, api_routes_count: 0, has_ci: false, live_deployment_reachable: false, todo_fixme_count: 0 } };

function mockFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes("/prizes")) return new Response("{}", { status: 404 });
    return handler(String(url), init);
  }));
}
const json = (body: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

const events = () => posthog.capture.mock.calls.map(([name, props]) => ({ name: name as string, props: props as Record<string, unknown> }));
const named = (n: string) => events().filter((e) => e.name === n);

async function submitIdea() {
  const user = userEvent.setup();
  render(<Home />);
  await user.type(screen.getByLabelText(/Tell us what you/i), SECRET_IDEA);
  await user.click(screen.getByRole("button", { name: /Review this idea/i }));
  return user;
}

beforeEach(() => {
  posthog.init.mockReset();
  posthog.capture.mockReset();
  _resetAnalyticsForTests();
  initAnalytics({ NEXT_PUBLIC_POSTHOG_KEY: "phc_test", NEXT_PUBLIC_ANALYTICS_ENABLED: "true" });
  vi.stubGlobal("IntersectionObserver", class {
    constructor(private cb: (e: { isIntersecting: boolean }[]) => void) {}
    observe() { this.cb([{ isIntersecting: true }]); }
    disconnect() {}
  });
});

describe("Idea review", () => {
  it("fires analysis_started once and analysis_completed once, with safe metadata only", async () => {
    mockFetch(() => json(ideaResult));
    await submitIdea();
    await screen.findByText(/Before the hackathon/i);

    expect(named("analysis_started")).toHaveLength(1);
    expect(named("analysis_completed")).toHaveLength(1);
    expect(named("analysis_failed")).toHaveLength(0);
    expect(named("analysis_started")[0].props).toEqual({
      mode: "idea", event_id: "shellhacks2025:2025", prize_event: "shellhacks2026:2026", input_type: "manual", prize_targeting: "automatic", has_repo: false, has_demo: false,
    });
    const done = named("analysis_completed")[0].props;
    expect(done).toMatchObject({ mode: "idea", jev_used: false, gemini_used: true, fallback_used: false, result_quality: "full" });
    expect(["<2s", "2-5s", "5-10s", "10-20s", "20s+"]).toContain(done.duration_bucket);
  });

  it("never sends idea text, generated text, or anything it typed", async () => {
    mockFetch(() => json(ideaResult));
    await submitIdea();
    await screen.findByText(/Before the hackathon/i);
    const wire = JSON.stringify(posthog.capture.mock.calls);
    for (const leak of ["ZEBRA", "Mr Smith", "clinic", "A → B", "Clear.", "Sharpen", "Best Overall"]) {
      expect(wire).not.toContain(leak);
    }
  });

  it("reports the prize-fit section once it is seen, with counts only", async () => {
    mockFetch(() => json(ideaResult));
    await submitIdea();
    await waitFor(() => expect(named("prize_fit_viewed")).toHaveLength(1));
    expect(named("prize_fit_viewed")[0].props).toEqual({ event_id: "shellhacks2025:2025", prize_event: "shellhacks2026:2026", fit_count: 1, automatic_targeting: true });
  });

  it("reports evidence_opened when the drawer opens, and review_again_clicked on the back action", async () => {
    mockFetch(() => json(ideaResult));
    const user = await submitIdea();
    await screen.findByText(/Before the hackathon/i);
    const details = document.querySelector("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));
    expect(named("evidence_opened")).toEqual([{ name: "evidence_opened", props: { mode: "idea" } }]);
    await user.click(screen.getByRole("button", { name: /Review another idea/i }));
    expect(named("review_again_clicked")).toEqual([{ name: "review_again_clicked", props: { mode: "idea" } }]);
  });

  it("does not report a submission that fails client-side validation", async () => {
    mockFetch(() => json(ideaResult));
    const user = userEvent.setup();
    render(<Home />);
    const form = screen.getByRole("button", { name: /Review this idea/i }).closest("form")!;
    fireEvent.submit(form); // empty textarea
    expect(named("analysis_started")).toHaveLength(0);
    void user;
  });
});

describe("failures", () => {
  it("records a 4xx as validation without any error text", async () => {
    mockFetch(() => json({ detail: `Security rejection for GitHub URL: ${SECRET_REPO}` }, 400));
    await submitIdea();
    await screen.findByText(/Security rejection/i);
    expect(named("analysis_failed")).toHaveLength(1);
    expect(named("analysis_failed")[0].props).toEqual({
      mode: "idea", event_id: "shellhacks2025:2025", input_type: "manual", failure_stage: "validation", http_status_class: "4xx",
    });
    expect(named("analysis_completed")).toHaveLength(0);
    expect(JSON.stringify(posthog.capture.mock.calls)).not.toMatch(/private-repo|token=abc123|Security rejection/);
  });

  it("uses the backend's failure stage for 5xx, only if it is a known value", async () => {
    mockFetch(() => json({ detail: "busy" }, 503, { "x-failure-stage": "repo_analysis" }));
    await submitIdea();
    await screen.findByText(/busy/i);
    expect(named("analysis_failed")[0].props).toMatchObject({ failure_stage: "repo_analysis", http_status_class: "5xx" });
  });

  it("records a network failure and still shows a friendly error", async () => {
    mockFetch(() => { throw new TypeError("Failed to fetch"); });
    await submitIdea();
    await screen.findByText(/couldn't reach the review service/i);
    expect(named("analysis_failed")[0].props).toMatchObject({ failure_stage: "unknown", http_status_class: "network" });
    expect(named("analysis_failed")).toHaveLength(1);
  });
});

describe("Project review", () => {
  it("records has_repo/input_type without sending the URL or description", async () => {
    mockFetch(() => json(projectResult));
    const user = userEvent.setup();
    render(<Home />);
    await user.click(screen.getByRole("tab", { name: /Review a project/i }));
    expect(named("mode_selected")).toEqual([{ name: "mode_selected", props: { mode: "project" } }]);

    await user.type(screen.getByLabelText(/Project link/i), SECRET_REPO);
    await user.type(screen.getByLabelText(/What does it do/i), SECRET_DESC);
    await user.click(screen.getByRole("button", { name: /Review this project/i }));
    await screen.findByText(/What to fix/i);

    expect(named("analysis_started")[0].props).toMatchObject({ mode: "project", input_type: "github", has_repo: true, has_demo: false, prize_targeting: "none" });
    expect(named("analysis_completed")).toHaveLength(1);
    expect(named("prize_fit_viewed")).toHaveLength(0);
    const wire = JSON.stringify(posthog.capture.mock.calls);
    for (const leak of ["private-owner", "private-repo-name", "abc123", "quokka", "PRIVATE-DESCRIPTION", "github.com"]) {
      expect(wire).not.toContain(leak);
    }
  });

  it("records mode_selected only when the mode actually changes", async () => {
    mockFetch(() => json(ideaResult));
    const user = userEvent.setup();
    render(<Home />);
    await user.click(screen.getByRole("tab", { name: /Review an idea/i })); // already selected
    await user.click(screen.getByRole("tab", { name: /Review a project/i }));
    await user.click(screen.getByRole("tab", { name: /Review an idea/i }));
    expect(named("mode_selected").map((e) => e.props.mode)).toEqual(["project", "idea"]);
  });
});

describe("resilience", () => {
  it("the app works normally when analytics throws on every call", async () => {
    posthog.capture.mockImplementation(() => { throw new Error("blocked by extension"); });
    mockFetch(() => json(ideaResult));
    await submitIdea();
    expect(await screen.findByText(/Before the hackathon/i)).toBeTruthy();
  });

  it("the app works normally, with zero analytics calls, when analytics is not configured", async () => {
    posthog.capture.mockReset();
    posthog.init.mockReset();
    _resetAnalyticsForTests();
    initAnalytics({});
    mockFetch(() => json(ideaResult));
    await submitIdea();
    expect(await screen.findByText(/Before the hackathon/i)).toBeTruthy();
    expect(posthog.capture).not.toHaveBeenCalled();
    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("form values are never autocaptured", () => {
    expect(posthog.init).toHaveBeenCalledTimes(1);
    const cfg = posthog.init.mock.calls[0][1];
    expect(cfg.autocapture).toBe(false);
    expect(cfg.disable_session_recording).toBe(true);
  });
});
