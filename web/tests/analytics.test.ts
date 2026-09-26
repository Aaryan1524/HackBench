import { beforeEach, describe, expect, it, vi } from "vitest";

const posthog = vi.hoisted(() => ({ init: vi.fn(), capture: vi.fn() }));
vi.mock("posthog-js", () => ({ default: posthog }));

import {
  EVENT_SCHEMA, POSTHOG_CONFIG, _resetAnalyticsForTests, analyticsEnabled, durationBucket, failureStageFor,
  initAnalytics, inputTypeFor, safeEventId, safePrizeEventId, sanitizeEvent, scrubCapture, statusClass, stripQuery,
  trackAnalysisCompleted, trackAnalysisStarted, trackModeSelected,
} from "@/lib/analytics";

const ON = { NEXT_PUBLIC_POSTHOG_KEY: "phc_test", NEXT_PUBLIC_ANALYTICS_ENABLED: "true" };
const base = {
  mode: "idea" as const, event_id: "shellhacks2025:2025" as const, prize_event: "shellhacks2026:2026" as const, input_type: "manual" as const,
  prize_targeting: "automatic" as const, has_repo: false, has_demo: false,
};

beforeEach(() => {
  posthog.init.mockReset();
  posthog.capture.mockReset();
  _resetAnalyticsForTests();
});

describe("configuration", () => {
  it("is a silent no-op without a key", () => {
    expect(() => {
      expect(initAnalytics({})).toBe(false);
      trackModeSelected({ mode: "idea" });
      trackAnalysisStarted(base);
    }).not.toThrow();
    expect(posthog.init).not.toHaveBeenCalled();
    expect(posthog.capture).not.toHaveBeenCalled();
  });

  it("stays off in development unless explicitly enabled, and can be forced off", () => {
    expect(analyticsEnabled({ NEXT_PUBLIC_POSTHOG_KEY: "k", NODE_ENV: "development" })).toBe(false);
    expect(analyticsEnabled({ NEXT_PUBLIC_POSTHOG_KEY: "k", NODE_ENV: "production" })).toBe(true);
    expect(analyticsEnabled({ NEXT_PUBLIC_POSTHOG_KEY: "k", NODE_ENV: "production", NEXT_PUBLIC_ANALYTICS_ENABLED: "false" })).toBe(false);
    expect(analyticsEnabled({ NEXT_PUBLIC_POSTHOG_KEY: "k", NODE_ENV: "development", NEXT_PUBLIC_ANALYTICS_ENABLED: "true" })).toBe(true);
  });

  it("also accepts PostHog's newer PROJECT_TOKEN variable name", () => {
    expect(analyticsEnabled({ NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN: "k", NODE_ENV: "production" })).toBe(true);
  });

  it("initialises once with privacy-preserving settings", () => {
    initAnalytics(ON);
    initAnalytics(ON);
    expect(posthog.init).toHaveBeenCalledTimes(1);
    const [key, cfg] = posthog.init.mock.calls[0];
    expect(key).toBe("phc_test");
    expect(cfg.disable_session_recording).toBe(true);
    expect(cfg.autocapture).toBe(false);
    expect(cfg.person_profiles).toBe("identified_only");
    expect(cfg.advanced_disable_feature_flags).toBe(true);
    expect(cfg.disable_surveys).toBe(true);
    expect(cfg.persistence).toBe("localStorage");
    expect(cfg.mask_all_text).toBe(true);
  });

  it("captures the automatic pageview exactly once and never captures $pageview by hand", () => {
    initAnalytics(ON);
    expect(POSTHOG_CONFIG.capture_pageview).toBe(true);
    trackModeSelected({ mode: "project" });
    trackAnalysisStarted(base);
    const names = posthog.capture.mock.calls.map((c) => c[0]);
    expect(names).not.toContain("$pageview");
  });

  it("swallows SDK failures", () => {
    posthog.init.mockImplementation(() => { throw new Error("blocked"); });
    expect(() => initAnalytics(ON)).not.toThrow();
    _resetAnalyticsForTests();
    posthog.init.mockReset();
    posthog.capture.mockImplementation(() => { throw new Error("network"); });
    initAnalytics(ON);
    expect(() => trackModeSelected({ mode: "idea" })).not.toThrow();
  });
});

describe("event privacy", () => {
  it("drops unknown properties, including free text and URLs", () => {
    initAnalytics(ON);
    const sneaky = { ...base, idea: "I want to build a secret thing", github_url: "https://github.com/a/b?token=1", description: "x" };
    trackAnalysisStarted(sneaky as unknown as typeof base);
    const props = posthog.capture.mock.calls[0][1];
    expect(Object.keys(props).sort()).toEqual(Object.keys(EVENT_SCHEMA.analysis_started).sort());
    expect(JSON.stringify(props)).not.toMatch(/secret|github|token/);
  });

  it("refuses values outside the allowed sets (no free text through enum fields)", () => {
    initAnalytics(ON);
    trackModeSelected({ mode: "my private idea text" as unknown as "idea" });
    trackAnalysisStarted({ ...base, event_id: "https://evil.example/?q=secret" as unknown as "other" });
    expect(posthog.capture).not.toHaveBeenCalled();
  });

  it("only allows booleans/enums on completion telemetry", () => {
    initAnalytics(ON);
    trackAnalysisCompleted({
      ...base, duration_bucket: "2-5s", jev_used: false, gemini_used: true, fallback_used: false, result_quality: "full",
    });
    const props = posthog.capture.mock.calls[0][1];
    for (const k of ["jev_used", "gemini_used", "fallback_used"]) expect(typeof props[k]).toBe("boolean");
    expect(sanitizeEvent("analysis_completed", { ...base, duration_bucket: "2-5s", jev_used: "yes" as unknown as boolean, gemini_used: true, fallback_used: false, result_quality: "full" })).toBeNull();
  });

  it("knows every baseline the UI offers, including all-years-combined, and not the retired 2026 option", () => {
    for (const id of ["shellhacks2025:2025", "shellhacks2024:2024", "shellhacks-2023:2023", "all:combined"]) {
      expect(safeEventId(id)).toBe(id);
    }
    // 2026 has no results, so it is a prize source but never a comparison baseline.
    expect(safeEventId("shellhacks2026:2026")).toBe("other");
    expect(safePrizeEventId("shellhacks2026:2026")).toBe("shellhacks2026:2026");
    expect(safePrizeEventId("my-private-hackathon")).toBe("other");
  });

  it("maps hackathon ids through an allow-list", () => {
    expect(safeEventId("shellhacks2025:2025")).toBe("shellhacks2025:2025");
    expect(safeEventId("my-private-hackathon")).toBe("other");
  });
});

describe("helpers", () => {
  it("buckets durations", () => {
    expect(durationBucket(400)).toBe("<2s");
    expect(durationBucket(2000)).toBe("2-5s");
    expect(durationBucket(7500)).toBe("5-10s");
    expect(durationBucket(15000)).toBe("10-20s");
    expect(durationBucket(61000)).toBe("20s+");
  });

  it("classifies input types without looking at URLs", () => {
    expect(inputTypeFor({ mode: "idea", manualSubmode: false, github: false, devpost: false })).toBe("manual");
    expect(inputTypeFor({ mode: "project", manualSubmode: false, github: true, devpost: false })).toBe("github");
    expect(inputTypeFor({ mode: "project", manualSubmode: false, github: false, devpost: true })).toBe("devpost");
    expect(inputTypeFor({ mode: "project", manualSubmode: false, github: true, devpost: true })).toBe("mixed");
    expect(inputTypeFor({ mode: "project", manualSubmode: true, github: true, devpost: false })).toBe("mixed");
    expect(inputTypeFor({ mode: "project", manualSubmode: true, github: false, devpost: false })).toBe("manual");
  });

  it("derives status class and failure stage safely", () => {
    expect(statusClass(400)).toBe("4xx");
    expect(statusClass(503)).toBe("5xx");
    expect(failureStageFor(400, "repo_analysis")).toBe("validation");
    expect(failureStageFor(503, "repo_analysis")).toBe("repo_analysis");
    expect(failureStageFor(500, "<script>")).toBe("unknown");
    expect(failureStageFor(500, null)).toBe("unknown");
  });
});

describe("url scrubbing (attribution kept, everything else removed)", () => {
  it("keeps utm_* and ref and drops other query params and fragments", () => {
    expect(stripQuery("https://hackbench.app/?utm_source=github&utm_campaign=launch&ref=x&token=abc&repo=https%3A%2F%2Fgithub.com%2Fa#frag"))
      .toBe("https://hackbench.app/?utm_source=github&utm_campaign=launch&ref=x");
    expect(stripQuery("https://www.linkedin.com/feed/?trk=secret")).toBe("https://www.linkedin.com/feed/");
  });

  it("scrubs URL properties on every captured event, including $set and $set_once", () => {
    const cr = {
      properties: {
        $current_url: "https://h.app/?q=secret&utm_source=li",
        $referrer: "https://google.com/search?q=private",
        $set: { $initial_referrer: "https://x.com/?u=1" },
        $set_once: { $initial_current_url: "https://h.app/?email=a@b.c" },
      },
    };
    const out = scrubCapture(cr);
    const text = JSON.stringify(out);
    expect(text).not.toMatch(/secret|private|email|u=1/);
    expect(text).toContain("utm_source=li");
  });

  it("never throws on odd input", () => {
    expect(() => scrubCapture(null)).not.toThrow();
    expect(() => scrubCapture({ properties: { $current_url: 5 as unknown as string } })).not.toThrow();
  });
});
