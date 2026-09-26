"use client";

/** Last-resort boundary for errors in the root layout itself. Self-contained: no app styles are guaranteed here. */
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#faf8f3", color: "#141414", margin: 0 }}>
        <main style={{ maxWidth: 560, margin: "0 auto", padding: "96px 24px" }}>
          <h1 style={{ fontSize: 32, fontWeight: 400, marginBottom: 16 }}>Something went wrong.</h1>
          <p style={{ lineHeight: 1.6, marginBottom: 32 }}>Please try again. If it keeps happening, reload the page.</p>
          <button
            type="button"
            onClick={reset}
            style={{ padding: "14px 24px", background: "#141414", color: "#fff", border: 0, borderRadius: 4, cursor: "pointer" }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
