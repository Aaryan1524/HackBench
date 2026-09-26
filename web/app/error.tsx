"use client";

import { useEffect } from "react";

/** If anything in the page throws while rendering, show a calm message instead of a blank screen. */
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Nothing about the failure is sent anywhere: it could contain what the user typed.
  }, []);
  return (
    <main className="min-h-screen bg-canvas text-ink flex items-center">
      <div className="max-w-xl mx-auto px-6 py-24">
        <h1 className="font-serif text-4xl font-normal tracking-tight mb-4">Something went wrong.</h1>
        <p className="text-ink-secondary leading-relaxed mb-8">
          The page hit an unexpected problem. Your review was not lost on our side. Try again, and if it keeps
          happening, reload the page.
        </p>
        <button
          type="button"
          onClick={reset}
          className="px-6 py-3.5 bg-ink text-white font-medium rounded text-sm hover:bg-neutral-800 transition-colors cursor-pointer"
        >
          Try again
        </button>
      </div>
    </main>
  );
}
