"use client";

import { useEffect } from "react";
import { initAnalytics } from "@/lib/analytics";

/** Starts analytics once on the client. Renders nothing and can never throw into the app. */
export default function AnalyticsInit() {
  useEffect(() => {
    initAnalytics();
  }, []);
  return null;
}
