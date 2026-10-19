"use client";

/** Shown when a page cannot reach the engine API or the API refuses the request. */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <section>
      <h1>Could not load this page</h1>
      <p>
        The console could not get an answer from the engine API. Check that it is running, that
        <code> ABHIYOGAH_API_URL</code> and <code>ABHIYOGAH_API_KEY</code> are set, and that time travel uses an ADMIN key.
      </p>
      {error.digest && <p className="muted small">Reference: {error.digest}</p>}
      <button type="button" onClick={reset}>
        Try again
      </button>
    </section>
  );
}
