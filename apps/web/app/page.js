const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";

async function fetchHealth() {
  try {
    const response = await fetch(`${coreBase}/health`, { cache: "no-store" });
    if (!response.ok) {
      return { ok: false, service: "unknown" };
    }
    return response.json();
  } catch {
    return { ok: false, service: "unreachable" };
  }
}

async function fetchJobs() {
  try {
    const response = await fetch(`${coreBase}/jobs`, { cache: "no-store" });
    if (!response.ok) {
      return [];
    }
    return response.json();
  } catch {
    return [];
  }
}

export default async function HomePage() {
  const [health, jobs] = await Promise.all([fetchHealth(), fetchJobs()]);

  return (
    <main style={{ maxWidth: 1100, margin: "40px auto", padding: "0 20px" }}>
      <section
        style={{
          background: "linear-gradient(130deg, #0d2026, #1c5d63)",
          borderRadius: 20,
          padding: 28,
          color: "#eff9fa"
        }}
      >
        <h1 style={{ margin: "0 0 8px", fontSize: 34 }}>Odoo Connector Control Plane</h1>
        <p style={{ margin: 0, opacity: 0.9 }}>
          Core Service: <strong>{health.service}</strong> | Status: {health.ok ? "Healthy" : "Unreachable"}
        </p>
      </section>

      <section style={{ marginTop: 24, display: "grid", gap: 18, gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        <div style={{ background: "#ffffff", borderRadius: 16, padding: 20, boxShadow: "0 6px 20px rgba(13, 32, 38, 0.08)" }}>
          <h2 style={{ marginTop: 0 }}>Connector Setup</h2>
          <ol style={{ paddingLeft: 20, margin: 0, lineHeight: 1.6 }}>
            <li>Create tenant via Core API `POST /tenants`.</li>
            <li>Create connection via `POST /connections` with encrypted `credential_payload`.</li>
            <li>Configure webhook source to `apps/mcp` endpoint.</li>
            <li>Or start Shopify OAuth: `GET /oauth/shopify/start?tenant_id=...&shop=...`.</li>
          </ol>
        </div>

        <div style={{ background: "#ffffff", borderRadius: 16, padding: 20, boxShadow: "0 6px 20px rgba(13, 32, 38, 0.08)" }}>
          <h2 style={{ marginTop: 0 }}>Queue Health</h2>
          <p style={{ marginTop: 0 }}>
            Job Count: <strong>{jobs.length}</strong>
          </p>
          <p style={{ marginBottom: 0, color: "#3f5056" }}>
            Open `/jobs` in Core API for full job detail and retry actions.
          </p>
        </div>
      </section>

      <section style={{ marginTop: 24, background: "#ffffff", borderRadius: 16, padding: 20, boxShadow: "0 6px 20px rgba(13, 32, 38, 0.08)" }}>
        <h2 style={{ marginTop: 0 }}>Recent Sync Jobs</h2>
        {jobs.length === 0 ? (
          <p style={{ marginBottom: 0 }}>No jobs yet. Trigger a webhook or poll sync.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #dbe5e7" }}>
                <th style={{ padding: "8px 4px" }}>ID</th>
                <th style={{ padding: "8px 4px" }}>Connector</th>
                <th style={{ padding: "8px 4px" }}>Type</th>
                <th style={{ padding: "8px 4px" }}>Status</th>
                <th style={{ padding: "8px 4px" }}>Attempts</th>
                <th style={{ padding: "8px 4px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.slice(0, 10).map((job) => (
                <tr key={job.id} style={{ borderBottom: "1px solid #eef3f4" }}>
                  <td style={{ padding: "8px 4px", fontFamily: "monospace" }}>{job.id.slice(0, 8)}</td>
                  <td style={{ padding: "8px 4px" }}>{job.connector}</td>
                  <td style={{ padding: "8px 4px" }}>{job.job_type}</td>
                  <td style={{ padding: "8px 4px" }}>{job.status}</td>
                  <td style={{ padding: "8px 4px" }}>{job.attempts}</td>
                  <td style={{ padding: "8px 4px", display: "flex", gap: 8 }}>
                    {(job.status === "failed" || job.status === "deadletter") && (
                      <form method="post" action={`/api/jobs/${job.id}/retry`}>
                        <button type="submit">Retry</button>
                      </form>
                    )}
                    {(job.status === "queued" || job.status === "running" || job.status === "failed") && (
                      <form method="post" action={`/api/jobs/${job.id}/deadletter`}>
                        <button type="submit">Dead-letter</button>
                      </form>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
