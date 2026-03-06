"use client";

import { useMemo, useState } from "react";

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    cache: "no-store"
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail || data?.error || `Request failed (${response.status})`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

const sectionStyle = {
  background: "#ffffff",
  border: "1px solid #d5e1df",
  borderRadius: 14,
  padding: 16,
  boxShadow: "0 8px 20px rgba(11, 37, 35, 0.06)"
};

const inputStyle = {
  width: "100%",
  border: "1px solid #b8c9c6",
  borderRadius: 10,
  padding: "10px 12px",
  fontSize: 14,
  boxSizing: "border-box"
};

const buttonStyle = {
  background: "#0b6159",
  color: "#ffffff",
  border: "none",
  borderRadius: 10,
  padding: "10px 14px",
  cursor: "pointer",
  fontWeight: 600
};

function StatusPill({ text, tone = "neutral" }) {
  const bg = tone === "good" ? "#d8f5e5" : tone === "bad" ? "#ffe0df" : "#ecf2f1";
  const color = tone === "good" ? "#17613b" : tone === "bad" ? "#8e1f1b" : "#2e4c49";
  return <span style={{ background: bg, color, borderRadius: 999, padding: "2px 10px", fontSize: 12 }}>{text}</span>;
}

export default function ControlPlaneApp({ initialHealth, initialJobs }) {
  const [tenantName, setTenantName] = useState("Acme Operations");
  const [tenantSlug, setTenantSlug] = useState("acme");
  const [tenantId, setTenantId] = useState("");

  const [odooBaseUrl, setOdooBaseUrl] = useState("https://odoo.example.com");
  const [odooDatabase, setOdooDatabase] = useState("prod_db");
  const [odooUsername, setOdooUsername] = useState("admin@example.com");
  const [odooPassword, setOdooPassword] = useState("");
  const [odooConnStatus, setOdooConnStatus] = useState("unknown");
  const [odooConnMessage, setOdooConnMessage] = useState("");

  const [targetAddress, setTargetAddress] = useState("support@example.com");
  const [sinceCursor, setSinceCursor] = useState("2026-03-01T00:00:00Z");
  const [webhookSecret, setWebhookSecret] = useState("replace-me");
  const [gmailAccountId, setGmailAccountId] = useState("default");
  const [gmailEmail, setGmailEmail] = useState("");
  const [gmailClientId, setGmailClientId] = useState("");
  const [gmailClientSecret, setGmailClientSecret] = useState("");
  const [gmailRefreshToken, setGmailRefreshToken] = useState("");
  const [gmailAccessToken, setGmailAccessToken] = useState("");
  const [gmailAccounts, setGmailAccounts] = useState([]);
  const [gmailWindowDays, setGmailWindowDays] = useState("7");
  const [gmailMaxMessages, setGmailMaxMessages] = useState("20");
  const [gmailIncludeAttachments, setGmailIncludeAttachments] = useState(true);

  const [health, setHealth] = useState(initialHealth || { ok: false, service: "unknown" });
  const [jobs, setJobs] = useState(Array.isArray(initialJobs) ? initialJobs : []);
  const [emails, setEmails] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const latestJobs = useMemo(() => jobs.slice(0, 20), [jobs]);

  function resetFeedback() {
    setError("");
    setNotice("");
  }

  async function refreshHealth() {
    try {
      const data = await apiFetch("/api/core/health", { method: "GET" });
      setHealth(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshJobs() {
    try {
      const query = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : "";
      const data = await apiFetch(`/api/core/jobs${query}`, { method: "GET" });
      setJobs(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshEmails() {
    if (!tenantId) {
      return;
    }
    try {
      const query = new URLSearchParams({ tenant_id: tenantId, limit: "100" });
      if (targetAddress) {
        query.set("to_address", targetAddress);
      }
      const data = await apiFetch(`/api/core/emails?${query.toString()}`, { method: "GET" });
      setEmails(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshGmailAccounts() {
    if (!tenantId) {
      return;
    }
    try {
      const data = await apiFetch(`/api/core/gmail/accounts?tenant_id=${encodeURIComponent(tenantId)}`, { method: "GET" });
      setGmailAccounts(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createTenant(event) {
    event.preventDefault();
    resetFeedback();
    setBusy(true);
    try {
      const data = await apiFetch("/api/core/tenants", {
        method: "POST",
        body: JSON.stringify({ name: tenantName, slug: tenantSlug })
      });
      setTenantId(data.id);
      setNotice(`Tenant created: ${data.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function createConnection(event) {
    event.preventDefault();
    resetFeedback();
    if (!tenantId) {
      setError("Create or set a tenant ID first.");
      return;
    }
    setBusy(true);
    try {
      const data = await apiFetch("/api/core/connections", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          connector: "odoo",
          external_account_id: odooDatabase,
          credential_payload: {
            username: odooUsername,
            password: odooPassword
          },
          metadata: {
            base_url: odooBaseUrl,
            database: odooDatabase,
            protocol: "jsonrpc"
          }
        })
      });
      setOdooConnStatus(data.validated ? "connected" : "unknown");
      setOdooConnMessage(data.message || "");
      setNotice(
        data.validated
          ? `Connection active and validated: ${data.id}`
          : `Connection active: ${data.id}`
      );
    } catch (err) {
      setOdooConnStatus("failed");
      setOdooConnMessage(err.message);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function testConnection() {
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/connections/test", {
        method: "POST",
        body: JSON.stringify({ tenant_id: tenantId, connector: "odoo" })
      });
      setOdooConnStatus(result.ok ? "connected" : "failed");
      setOdooConnMessage(result.message || "");
      setNotice(result.ok ? "Odoo connection test succeeded." : "Odoo connection test failed.");
    } catch (err) {
      setOdooConnStatus("failed");
      setOdooConnMessage(err.message);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function triggerEmailSync(event) {
    event.preventDefault();
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    setBusy(true);
    try {
      const job = await apiFetch("/api/core/sync/emails/import", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          connector: "odoo",
          since_cursor: sinceCursor,
          target_address: targetAddress,
          source: "odoo_alias_fetchmail",
          limit: 200
        })
      });
      setNotice(`IMPORT_EMAILS queued: ${job.id}`);
      await Promise.all([refreshJobs(), refreshEmails()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function triggerGmailFetch(event) {
    event.preventDefault();
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/sync/gmail/import", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          account_id: gmailAccountId,
          mailbox: "INBOX",
          window_days: Number(gmailWindowDays || 7),
          max_messages: Number(gmailMaxMessages || 20),
          target_to_address: targetAddress,
          include_headers: false,
          include_snippet: true,
          include_attachments: gmailIncludeAttachments,
          extract_attachment_text: gmailIncludeAttachments
        })
      });
      setNotice(
        `Gmail import complete: imported=${result.imported_count}, fetched=${result.fetched_count}, attachments=${result.attachments_processed}`
      );
      await Promise.all([refreshEmails(), refreshJobs()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveGmailAccount(event) {
    event.preventDefault();
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/gmail/accounts", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          account_id: gmailAccountId,
          email: gmailEmail,
          client_id: gmailClientId,
          client_secret: gmailClientSecret,
          refresh_token: gmailRefreshToken,
          access_token: gmailAccessToken,
          redirect_uri: "urn:ietf:wg:oauth:2.0:oob"
        })
      });
      setNotice(`Gmail OAuth account saved: ${result.account_id}`);
      await refreshGmailAccounts();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function deactivateGmailAccount(accountId) {
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    setBusy(true);
    try {
      await apiFetch(
        `/api/core/gmail/accounts/${encodeURIComponent(accountId)}?tenant_id=${encodeURIComponent(tenantId)}`,
        { method: "DELETE" }
      );
      setNotice(`Gmail account deactivated: ${accountId}`);
      await refreshGmailAccounts();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendWebhookSample(event) {
    event.preventDefault();
    resetFeedback();
    if (!tenantSlug) {
      setError("Tenant slug is required.");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        id: `provider-${Date.now()}`,
        subject: "Inbound support request",
        from: "customer@example.com",
        to: targetAddress,
        body: "Please review attached invoice PDF.",
        received_at: new Date().toISOString()
      };

      await apiFetch("/api/mcp/webhooks/email/inbound", {
        method: "POST",
        body: JSON.stringify({
          tenant_slug: tenantSlug,
          connector: "odoo",
          target_address: targetAddress,
          webhook_secret: webhookSecret,
          email_payload: payload
        })
      });

      setNotice("Webhook accepted by MCP. Worker will queue/import shortly.");
      await Promise.all([refreshJobs(), refreshEmails()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function retryJob(jobId) {
    resetFeedback();
    setBusy(true);
    try {
      await apiFetch(`/api/core/jobs/${jobId}/retry`, { method: "POST" });
      setNotice(`Retried job: ${jobId}`);
      await refreshJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function deadletterJob(jobId) {
    resetFeedback();
    setBusy(true);
    try {
      await apiFetch(`/api/core/jobs/${jobId}/deadletter`, { method: "POST" });
      setNotice(`Dead-lettered job: ${jobId}`);
      await refreshJobs();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshAll() {
    resetFeedback();
    setBusy(true);
    try {
      await Promise.all([refreshHealth(), refreshJobs(), refreshEmails(), refreshGmailAccounts()]);
      setNotice("Data refreshed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 1280, margin: "28px auto", padding: "0 16px 36px" }}>
      <header
        style={{
          background: "linear-gradient(140deg, #062a2a 0%, #0b6159 55%, #2e8b7c 100%)",
          color: "#ecfdfa",
          borderRadius: 20,
          padding: 24,
          boxShadow: "0 12px 28px rgba(6, 42, 42, 0.28)"
        }}
      >
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 31 }}>Odoo Adapter Workflow Console</h1>
            <p style={{ margin: "8px 0 0", opacity: 0.92 }}>
              Full workflow: tenant setup, Odoo connect, email sync, inbound webhook ingest, and operations.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <StatusPill text={health.ok ? `Core: ${health.service}` : "Core Unreachable"} tone={health.ok ? "good" : "bad"} />
            <button type="button" style={buttonStyle} onClick={refreshAll} disabled={busy}>
              {busy ? "Working..." : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      {(error || notice) && (
        <section style={{ marginTop: 14, ...sectionStyle }}>
          {error && <p style={{ margin: 0, color: "#9d1f1f" }}>Error: {error}</p>}
          {notice && <p style={{ margin: error ? "8px 0 0" : 0, color: "#165a39" }}>{notice}</p>}
        </section>
      )}

      <section style={{ marginTop: 16, display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
        <form onSubmit={createTenant} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 1. Create Tenant</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>Create your tenant and retain `tenant_id` + `slug` for all other actions.</p>
          <div style={{ display: "grid", gap: 10 }}>
            <input style={inputStyle} value={tenantName} onChange={(e) => setTenantName(e.target.value)} placeholder="Tenant name" required />
            <input style={inputStyle} value={tenantSlug} onChange={(e) => setTenantSlug(e.target.value)} placeholder="Tenant slug" required />
            <input style={inputStyle} value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="Tenant ID (auto-filled after create)" />
            <button type="submit" style={buttonStyle} disabled={busy}>Create Tenant</button>
          </div>
        </form>

        <form onSubmit={createConnection} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 2. Connect Odoo</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>Saves encrypted credentials and activates the Odoo connection for this tenant.</p>
          <div style={{ display: "grid", gap: 10 }}>
            <input style={inputStyle} value={odooBaseUrl} onChange={(e) => setOdooBaseUrl(e.target.value)} placeholder="https://odoo.example.com" required />
            <input style={inputStyle} value={odooDatabase} onChange={(e) => setOdooDatabase(e.target.value)} placeholder="Database" required />
            <input style={inputStyle} value={odooUsername} onChange={(e) => setOdooUsername(e.target.value)} placeholder="Username" required />
            <input style={inputStyle} type="password" value={odooPassword} onChange={(e) => setOdooPassword(e.target.value)} placeholder="Password" required />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="submit" style={buttonStyle} disabled={busy}>Create/Update Odoo Connection</button>
              <button type="button" style={{ ...buttonStyle, background: "#2f556d" }} onClick={testConnection} disabled={busy}>
                Test Connection
              </button>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <strong style={{ color: "#33514d" }}>Connection status:</strong>
              <StatusPill
                text={
                  odooConnStatus === "connected"
                    ? "Connected"
                    : odooConnStatus === "failed"
                      ? "Failed"
                      : "Unknown"
                }
                tone={odooConnStatus === "connected" ? "good" : odooConnStatus === "failed" ? "bad" : "neutral"}
              />
            </div>
            {odooConnMessage && (
              <p style={{ margin: 0, color: odooConnStatus === "failed" ? "#9d1f1f" : "#35514d" }}>
                {odooConnMessage}
              </p>
            )}
          </div>
        </form>

        <form onSubmit={saveGmailAccount} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 3. Save Gmail OAuth Account</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>
            Stores Gmail OAuth secrets encrypted in DB (`credential_vault`) and links account metadata.
          </p>
          <div style={{ display: "grid", gap: 10 }}>
            <input style={inputStyle} value={gmailAccountId} onChange={(e) => setGmailAccountId(e.target.value)} placeholder="account_id" required />
            <input style={inputStyle} value={gmailEmail} onChange={(e) => setGmailEmail(e.target.value)} placeholder="gmail address (optional)" />
            <input style={inputStyle} value={gmailClientId} onChange={(e) => setGmailClientId(e.target.value)} placeholder="Gmail client_id" required />
            <input style={inputStyle} type="password" value={gmailClientSecret} onChange={(e) => setGmailClientSecret(e.target.value)} placeholder="Gmail client_secret" required />
            <input style={inputStyle} type="password" value={gmailRefreshToken} onChange={(e) => setGmailRefreshToken(e.target.value)} placeholder="Gmail refresh_token" required />
            <input style={inputStyle} type="password" value={gmailAccessToken} onChange={(e) => setGmailAccessToken(e.target.value)} placeholder="Gmail access_token (optional)" />
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button type="submit" style={buttonStyle} disabled={busy}>Save Gmail OAuth</button>
              <button type="button" style={{ ...buttonStyle, background: "#3a6f69" }} onClick={refreshGmailAccounts} disabled={busy}>Refresh Accounts</button>
            </div>
          </div>
        </form>

        <form onSubmit={triggerEmailSync} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 4. Pull Odoo Emails</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>Queues `IMPORT_EMAILS` from Odoo `mail.message` (alias/fetchmail flow).</p>
          <div style={{ display: "grid", gap: 10 }}>
            <input style={inputStyle} value={targetAddress} onChange={(e) => setTargetAddress(e.target.value)} placeholder="target address" required />
            <input style={inputStyle} value={sinceCursor} onChange={(e) => setSinceCursor(e.target.value)} placeholder="since cursor ISO timestamp" />
            <button type="submit" style={buttonStyle} disabled={busy}>Trigger IMPORT_EMAILS</button>
          </div>
        </form>

        <form onSubmit={triggerGmailFetch} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 5. Gmail Fetch via MCP</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>
            Calls core `/sync/gmail/import`, which invokes Email MCP HTTP tools and stores results in canonical emails.
          </p>
          <div style={{ display: "grid", gap: 10 }}>
            <input style={inputStyle} value={gmailAccountId} onChange={(e) => setGmailAccountId(e.target.value)} placeholder="Gmail account_id" required />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <input style={inputStyle} value={gmailWindowDays} onChange={(e) => setGmailWindowDays(e.target.value)} placeholder="window days" />
              <input style={inputStyle} value={gmailMaxMessages} onChange={(e) => setGmailMaxMessages(e.target.value)} placeholder="max messages" />
            </div>
            <label style={{ display: "flex", gap: 8, alignItems: "center", color: "#35514d", fontSize: 14 }}>
              <input type="checkbox" checked={gmailIncludeAttachments} onChange={(e) => setGmailIncludeAttachments(e.target.checked)} />
              Extract PDF/DOCX/CSV/XLSX attachment text
            </label>
            <button type="submit" style={buttonStyle} disabled={busy}>Fetch Gmail Emails</button>
          </div>
        </form>

        <form onSubmit={sendWebhookSample} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 6. Inbound Webhook Test</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>Sends a signed sample inbound email to MCP then into `sync:events`.</p>
          <div style={{ display: "grid", gap: 10 }}>
            <input style={inputStyle} value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} placeholder="INBOUND_EMAIL_WEBHOOK_SECRET" required />
            <button type="submit" style={buttonStyle} disabled={busy}>Send MCP Webhook Sample</button>
          </div>
        </form>
      </section>

      <section style={{ marginTop: 16, ...sectionStyle }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Step 7. Operations</h2>
          <button type="button" style={buttonStyle} onClick={() => Promise.all([refreshJobs(), refreshEmails(), refreshGmailAccounts()])} disabled={busy}>
            Refresh Jobs + Emails
          </button>
        </div>

        {gmailAccounts.length > 0 && (
          <>
            <h3>Gmail OAuth Accounts</h3>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #d9e4e2", textAlign: "left" }}>
                    <th style={{ padding: "8px 6px" }}>Account ID</th>
                    <th style={{ padding: "8px 6px" }}>Email</th>
                    <th style={{ padding: "8px 6px" }}>Status</th>
                    <th style={{ padding: "8px 6px" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {gmailAccounts.map((acc) => (
                    <tr key={acc.id} style={{ borderBottom: "1px solid #edf3f2" }}>
                      <td style={{ padding: "8px 6px", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}>{acc.account_id}</td>
                      <td style={{ padding: "8px 6px" }}>{acc.email || "n/a"}</td>
                      <td style={{ padding: "8px 6px" }}>{acc.status}</td>
                      <td style={{ padding: "8px 6px" }}>
                        <button type="button" style={{ ...buttonStyle, background: "#8d2b2b" }} onClick={() => deactivateGmailAccount(acc.account_id)} disabled={busy}>
                          Deactivate
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <h3>Jobs</h3>
        {latestJobs.length === 0 ? (
          <p>No jobs available.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #d9e4e2", textAlign: "left" }}>
                  <th style={{ padding: "8px 6px" }}>ID</th>
                  <th style={{ padding: "8px 6px" }}>Connector</th>
                  <th style={{ padding: "8px 6px" }}>Type</th>
                  <th style={{ padding: "8px 6px" }}>Status</th>
                  <th style={{ padding: "8px 6px" }}>Attempts</th>
                  <th style={{ padding: "8px 6px" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {latestJobs.map((job) => (
                  <tr key={job.id} style={{ borderBottom: "1px solid #edf3f2" }}>
                    <td style={{ padding: "8px 6px", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}>{job.id.slice(0, 8)}</td>
                    <td style={{ padding: "8px 6px" }}>{job.connector}</td>
                    <td style={{ padding: "8px 6px" }}>{job.job_type}</td>
                    <td style={{ padding: "8px 6px" }}>{job.status}</td>
                    <td style={{ padding: "8px 6px" }}>{job.attempts}</td>
                    <td style={{ padding: "8px 6px", display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {(job.status === "failed" || job.status === "deadletter") && (
                        <button type="button" style={buttonStyle} onClick={() => retryJob(job.id)} disabled={busy}>Retry</button>
                      )}
                      {(job.status === "queued" || job.status === "running" || job.status === "failed") && (
                        <button type="button" style={{ ...buttonStyle, background: "#8d2b2b" }} onClick={() => deadletterJob(job.id)} disabled={busy}>Dead-letter</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <h3 style={{ marginTop: 18 }}>Emails</h3>
        {emails.length === 0 ? (
          <p>No synced emails yet.</p>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {emails.slice(0, 20).map((email) => (
              <article key={email.id} style={{ border: "1px solid #d7e3e1", borderRadius: 12, padding: 10, background: "#f8fbfa" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                  <strong>{email.subject || "(no subject)"}</strong>
                  <StatusPill text={email.status} tone={email.status === "received" ? "good" : "neutral"} />
                </div>
                <p style={{ margin: "6px 0", color: "#2f4b47" }}>From: {email.from_address || "n/a"} | To: {email.to_address || "n/a"}</p>
                <p style={{ margin: 0, fontSize: 12, color: "#54716c" }}>Source: {email.source} | Received: {email.received_at}</p>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
