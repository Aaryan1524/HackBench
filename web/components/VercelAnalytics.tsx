"use client";

import { Analytics } from "@vercel/analytics/next";
import { stripQuery } from "@/lib/analytics";

type VercelEvent = { type: string; url: string };

/** Page-view analytics from Vercel. Cookieless; query strings are stripped except utm_* and ref, like PostHog. */
export function sanitizeVercelEvent<T extends VercelEvent>(event: T): T {
  try {
    return { ...event, url: String(stripQuery(event.url)) };
  } catch {
    return event;
  }
}

export default function VercelAnalytics() {
  // NEXT_PUBLIC_ANALYTICS_ENABLED=false turns every analytics tool off, including this one.
  if (process.env.NEXT_PUBLIC_ANALYTICS_ENABLED === "false") return null;
  return <Analytics beforeSend={sanitizeVercelEvent} />;
}
