/**
 * Privacy-conscious product analytics (PostHog).
 *
 * Rules enforced here, in one place:
 *  - Only the events and properties declared in EVENT_SCHEMA can ever be sent. Anything else is dropped.
 *  - Property values must be booleans, numbers, or members of a fixed set. Free text can never pass.
 *  - No autocapture, no session recording, no feature flags, no surveys, no person profiles.
 *  - URLs that PostHog attaches itself are stripped of query strings, except utm_* and ref (traffic attribution).
 *  - Missing config, a disabled flag, or any SDK error turns every call into a silent no-op.
 */
import posthog from "posthog-js";

export type Mode = "idea" | "project";
export type InputType = "manual" | "github" | "devpost" | "mixed";
export type PrizeTargeting = "automatic" | "specific" | "none";
export type FailureStage =
  | "validation"
  | "source_fetch"
  | "repo_analysis"
  | "ai_provider"
  | "historical_lookup"
  | "unknown";
export type StatusClass = "4xx" | "5xx" | "network";
export type DurationBucket = "<2s" | "2-5s" | "5-10s" | "10-20s" | "20s+";
export type ResultQuality = "full" | "partial";

/** Public, predefined hackathon identifiers only. Anything else is reported as "other". */
export const KNOWN_EVENT_IDS = [
  "shellhacks2025:2025",
  "shellhacks2024:2024",
  "shellhacks-2023:2023",
  "all:combined",
] as const;
export type EventId = (typeof KNOWN_EVENT_IDS)[number] | "other";

/** Where prizes come from: this year's challenges (no results yet) or any comparison baseline. */
export const KNOWN_PRIZE_EVENT_IDS = ["shellhacks2026:2026", ...KNOWN_EVENT_IDS] as const;
export type PrizeEventId = (typeof KNOWN_PRIZE_EVENT_IDS)[number] | "other";

interface AnalysisBase {
  mode: Mode;
  event_id: EventId; // the past results compared against
  prize_event: PrizeEventId; // whose prizes were matched
  input_type: InputType;
  prize_targeting: PrizeTargeting;
  has_repo: boolean;
  has_demo: boolean;
}

export interface EventMap {
  mode_selected: { mode: Mode };
  analysis_started: AnalysisBase;
  analysis_completed: AnalysisBase & {
    duration_bucket: DurationBucket;
    jev_used: boolean;
    gemini_used: boolean;
    fallback_used: boolean;
    result_quality: ResultQuality;
  };
  analysis_failed: {
    mode: Mode;
    event_id: EventId;
    input_type: InputType;
    failure_stage: FailureStage;
    http_status_class: StatusClass;
  };
  prize_fit_viewed: { event_id: EventId; prize_event: PrizeEventId; fit_count: number; automatic_targeting: boolean };
  evidence_opened: { mode: Mode };
  review_again_clicked: { mode: Mode };
}

type Validator = (v: unknown) => boolean;
const oneOf =
  (...allowed: readonly string[]): Validator =>
  (v) =>
    typeof v === "string" && allowed.includes(v);
const isBool: Validator = (v) => typeof v === "boolean";
const isCount: Validator = (v) => typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= 1000;

const V = {
  mode: oneOf("idea", "project"),
  event_id: oneOf(...KNOWN_EVENT_IDS, "other"),
  prize_event: oneOf(...KNOWN_PRIZE_EVENT_IDS, "other"),
  input_type: oneOf("manual", "github", "devpost", "mixed"),
  prize_targeting: oneOf("automatic", "specific", "none"),
  duration_bucket: oneOf("<2s", "2-5s", "5-10s", "10-20s", "20s+"),
  result_quality: oneOf("full", "partial"),
  failure_stage: oneOf("validation", "source_fetch", "repo_analysis", "ai_provider", "historical_lookup", "unknown"),
  http_status_class: oneOf("4xx", "5xx", "network"),
};

const ANALYSIS_BASE = {
  mode: V.mode,
  event_id: V.event_id,
  prize_event: V.prize_event,
  input_type: V.input_type,
  prize_targeting: V.prize_targeting,
  has_repo: isBool,
  has_demo: isBool,
};

/** The complete list of what may leave the browser. */
export const EVENT_SCHEMA: { [E in keyof EventMap]: Record<keyof EventMap[E], Validator> } = {
  mode_selected: { mode: V.mode },
  analysis_started: ANALYSIS_BASE,
  analysis_completed: {
    ...ANALYSIS_BASE,
    duration_bucket: V.duration_bucket,
    jev_used: isBool,
    gemini_used: isBool,
    fallback_used: isBool,
    result_quality: V.result_quality,
  },
  analysis_failed: {
    mode: V.mode,
    event_id: V.event_id,
    input_type: V.input_type,
    failure_stage: V.failure_stage,
    http_status_class: V.http_status_class,
  },
  prize_fit_viewed: { event_id: V.event_id, prize_event: V.prize_event, fit_count: isCount, automatic_targeting: isBool },
  evidence_opened: { mode: V.mode },
  review_again_clicked: { mode: V.mode },
};

/** Keep only declared keys with valid values. Returns null if any declared key is missing or invalid. */
export function sanitizeEvent<E extends keyof EventMap>(event: E, props: EventMap[E]): Record<string, unknown> | null {
  const schema = EVENT_SCHEMA[event] as Record<string, Validator> | undefined;
  if (!schema) return null;
  const source = props as unknown as Record<string, unknown>;
  const clean: Record<string, unknown> = {};
  for (const [key, validate] of Object.entries(schema)) {
    if (!validate(source[key])) return null;
    clean[key] = source[key];
  }
  return clean;
}

// ---------- pure helpers ----------

export function durationBucket(ms: number): DurationBucket {
  const s = ms / 1000;
  if (s < 2) return "<2s";
  if (s < 5) return "2-5s";
  if (s < 10) return "5-10s";
  if (s < 20) return "10-20s";
  return "20s+";
}

export function safeEventId(id: string): EventId {
  return (KNOWN_EVENT_IDS as readonly string[]).includes(id) ? (id as EventId) : "other";
}

export function safePrizeEventId(id: string): PrizeEventId {
  return (KNOWN_PRIZE_EVENT_IDS as readonly string[]).includes(id) ? (id as PrizeEventId) : "other";
}

export function statusClass(status: number): "4xx" | "5xx" {
  return status >= 500 ? "5xx" : "4xx";
}

export function failureStageFor(status: number, headerValue: string | null): FailureStage {
  if (status >= 400 && status < 500) return "validation";
  return V.failure_stage(headerValue) ? (headerValue as FailureStage) : "unknown";
}

export function inputTypeFor(args: {
  mode: Mode;
  manualSubmode: boolean;
  github: boolean;
  devpost: boolean;
}): InputType {
  if (args.mode === "idea") return "manual";
  if (args.github && args.devpost) return "mixed";
  if (args.github) return args.manualSubmode ? "mixed" : "github";
  if (args.devpost) return args.manualSubmode ? "mixed" : "devpost";
  return "manual";
}

/** Keep utm_* and ref (attribution); drop every other query parameter and the fragment. */
export function stripQuery(url: unknown): unknown {
  if (typeof url !== "string" || !url) return url;
  try {
    const u = new URL(url);
    const keep = new URLSearchParams();
    u.searchParams.forEach((value, key) => {
      if (/^utm_/i.test(key) || key === "ref") keep.set(key, value.slice(0, 100));
    });
    const query = keep.toString();
    return `${u.origin}${u.pathname}${query ? `?${query}` : ""}`;
  } catch {
    return url;
  }
}

const URL_PROPS = ["$current_url", "$referrer", "$initial_current_url", "$initial_referrer", "$session_entry_url", "$session_entry_referrer"];

/** PostHog before_send hook: scrub URL-like properties, never let an error escape. */
export function scrubCapture<T extends { properties?: Record<string, unknown> } | null>(cr: T): T {
  try {
    if (cr && cr.properties) {
      const props = cr.properties as Record<string, unknown>;
      const containers = [props, props["$set"], props["$set_once"]];
      for (const box of containers) {
        if (!box || typeof box !== "object") continue;
        const record = box as Record<string, unknown>;
        for (const key of URL_PROPS) {
          if (key in record) record[key] = stripQuery(record[key]);
        }
      }
    }
  } catch {
    /* analytics must never throw */
  }
  return cr;
}

// ---------- configuration and init ----------

// Next.js only inlines NEXT_PUBLIC_* variables that are referenced literally, so list them explicitly.
const CLIENT_ENV: Record<string, string | undefined> = {
  NEXT_PUBLIC_POSTHOG_KEY: process.env.NEXT_PUBLIC_POSTHOG_KEY,
  NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN: process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN,
  NEXT_PUBLIC_POSTHOG_HOST: process.env.NEXT_PUBLIC_POSTHOG_HOST,
  NEXT_PUBLIC_ANALYTICS_ENABLED: process.env.NEXT_PUBLIC_ANALYTICS_ENABLED,
  NODE_ENV: process.env.NODE_ENV,
};

export function analyticsKey(env: Record<string, string | undefined> = CLIENT_ENV): string {
  return (env.NEXT_PUBLIC_POSTHOG_KEY || env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN || "").trim();
}

export function analyticsEnabled(env: Record<string, string | undefined> = CLIENT_ENV): boolean {
  if (!analyticsKey(env)) return false;
  const flag = (env.NEXT_PUBLIC_ANALYTICS_ENABLED || "").toLowerCase();
  if (flag === "false") return false;
  if (flag === "true") return true;
  return env.NODE_ENV === "production"; // local dev stays off unless explicitly enabled
}

export const POSTHOG_CONFIG = {
  autocapture: false, // explicit events only: nothing typed into the page can be captured
  capture_pageview: true, // one automatic $pageview per page load (single-route app); never captured manually too
  capture_pageleave: false,
  disable_session_recording: true,
  disable_surveys: true,
  advanced_disable_feature_flags: true,
  person_profiles: "identified_only" as const, // anonymous visitors get no person profile
  persistence: "localStorage" as const, // no cookies
  respect_dnt: true,
  mask_all_text: true,
  mask_all_element_attributes: true,
  before_send: scrubCapture,
};

let initialized = false;
let active = false;

export function initAnalytics(env: Record<string, string | undefined> = CLIENT_ENV): boolean {
  if (initialized) return active;
  initialized = true;
  try {
    if (!analyticsEnabled(env)) return (active = false);
    posthog.init(analyticsKey(env), {
      api_host: env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
      ...POSTHOG_CONFIG,
    });
    active = true;
  } catch {
    active = false;
  }
  return active;
}

/** Test hook: reset module state. */
export function _resetAnalyticsForTests(): void {
  initialized = false;
  active = false;
}

function send<E extends keyof EventMap>(event: E, props: EventMap[E]): void {
  try {
    if (!active) return;
    const clean = sanitizeEvent(event, props);
    if (!clean) return;
    posthog.capture(event, clean);
  } catch {
    /* fire and forget */
  }
}

export const trackModeSelected = (p: EventMap["mode_selected"]) => send("mode_selected", p);
export const trackAnalysisStarted = (p: EventMap["analysis_started"]) => send("analysis_started", p);
export const trackAnalysisCompleted = (p: EventMap["analysis_completed"]) => send("analysis_completed", p);
export const trackAnalysisFailed = (p: EventMap["analysis_failed"]) => send("analysis_failed", p);
export const trackPrizeFitViewed = (p: EventMap["prize_fit_viewed"]) => send("prize_fit_viewed", p);
export const trackEvidenceOpened = (p: EventMap["evidence_opened"]) => send("evidence_opened", p);
export const trackReviewAgainClicked = (p: EventMap["review_again_clicked"]) => send("review_again_clicked", p);
