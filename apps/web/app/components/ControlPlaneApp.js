"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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

function renderEmailStatusLabel(email) {
  if (email.imported) {
    return "Imported";
  }
  const raw = String(email.status || "").trim();
  if (raw === "?") {
    return "Not Invoice";
  }
  return raw || "received";
}

export default function ControlPlaneApp({ initialHealth, initialJobs, initialConfig = {} }) {
  const [currentUser, setCurrentUser] = useState(initialConfig.currentUser || initialConfig.tenantSlug || "ui-user");
  const [tenantName, setTenantName] = useState(initialConfig.tenantName || "Acme Operations");
  const [tenantSlug, setTenantSlug] = useState(initialConfig.tenantSlug || "acme");
  const [tenantId, setTenantId] = useState(initialConfig.tenantId || "");

  const [odooBaseUrl, setOdooBaseUrl] = useState(initialConfig.odooBaseUrl || "https://odoo.example.com");
  const [odooDatabase, setOdooDatabase] = useState(initialConfig.odooDatabase || "prod_db");
  const [odooUsername, setOdooUsername] = useState(initialConfig.odooUsername || "admin@example.com");
  const [odooPassword, setOdooPassword] = useState("");
  const [odooConnStatus, setOdooConnStatus] = useState("unknown");
  const [odooConnMessage, setOdooConnMessage] = useState("");

  const [targetAddress, setTargetAddress] = useState("support@example.com");
  const [selectedFromAddresses, setSelectedFromAddresses] = useState([]);
  const [emailSubjectFilter, setEmailSubjectFilter] = useState("");
  const [emailHasAttachmentsFilter, setEmailHasAttachmentsFilter] = useState("any");
  const [emailFilterLogic, setEmailFilterLogic] = useState("and");
  const [sinceCursor, setSinceCursor] = useState("2026-03-01 00:00:00");
  const [webhookSecret, setWebhookSecret] = useState("replace-me");
  const [billFilename, setBillFilename] = useState("");
  const [billPdfBase64, setBillPdfBase64] = useState("");
  const [billDebug, setBillDebug] = useState(null);
  const [odooVendors, setOdooVendors] = useState([]);
  const [odooVendorSearch, setOdooVendorSearch] = useState("");
  const [gmailAccountId, setGmailAccountId] = useState(initialConfig.gmailAccountId || "default");
  const [gmailEmail, setGmailEmail] = useState(initialConfig.gmailEmail || "");
  const [gmailClientId, setGmailClientId] = useState("");
  const [gmailClientSecret, setGmailClientSecret] = useState("");
  const [gmailRefreshToken, setGmailRefreshToken] = useState("");
  const [gmailAccessToken, setGmailAccessToken] = useState("");
  const [gmailAccounts, setGmailAccounts] = useState([]);
  const [gmailWindowDays, setGmailWindowDays] = useState("7");
  const [gmailMaxMessages, setGmailMaxMessages] = useState("20");
  const [gmailIncludeAttachments, setGmailIncludeAttachments] = useState(true);
  const [batchRuns, setBatchRuns] = useState("3");
  const [recurringEnabled, setRecurringEnabled] = useState(false);
  const [recurringJobSaved, setRecurringJobSaved] = useState(false);
  const [recurringScheduleType, setRecurringScheduleType] = useState("interval");
  const [recurringIntervalValue, setRecurringIntervalValue] = useState("10");
  const [recurringIntervalUnit, setRecurringIntervalUnit] = useState("minutes");
  const [recurringHour, setRecurringHour] = useState("9");
  const [recurringMinute, setRecurringMinute] = useState("0");
  const [recurringWeekday, setRecurringWeekday] = useState("1");
  const [recurringMonthDay, setRecurringMonthDay] = useState("1");
  const [recurringNextRunAt, setRecurringNextRunAt] = useState("");
  const [recurringLastRunAt, setRecurringLastRunAt] = useState("");
  const [recurringLastRunStatus, setRecurringLastRunStatus] = useState("");
  const [recurringLastRunMessage, setRecurringLastRunMessage] = useState("");
  const [autoSelectFilteredAfterRead, setAutoSelectFilteredAfterRead] = useState(true);
  const [gmailAccessStatus, setGmailAccessStatus] = useState("idle");
  const [gmailAccessMessage, setGmailAccessMessage] = useState("");
  const [llmInfo, setLlmInfo] = useState({ provider: "unknown", model: "unknown", configured: false, status: "unknown" });

  const [health, setHealth] = useState(initialHealth || { ok: false, service: "unknown" });
  const [jobs, setJobs] = useState(Array.isArray(initialJobs) ? initialJobs : []);
  const [emails, setEmails] = useState([]);
  const [selectedEmailIds, setSelectedEmailIds] = useState([]);
  const [emailBillPreview, setEmailBillPreview] = useState(null);
  const [showEmailBillPreviewModal, setShowEmailBillPreviewModal] = useState(false);
  const [previewEditsByEmailId, setPreviewEditsByEmailId] = useState({});
  const [previewOriginalByEmailId, setPreviewOriginalByEmailId] = useState({});
  const [previewImportResultByEmailId, setPreviewImportResultByEmailId] = useState({});
  const [emailBillImportDebug, setEmailBillImportDebug] = useState(null);
  const [debugImportEnabled, setDebugImportEnabled] = useState(false);
  const [auditLogs, setAuditLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const recurringInProgressRef = useRef(false);

  const latestJobs = useMemo(() => jobs.slice(0, 20), [jobs]);
  const senderOptions = useMemo(() => {
    const unique = new Set(
      emails
        .map((email) => String(email.from_address || "").trim())
        .filter(Boolean)
    );
    return Array.from(unique).sort((a, b) => a.localeCompare(b));
  }, [emails]);
  const filteredEmails = useMemo(() => {
    const isOr = String(emailFilterLogic).toLowerCase() === "or";
    const normalizedSelected = selectedFromAddresses.map((value) => value.toLowerCase());
    const normalizedSubject = emailSubjectFilter.trim().toLowerCase();

    return emails
      .filter((email) => {
        const checks = [];
        if (normalizedSelected.length > 0) {
          checks.push(normalizedSelected.includes(String(email.from_address || "").toLowerCase()));
        }
        if (normalizedSubject) {
          checks.push(String(email.subject || "").toLowerCase().includes(normalizedSubject));
        }
        if (emailHasAttachmentsFilter === "yes") {
          checks.push(Boolean(email.has_attachments));
        } else if (emailHasAttachmentsFilter === "no") {
          checks.push(!email.has_attachments);
        }

        if (checks.length === 0) {
          return true;
        }
        return isOr ? checks.some(Boolean) : checks.every(Boolean);
      })
      .sort((a, b) => {
        const aTime = Date.parse(a.received_at || a.created_at || "") || 0;
        const bTime = Date.parse(b.received_at || b.created_at || "") || 0;
        return bTime - aTime;
      });
  }, [emails, selectedFromAddresses, emailSubjectFilter, emailHasAttachmentsFilter, emailFilterLogic]);
  const storageKey = "odoo-adapter-control-plane-v1";
  const gmailFilterWarning = useMemo(() => {
    const target = targetAddress.trim().toLowerCase();
    const mailbox = gmailEmail.trim().toLowerCase();
    if (!target || !mailbox) {
      return "";
    }
    if (target === mailbox || target.includes(mailbox) || mailbox.includes(target)) {
      return "";
    }
    return `Gmail fetch is filtered to "${targetAddress}". Saved Gmail mailbox is "${gmailEmail}", so Step 5 may return 0 emails.`;
  }, [targetAddress, gmailEmail]);

  function resetFeedback() {
    setError("");
    setNotice("");
  }

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (!raw) {
        return;
      }
      const saved = JSON.parse(raw);
      if (saved && typeof saved === "object") {
        if (typeof saved.tenantName === "string") setTenantName(saved.tenantName);
        if (typeof saved.tenantSlug === "string") setTenantSlug(saved.tenantSlug);
        if (typeof saved.tenantId === "string") setTenantId(saved.tenantId);
        if (typeof saved.currentUser === "string") setCurrentUser(saved.currentUser);
        if (typeof saved.odooBaseUrl === "string") setOdooBaseUrl(saved.odooBaseUrl);
        if (typeof saved.odooDatabase === "string") setOdooDatabase(saved.odooDatabase);
        if (typeof saved.odooUsername === "string") setOdooUsername(saved.odooUsername);
        if (typeof saved.targetAddress === "string") setTargetAddress(saved.targetAddress);
        if (Array.isArray(saved.selectedFromAddresses)) setSelectedFromAddresses(saved.selectedFromAddresses.filter((value) => typeof value === "string"));
        if (typeof saved.emailSubjectFilter === "string") setEmailSubjectFilter(saved.emailSubjectFilter);
        if (typeof saved.emailHasAttachmentsFilter === "string") setEmailHasAttachmentsFilter(saved.emailHasAttachmentsFilter);
        if (typeof saved.emailFilterLogic === "string") setEmailFilterLogic(saved.emailFilterLogic);
        if (typeof saved.sinceCursor === "string") setSinceCursor(saved.sinceCursor);
        if (typeof saved.webhookSecret === "string") setWebhookSecret(saved.webhookSecret);
        if (typeof saved.gmailAccountId === "string") setGmailAccountId(saved.gmailAccountId);
        if (typeof saved.gmailEmail === "string") setGmailEmail(saved.gmailEmail);
        if (typeof saved.gmailClientId === "string") setGmailClientId(saved.gmailClientId);
        if (typeof saved.gmailClientSecret === "string") setGmailClientSecret(saved.gmailClientSecret);
        if (typeof saved.gmailRefreshToken === "string") setGmailRefreshToken(saved.gmailRefreshToken);
        if (typeof saved.gmailAccessToken === "string") setGmailAccessToken(saved.gmailAccessToken);
        if (typeof saved.gmailWindowDays === "string") setGmailWindowDays(saved.gmailWindowDays);
        if (typeof saved.gmailMaxMessages === "string") setGmailMaxMessages(saved.gmailMaxMessages);
        if (typeof saved.gmailIncludeAttachments === "boolean") setGmailIncludeAttachments(saved.gmailIncludeAttachments);
        if (typeof saved.batchRuns === "string") setBatchRuns(saved.batchRuns);
        if (typeof saved.recurringEnabled === "boolean") setRecurringEnabled(saved.recurringEnabled);
        if (typeof saved.recurringJobSaved === "boolean") setRecurringJobSaved(saved.recurringJobSaved);
        if (typeof saved.recurringScheduleType === "string") setRecurringScheduleType(saved.recurringScheduleType);
        if (typeof saved.recurringIntervalValue === "string") setRecurringIntervalValue(saved.recurringIntervalValue);
        if (typeof saved.recurringIntervalUnit === "string") setRecurringIntervalUnit(saved.recurringIntervalUnit);
        if (typeof saved.recurringHour === "string") setRecurringHour(saved.recurringHour);
        if (typeof saved.recurringMinute === "string") setRecurringMinute(saved.recurringMinute);
        if (typeof saved.recurringWeekday === "string") setRecurringWeekday(saved.recurringWeekday);
        if (typeof saved.recurringMonthDay === "string") setRecurringMonthDay(saved.recurringMonthDay);
        if (typeof saved.recurringNextRunAt === "string") setRecurringNextRunAt(saved.recurringNextRunAt);
        if (typeof saved.recurringLastRunAt === "string") setRecurringLastRunAt(saved.recurringLastRunAt);
        if (typeof saved.recurringLastRunStatus === "string") setRecurringLastRunStatus(saved.recurringLastRunStatus);
        if (typeof saved.recurringLastRunMessage === "string") setRecurringLastRunMessage(saved.recurringLastRunMessage);
        if (typeof saved.recurringEveryMinutes === "string" && !saved.recurringIntervalValue) {
          setRecurringScheduleType("interval");
          setRecurringIntervalValue(saved.recurringEveryMinutes);
          setRecurringIntervalUnit("minutes");
        }
        if (typeof saved.autoSelectFilteredAfterRead === "boolean") setAutoSelectFilteredAfterRead(saved.autoSelectFilteredAfterRead);
      }
    } catch {
      // Ignore local parsing errors and continue with server-provided defaults.
    }
  }, [storageKey]);

  useEffect(() => {
      const payload = {
      tenantName,
      tenantSlug,
      tenantId,
      currentUser,
      odooBaseUrl,
      odooDatabase,
      odooUsername,
      targetAddress,
      selectedFromAddresses,
      emailSubjectFilter,
      emailHasAttachmentsFilter,
      emailFilterLogic,
      sinceCursor,
      webhookSecret,
      gmailAccountId,
      gmailEmail,
      gmailClientId,
      gmailClientSecret,
      gmailRefreshToken,
      gmailAccessToken,
      gmailWindowDays,
      gmailMaxMessages,
      gmailIncludeAttachments,
      batchRuns,
      recurringEnabled,
      recurringJobSaved,
      recurringScheduleType,
      recurringIntervalValue,
      recurringIntervalUnit,
      recurringHour,
      recurringMinute,
      recurringWeekday,
      recurringMonthDay,
      recurringNextRunAt,
      recurringLastRunAt,
      recurringLastRunStatus,
      recurringLastRunMessage,
      autoSelectFilteredAfterRead
    };
    window.localStorage.setItem(storageKey, JSON.stringify(payload));
  }, [
    storageKey,
    tenantName,
    tenantSlug,
    tenantId,
    currentUser,
    odooBaseUrl,
    odooDatabase,
    odooUsername,
    targetAddress,
    selectedFromAddresses,
    emailSubjectFilter,
    emailHasAttachmentsFilter,
    emailFilterLogic,
    sinceCursor,
    webhookSecret,
    gmailAccountId,
    gmailEmail,
    gmailClientId,
    gmailClientSecret,
    gmailRefreshToken,
    gmailAccessToken,
    gmailWindowDays,
    gmailMaxMessages,
    gmailIncludeAttachments,
    batchRuns,
    recurringEnabled,
    recurringJobSaved,
    recurringScheduleType,
    recurringIntervalValue,
    recurringIntervalUnit,
    recurringHour,
    recurringMinute,
    recurringWeekday,
    recurringMonthDay,
    recurringNextRunAt,
    recurringLastRunAt,
    recurringLastRunStatus,
    recurringLastRunMessage,
    autoSelectFilteredAfterRead
  ]);

  useEffect(() => {
    if (!Array.isArray(gmailAccounts) || gmailAccounts.length === 0) {
      return;
    }
    const selected = gmailAccounts.find((acc) => acc.account_id === gmailAccountId) || gmailAccounts[0];
    if (selected?.email) {
      if (!gmailEmail.trim()) {
        setGmailEmail(selected.email);
      }
      if (!targetAddress.trim()) {
        setTargetAddress(selected.email);
      }
    }
  }, [gmailAccounts, gmailAccountId, gmailEmail, targetAddress]);

  useEffect(() => {
    if (gmailEmail.trim() && !targetAddress.trim()) {
      setTargetAddress(gmailEmail.trim());
    }
  }, [gmailEmail, targetAddress]);

  useEffect(() => {
    if (!tenantId) {
      return;
    }
    Promise.all([refreshJobs(), refreshEmails(), refreshGmailAccounts(), refreshOdooConnectionState(), refreshAuditLogs()]).catch(() => {
      // Errors are already handled by individual refresh methods.
    });
  }, [tenantId]);

  async function refreshHealth() {
    try {
      const data = await apiFetch("/api/core/health", { method: "GET" });
      setHealth(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshLlmInfo() {
    try {
      const data = await apiFetch("/api/core/system/llm", { method: "GET" });
      setLlmInfo({
        provider: String(data?.provider || "unknown"),
        model: String(data?.model || "unknown"),
        configured: Boolean(data?.configured),
        status: String(data?.status || "unknown")
      });
    } catch {
      setLlmInfo({ provider: "unknown", model: "unknown", configured: false, status: "unreachable" });
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

  async function refreshOdooConnectionState() {
    if (!tenantId) {
      setOdooConnStatus("unknown");
      setOdooConnMessage("");
      return;
    }
    try {
      const data = await apiFetch(
        `/api/core/connections?tenant_id=${encodeURIComponent(tenantId)}&connector=odoo&limit=1`,
        { method: "GET" }
      );
      const row = Array.isArray(data) && data.length > 0 ? data[0] : null;
      if (row?.id) {
        setOdooConnStatus("connected");
        setOdooConnMessage(`Active Odoo connection found: ${row.id}`);
      } else {
        setOdooConnStatus("unknown");
        setOdooConnMessage("No active Odoo connection found for this tenant.");
      }
    } catch (err) {
      setOdooConnStatus("failed");
      setOdooConnMessage(err.message);
    }
  }

  async function refreshEmails() {
    if (!tenantId) {
      return;
    }
    try {
      const query = new URLSearchParams({ tenant_id: tenantId, limit: "200" });
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

  async function refreshAuditLogs() {
    if (!tenantId) {
      return;
    }
    try {
      const query = new URLSearchParams({ tenant_id: tenantId, limit: "100" });
      const data = await apiFetch(`/api/core/audit/logs?${query.toString()}`, { method: "GET" });
      setAuditLogs(Array.isArray(data) ? data : []);
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
            username: odooUsername,
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

  const runGmailReadOnce = useCallback(
    async ({ forceAttachments = false } = {}) => {
      const includeAttachments = forceAttachments ? true : gmailIncludeAttachments;
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
          include_attachments: includeAttachments,
          extract_attachment_text: includeAttachments
        })
      });
      await Promise.all([refreshEmails(), refreshJobs()]);
      if (autoSelectFilteredAfterRead) {
        setSelectedEmailIds(filteredEmails.slice(0, 20).map((email) => email.id));
      }
      return result;
    },
    [
      gmailIncludeAttachments,
      tenantId,
      gmailAccountId,
      gmailWindowDays,
      gmailMaxMessages,
      targetAddress,
      autoSelectFilteredAfterRead,
      filteredEmails
    ]
  );

  async function triggerGmailFetch(event) {
    event.preventDefault();
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    setBusy(true);
    try {
      const result = await runGmailReadOnce({ forceAttachments: false });
      setNotice(
        `Gmail import complete: imported=${result.imported_count}, fetched=${result.fetched_count}, attachments=${result.attachments_processed}`
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const runScheduledBatch = useCallback(async (runs) => {
    let totalImported = 0;
    let totalFetched = 0;
    let totalAttachments = 0;
    for (let i = 0; i < runs; i += 1) {
      const result = await runGmailReadOnce({ forceAttachments: true });
      totalImported += Number(result.imported_count || 0);
      totalFetched += Number(result.fetched_count || 0);
      totalAttachments += Number(result.attachments_processed || 0);
    }
    return { totalImported, totalFetched, totalAttachments };
  }, [runGmailReadOnce]);

  const computeNextRecurringRun = useCallback(
    (from = new Date()) => {
      const now = new Date(from);
      const hour = Math.max(0, Math.min(23, Number(recurringHour || 0)));
      const minute = Math.max(0, Math.min(59, Number(recurringMinute || 0)));

      if (recurringScheduleType === "interval") {
        const value = Math.max(1, Number(recurringIntervalValue || 1));
        const unit = String(recurringIntervalUnit || "minutes");
        const msMap = {
          minutes: 60 * 1000,
          hours: 60 * 60 * 1000,
          days: 24 * 60 * 60 * 1000,
          weeks: 7 * 24 * 60 * 60 * 1000
        };
        const intervalMs = value * (msMap[unit] || msMap.minutes);
        return new Date(now.getTime() + intervalMs);
      }

      if (recurringScheduleType === "daily") {
        const next = new Date(now);
        next.setHours(hour, minute, 0, 0);
        if (next <= now) {
          next.setDate(next.getDate() + 1);
        }
        return next;
      }

      if (recurringScheduleType === "weekly") {
        const targetWeekday = Math.max(0, Math.min(6, Number(recurringWeekday || 0)));
        const next = new Date(now);
        next.setHours(hour, minute, 0, 0);
        const dayDelta = (targetWeekday - next.getDay() + 7) % 7;
        next.setDate(next.getDate() + dayDelta);
        if (next <= now) {
          next.setDate(next.getDate() + 7);
        }
        return next;
      }

      const targetMonthDay = Math.max(1, Math.min(31, Number(recurringMonthDay || 1)));
      const year = now.getFullYear();
      const month = now.getMonth();
      const thisMonthMax = new Date(year, month + 1, 0).getDate();
      const dayThisMonth = Math.min(targetMonthDay, thisMonthMax);
      const candidate = new Date(year, month, dayThisMonth, hour, minute, 0, 0);
      if (candidate > now) {
        return candidate;
      }
      const nextMonthDate = new Date(year, month + 1, 1, hour, minute, 0, 0);
      const nextYear = nextMonthDate.getFullYear();
      const nextMonth = nextMonthDate.getMonth();
      const nextMonthMax = new Date(nextYear, nextMonth + 1, 0).getDate();
      const nextDay = Math.min(targetMonthDay, nextMonthMax);
      return new Date(nextYear, nextMonth, nextDay, hour, minute, 0, 0);
    },
    [recurringScheduleType, recurringIntervalValue, recurringIntervalUnit, recurringHour, recurringMinute, recurringWeekday, recurringMonthDay]
  );

  const isRecurringConfigValid = useMemo(() => {
    if (recurringScheduleType === "interval") {
      return Number(recurringIntervalValue || 0) > 0;
    }
    return Number(recurringHour) >= 0 && Number(recurringHour) <= 23 && Number(recurringMinute) >= 0 && Number(recurringMinute) <= 59;
  }, [recurringScheduleType, recurringIntervalValue, recurringHour, recurringMinute]);

  function saveRecurringBatchJob(event) {
    event.preventDefault();
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    if (!isRecurringConfigValid) {
      setError("Recurring schedule is invalid.");
      return;
    }
    const next = computeNextRecurringRun(new Date());
    setRecurringEnabled(true);
    setRecurringJobSaved(true);
    setRecurringNextRunAt(next.toISOString());
    setNotice("Recurring batch email read job saved.");
  }

  function cancelRecurringBatchJob() {
    resetFeedback();
    setRecurringEnabled(false);
    setRecurringJobSaved(false);
    setRecurringNextRunAt("");
    setRecurringLastRunStatus("");
    setRecurringLastRunMessage("");
    setNotice("Recurring batch email read job canceled.");
  }

  useEffect(() => {
    if (!recurringEnabled || !recurringJobSaved) {
      return;
    }
    const next = computeNextRecurringRun(new Date());
    setRecurringNextRunAt(next.toISOString());
  }, [recurringEnabled, recurringJobSaved, recurringScheduleType, recurringIntervalValue, recurringIntervalUnit, recurringHour, recurringMinute, recurringWeekday, recurringMonthDay, computeNextRecurringRun]);

  useEffect(() => {
    if (!recurringJobSaved && recurringEnabled) {
      setRecurringEnabled(false);
    }
  }, [recurringJobSaved, recurringEnabled]);

  useEffect(() => {
    if (!recurringEnabled || !recurringJobSaved || !recurringNextRunAt) {
      return undefined;
    }
    const timer = window.setInterval(async () => {
      if (recurringInProgressRef.current || busy || !tenantId) {
        return;
      }
      const dueAt = new Date(recurringNextRunAt);
      if (Number.isNaN(dueAt.getTime())) {
        return;
      }
      if (new Date() < dueAt) {
        return;
      }
      recurringInProgressRef.current = true;
      const startedAt = new Date();
      try {
        const runs = Math.max(1, Math.min(50, Number(batchRuns || 1)));
        const result = await runScheduledBatch(runs);
        setNotice(
          `Recurring email read complete: runs=${runs}, imported=${result.totalImported}, fetched=${result.totalFetched}, attachments=${result.totalAttachments}`
        );
        setRecurringLastRunAt(startedAt.toISOString());
        setRecurringLastRunStatus("success");
        setRecurringLastRunMessage(`runs=${runs}, imported=${result.totalImported}, fetched=${result.totalFetched}, attachments=${result.totalAttachments}`);
      } catch (err) {
        setError(err.message);
        setRecurringLastRunAt(startedAt.toISOString());
        setRecurringLastRunStatus("error");
        setRecurringLastRunMessage(err.message);
      } finally {
        const next = computeNextRecurringRun(new Date());
        setRecurringNextRunAt(next.toISOString());
        recurringInProgressRef.current = false;
      }
    }, 15 * 1000);
    return () => window.clearInterval(timer);
  }, [recurringEnabled, recurringJobSaved, recurringNextRunAt, busy, tenantId, batchRuns, runScheduledBatch, computeNextRecurringRun]);

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
      setGmailAccessStatus("captured");
      setGmailAccessMessage(`Gmail OAuth account saved for ${result.account_id}. Verifying Gmail access...`);
      const verified = await apiFetch("/api/core/gmail/accounts/test", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          account_id: result.account_id
        })
      });
      setGmailAccessStatus("connected");
      setGmailAccessMessage(
        verified?.email
          ? `${verified.message} (${verified.email})`
          : (verified?.message || `Gmail access is active for account: ${result.account_id}`)
      );
      setNotice(`Gmail OAuth saved and verified: ${result.account_id}`);
      await refreshGmailAccounts();
    } catch (err) {
      setGmailAccessStatus("failed");
      setGmailAccessMessage(err.message);
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function testSavedGmailAuth() {
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    if (!gmailAccountId.trim()) {
      setError("Gmail account_id is required.");
      return;
    }
    setBusy(true);
    try {
      const verified = await apiFetch("/api/core/gmail/accounts/test", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          account_id: gmailAccountId.trim()
        })
      });
      setGmailAccessStatus("connected");
      setGmailAccessMessage(
        verified?.email
          ? `${verified.message} (${verified.email})`
          : (verified?.message || `Gmail access is active for account: ${gmailAccountId.trim()}`)
      );
      setNotice(`Gmail auth test successful for ${gmailAccountId.trim()}`);
    } catch (err) {
      setGmailAccessStatus("failed");
      setGmailAccessMessage(err.message);
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

  function onBillPdfSelected(event) {
    const file = event.target.files?.[0];
    if (!file) {
      setBillPdfBase64("");
      setBillFilename("");
      return;
    }
    setBillFilename(file.name || "invoice.pdf");
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      const raw = value.includes(",") ? value.split(",", 2)[1] : value;
      setBillPdfBase64(raw);
    };
    reader.readAsDataURL(file);
  }

  async function createOdooBillFromPdf(event) {
    event.preventDefault();
    resetFeedback();
    setBillDebug(null);
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    if (!billPdfBase64) {
      setError("Select a PDF file first.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/sync/odoo/bills/from-pdf", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          pdf_base64: billPdfBase64,
          filename: billFilename || "invoice.pdf"
        })
      });
      setBillDebug(result);
      setNotice(`Odoo bill created: bill_id=${result.bill_id}, attachment_id=${result.attachment_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function importSelectedEmailsToOdooBills() {
    return importEmailIdsToOdooBills(selectedEmailIds);
  }

  async function importEmailIdsToOdooBills(emailIds) {
    resetFeedback();
    setEmailBillImportDebug(null);
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    if (!Array.isArray(emailIds) || emailIds.length === 0) {
      setError("Select at least one email first.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/sync/odoo/bills/from-emails", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          email_ids: emailIds,
          actor: currentUser || "ui-user",
        })
      });
      setEmailBillImportDebug(result);
      setNotice(`Email->Odoo import complete: created=${result.created}, processed=${result.processed}`);
      setSelectedEmailIds([]);
      await Promise.all([refreshJobs(), refreshAuditLogs()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function previewSelectedEmailsForOdooBills() {
    resetFeedback();
    setEmailBillPreview(null);
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    if (selectedEmailIds.length === 0) {
      setError("Select at least one email first.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/sync/odoo/bills/preview-from-emails", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          email_ids: selectedEmailIds,
          actor: currentUser || "ui-user",
        })
      });
      setEmailBillPreview(result);
      const sourceItems = Array.isArray(result.items) ? result.items : [];
      const edits = {};
      const original = {};
      for (const item of sourceItems) {
        const extracted = item?.extracted && typeof item.extracted === "object" ? item.extracted : {};
        edits[item.email_id] = { ...extracted };
        original[item.email_id] = { ...extracted };
      }
      setPreviewEditsByEmailId(edits);
      setPreviewOriginalByEmailId(original);
      setPreviewImportResultByEmailId({});
      setShowEmailBillPreviewModal(true);
      setNotice(`Preview ready: ${result.ready}/${result.processed} email(s) are ready for import.`);
      await refreshAuditLogs();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function previewSingleEmailForOdooBill(emailId) {
    resetFeedback();
    if (!tenantId || !emailId) {
      setError("Tenant and email are required.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/sync/odoo/bills/preview-from-emails", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          email_ids: [emailId],
          actor: currentUser || "ui-user",
        }),
      });
      const edits = {};
      for (const item of (Array.isArray(result.items) ? result.items : [])) {
        edits[item.email_id] = { ...(item.extracted || {}) };
      }
      setEmailBillPreview(result);
      setPreviewEditsByEmailId(edits);
      setPreviewOriginalByEmailId(edits);
      setPreviewImportResultByEmailId({});
      setSelectedEmailIds([emailId]);
      setShowEmailBillPreviewModal(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function onPreviewFieldChanged(emailId, field, value) {
    setPreviewEditsByEmailId((prev) => ({
      ...prev,
      [emailId]: {
        ...(prev[emailId] || {}),
        [field]: value,
      },
    }));
  }

  async function savePreviewEditsAudit() {
    if (!tenantId || !emailBillPreview) {
      return;
    }
    const items = Array.isArray(emailBillPreview.items) ? emailBillPreview.items : [];
    const updates = [];
    for (const item of items) {
      const emailId = item.email_id;
      const before = previewOriginalByEmailId[emailId] || {};
      const after = previewEditsByEmailId[emailId] || {};
      const changed = {};
      for (const key of Object.keys(after)) {
        const beforeValue = before[key] ?? null;
        const afterValue = after[key] ?? null;
        if (String(beforeValue) !== String(afterValue)) {
          changed[key] = { before: beforeValue, after: afterValue };
        }
      }
      if (Object.keys(changed).length > 0) {
        updates.push({ email_id: emailId, changed_fields: changed });
      }
    }
    if (updates.length === 0) {
      setNotice("No field edits to save.");
      return;
    }
    await apiFetch("/api/core/audit/logs", {
      method: "POST",
      body: JSON.stringify({
        tenant_id: tenantId,
        action: "bill_preview_update",
        actor: currentUser || "ui-user",
        entity_type: "email_bill_preview",
        entity_id: updates.map((entry) => entry.email_id).join(","),
        details: { updated_fields: updates },
      }),
    });
    setPreviewOriginalByEmailId((prev) => ({ ...prev, ...previewEditsByEmailId }));
    setNotice(`Saved ${updates.length} preview update audit record(s).`);
    await refreshAuditLogs();
  }

  async function importEditedPreviewBillsToOdoo() {
    resetFeedback();
    if (!tenantId || !emailBillPreview) {
      setError("Preview data is missing.");
      return;
    }
    const previewItems = Array.isArray(emailBillPreview.items) ? emailBillPreview.items : [];
    const importItems = previewItems
      .filter((item) => item.status === "ready")
      .map((item) => {
        const edited = previewEditsByEmailId[item.email_id] || item.extracted || {};
        return {
          email_id: item.email_id,
          extracted: {
            vendor: edited.vendor || "",
            bill_reference: edited.bill_reference || "",
            bill_date: edited.bill_date || "",
            invoice_date: edited.invoice_date || "",
            product: edited.product || "",
            accounting_date: edited.accounting_date || "",
            account_id: edited.account_id || "",
            vat_percent: edited.vat_percent || "",
            billing_id: edited.billing_id || "",
            currency: edited.currency || "",
            discount: edited.discount || "",
            payment_reference: edited.payment_reference || "",
            recipient_bank: edited.recipient_bank || "",
            price: edited.price === "" || edited.price == null ? null : Number(edited.price),
            tax: edited.tax || "",
            amount: edited.amount === "" || edited.amount == null ? null : Number(edited.amount),
            due_date: edited.due_date || "",
          },
        };
      });
    if (importItems.length === 0) {
      setError("No preview-ready bills to import.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiFetch("/api/core/sync/odoo/bills/import-from-preview", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: tenantId,
          actor: currentUser || "ui-user",
          items: importItems,
        }),
      });
      const statusMap = {};
      for (const item of (Array.isArray(result.items) ? result.items : [])) {
        statusMap[item.email_id] = item;
      }
      setPreviewImportResultByEmailId(statusMap);
      setEmailBillImportDebug(result);
      setNotice(`Preview import complete: created=${result.created}, processed=${result.processed}`);
      setSelectedEmailIds([]);
      await Promise.all([refreshJobs(), refreshAuditLogs()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadOdooVendors() {
    resetFeedback();
    if (!tenantId) {
      setError("Tenant ID is required.");
      return;
    }
    setBusy(true);
    try {
      const params = new URLSearchParams({
        tenant_id: tenantId,
        limit: "200",
      });
      if (odooVendorSearch.trim()) {
        params.set("search", odooVendorSearch.trim());
      }
      const rows = await apiFetch(`/api/core/odoo/vendors?${params.toString()}`, { method: "GET" });
      setOdooVendors(Array.isArray(rows) ? rows : []);
      setNotice(`Loaded ${Array.isArray(rows) ? rows.length : 0} Odoo vendor(s).`);
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

  useEffect(() => {
    const isCaptured = Boolean(
      gmailAccountId.trim() &&
        gmailClientId.trim() &&
        gmailClientSecret.trim() &&
        gmailRefreshToken.trim()
    );
    if (!isCaptured) {
      if (gmailAccessStatus !== "connected") {
        setGmailAccessStatus("idle");
        setGmailAccessMessage("");
      }
      return;
    }
    if (gmailAccessStatus !== "connected") {
      setGmailAccessStatus("captured");
      setGmailAccessMessage("Gmail OAuth data captured in UI. Click Save Gmail OAuth to persist it.");
    }
  }, [
    gmailAccountId,
    gmailClientId,
    gmailClientSecret,
    gmailRefreshToken,
    gmailAccessStatus
  ]);

  async function refreshAll() {
    resetFeedback();
    setBusy(true);
    try {
      await Promise.all([refreshHealth(), refreshLlmInfo(), refreshJobs(), refreshEmails(), refreshGmailAccounts(), refreshOdooConnectionState(), refreshAuditLogs()]);
      setNotice("Data refreshed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshLlmInfo();
  }, []);

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
            <StatusPill
              text={`LLM: ${llmInfo.provider}/${llmInfo.model}`}
              tone={llmInfo.configured ? "good" : "bad"}
            />
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
              <button type="button" style={{ ...buttonStyle, background: "#2f556d" }} onClick={testSavedGmailAuth} disabled={busy}>
                Test Gmail Auth
              </button>
              <button type="button" style={{ ...buttonStyle, background: "#3a6f69" }} onClick={refreshGmailAccounts} disabled={busy}>Refresh Accounts</button>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <strong style={{ color: "#33514d" }}>Gmail access status:</strong>
              <StatusPill
                text={
                  gmailAccessStatus === "connected"
                    ? "Active"
                    : gmailAccessStatus === "failed"
                      ? "Failed"
                      : gmailAccessStatus === "captured"
                        ? "Captured (Not Saved)"
                        : "Not Ready"
                }
                tone={gmailAccessStatus === "connected" ? "good" : gmailAccessStatus === "failed" ? "bad" : "neutral"}
              />
            </div>
            {gmailAccessMessage && (
              <p style={{ margin: 0, color: gmailAccessStatus === "failed" ? "#9d1f1f" : "#35514d" }}>
                {gmailAccessMessage}
              </p>
            )}
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
            {gmailFilterWarning && (
              <p style={{ margin: 0, color: "#8e5a13", background: "#fff5e8", border: "1px solid #f1d2a9", borderRadius: 10, padding: "8px 10px" }}>
                {gmailFilterWarning}
              </p>
            )}
            <label style={{ display: "flex", gap: 8, alignItems: "center", color: "#35514d", fontSize: 14 }}>
              <input type="checkbox" checked={gmailIncludeAttachments} onChange={(e) => setGmailIncludeAttachments(e.target.checked)} />
              Extract PDF/DOCX/CSV/XLSX attachment text
            </label>
            <button type="submit" style={buttonStyle} disabled={busy}>Fetch Gmail Emails</button>
          </div>
        </form>

        <form onSubmit={saveRecurringBatchJob} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 7. Batch + Recurring Email Read</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>
            Runs Gmail email read in batch or on schedule using attachment extraction automatically, then refreshes the filtered email list.
          </p>
          <div style={{ display: "grid", gap: 10 }}>
            <input style={inputStyle} value={gmailAccountId} onChange={(e) => setGmailAccountId(e.target.value)} placeholder="Gmail account_id" required />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <input style={inputStyle} value={batchRuns} onChange={(e) => setBatchRuns(e.target.value)} placeholder="batch runs (e.g. 3)" />
              <select style={inputStyle} value={recurringScheduleType} onChange={(e) => setRecurringScheduleType(e.target.value)}>
                <option value="interval">Repeat Every (minutes/hours/days/weeks)</option>
                <option value="daily">Daily (at hour)</option>
                <option value="weekly">Weekly (at weekday + hour)</option>
                <option value="monthly">Monthly (at day + hour)</option>
              </select>
            </div>
            {recurringScheduleType === "interval" ? (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <input
                  style={inputStyle}
                  value={recurringIntervalValue}
                  onChange={(e) => setRecurringIntervalValue(e.target.value)}
                  placeholder="repeat every (e.g. 2)"
                />
                <select style={inputStyle} value={recurringIntervalUnit} onChange={(e) => setRecurringIntervalUnit(e.target.value)}>
                  <option value="minutes">minutes</option>
                  <option value="hours">hours</option>
                  <option value="days">days</option>
                  <option value="weeks">weeks</option>
                </select>
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <input style={inputStyle} value={recurringHour} onChange={(e) => setRecurringHour(e.target.value)} placeholder="hour (0-23)" />
                <input style={inputStyle} value={recurringMinute} onChange={(e) => setRecurringMinute(e.target.value)} placeholder="minute (0-59)" />
              </div>
            )}
            {recurringScheduleType === "weekly" && (
              <select style={inputStyle} value={recurringWeekday} onChange={(e) => setRecurringWeekday(e.target.value)}>
                <option value="0">Sunday</option>
                <option value="1">Monday</option>
                <option value="2">Tuesday</option>
                <option value="3">Wednesday</option>
                <option value="4">Thursday</option>
                <option value="5">Friday</option>
                <option value="6">Saturday</option>
              </select>
            )}
            {recurringScheduleType === "monthly" && (
              <input
                style={inputStyle}
                value={recurringMonthDay}
                onChange={(e) => setRecurringMonthDay(e.target.value)}
                placeholder="day of month (1-31)"
              />
            )}
            {recurringJobSaved && recurringNextRunAt && (
              <p style={{ margin: 0, fontSize: 12, color: "#35514d" }}>
                Next run: {new Date(recurringNextRunAt).toLocaleString()}
              </p>
            )}
            {recurringJobSaved && recurringLastRunAt && (
              <p style={{ margin: 0, fontSize: 12, color: recurringLastRunStatus === "error" ? "#9d1f1f" : "#35514d" }}>
                Last run: {new Date(recurringLastRunAt).toLocaleString()} ({recurringLastRunStatus || "unknown"})
                {recurringLastRunMessage ? ` | ${recurringLastRunMessage}` : ""}
              </p>
            )}
            <label style={{ display: "flex", gap: 8, alignItems: "center", color: "#35514d", fontSize: 14 }}>
              <input
                type="checkbox"
                checked={autoSelectFilteredAfterRead}
                onChange={(e) => setAutoSelectFilteredAfterRead(e.target.checked)}
              />
              Auto-select visible filtered emails after each run
            </label>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {isRecurringConfigValid && (
                <button type="submit" style={buttonStyle} disabled={busy}>
                  Save
                </button>
              )}
              {recurringJobSaved && (
                <button type="button" style={{ ...buttonStyle, background: "#8d2b2b" }} onClick={cancelRecurringBatchJob} disabled={busy}>
                  Cancel
                </button>
              )}
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "#54716c" }}>
              Uses current `Filter #1` settings in the UI view after each read. For attachment-focused runs, set `Attachments: Yes` in Filter #1.
            </p>
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

        <form onSubmit={createOdooBillFromPdf} style={sectionStyle}>
          <h2 style={{ marginTop: 0 }}>Step 8. Create Odoo Bill from PDF</h2>
          <p style={{ marginTop: 0, color: "#3a5551" }}>
            Upload only a PDF. OdooAdapter creates a draft vendor bill and attaches the PDF automatically.
          </p>
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <strong style={{ color: "#33514d" }}>Active Odoo connection:</strong>
              <StatusPill
                text={odooConnStatus === "connected" ? "Detected" : odooConnStatus === "failed" ? "Check Failed" : "Not Detected"}
                tone={odooConnStatus === "connected" ? "good" : odooConnStatus === "failed" ? "bad" : "neutral"}
              />
            </div>
            {odooConnMessage && (
              <p style={{ margin: 0, color: odooConnStatus === "failed" ? "#9d1f1f" : "#35514d" }}>
                {odooConnMessage}
              </p>
            )}
            <input style={inputStyle} type="file" accept="application/pdf" onChange={onBillPdfSelected} required />
            {billFilename && <p style={{ margin: 0, color: "#35514d" }}>Selected PDF: {billFilename}</p>}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <input
                style={{ ...inputStyle, flex: 1, minWidth: 220 }}
                value={odooVendorSearch}
                onChange={(e) => setOdooVendorSearch(e.target.value)}
                placeholder="Search Odoo vendors (name, VAT, email)"
              />
              <button type="button" style={{ ...buttonStyle, background: "#2f556d" }} onClick={loadOdooVendors} disabled={busy}>
                Load Odoo Vendors
              </button>
            </div>
            {odooVendors.length > 0 && (
              <div style={{ border: "1px solid #d7e3e1", borderRadius: 10, background: "#f8fbfa", padding: 10, maxHeight: 180, overflowY: "auto" }}>
                <p style={{ margin: "0 0 8px", fontWeight: 700, color: "#2f4b47" }}>Vendor Check ({odooVendors.length})</p>
                <div style={{ display: "grid", gap: 6 }}>
                  {odooVendors.slice(0, 60).map((vendor) => (
                    <p key={vendor.id} style={{ margin: 0, fontSize: 13, color: "#35514d" }}>
                      {vendor.name} {vendor.vat ? `| VAT: ${vendor.vat}` : ""} {vendor.email ? `| ${vendor.email}` : ""}
                    </p>
                  ))}
                </div>
              </div>
            )}
            <button type="submit" style={buttonStyle} disabled={busy}>Create Bill + Attach PDF</button>
            {billDebug && (
              <div style={{ border: "1px solid #d7e3e1", borderRadius: 10, background: "#f8fbfa", padding: 10 }}>
                <p style={{ margin: "0 0 8px", fontWeight: 700, color: "#2f4b47" }}>Import Debug & Details</p>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#35514d" }}>
                  {JSON.stringify(billDebug, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </form>
      </section>

      <section style={{ marginTop: 16, ...sectionStyle }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Emails</h2>
          <button type="button" style={buttonStyle} onClick={() => Promise.all([refreshJobs(), refreshEmails(), refreshGmailAccounts()])} disabled={busy}>
            Refresh Jobs + Emails
          </button>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
          <button type="button" style={buttonStyle} onClick={previewSelectedEmailsForOdooBills} disabled={busy || selectedEmailIds.length === 0}>
            Preview Bills Before Import
          </button>
          <button type="button" style={buttonStyle} onClick={importSelectedEmailsToOdooBills} disabled={busy || selectedEmailIds.length === 0}>
            Quick Import (No Preview)
          </button>
          <button
            type="button"
            style={{ ...buttonStyle, background: "#3a6f69" }}
            onClick={() => setSelectedEmailIds(filteredEmails.slice(0, 20).map((email) => email.id))}
            disabled={busy || filteredEmails.length === 0}
          >
            Select Visible Emails
          </button>
          <button
            type="button"
            style={{ ...buttonStyle, background: "#5b6d73" }}
            onClick={() => setSelectedEmailIds([])}
            disabled={busy || selectedEmailIds.length === 0}
          >
            Clear Selection
          </button>
          <StatusPill text={`Selected: ${selectedEmailIds.length}`} tone="neutral" />
          <label style={{ display: "flex", alignItems: "center", gap: 6, color: "#2f4b47", fontWeight: 600 }}>
            <input
              type="checkbox"
              checked={debugImportEnabled}
              onChange={(e) => setDebugImportEnabled(e.target.checked)}
            />
            <span>Debug Import</span>
          </label>
        </div>
        <div style={{ display: "grid", gap: 10, marginBottom: 12 }}>
          <p style={{ margin: 0, color: "#35514d", fontWeight: 700 }}>Filter #1</p>
          <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            <div style={{ border: "1px solid #b8c9c6", borderRadius: 10, padding: 10, maxHeight: 160, overflowY: "auto" }}>
              <p style={{ margin: "0 0 8px", color: "#35514d", fontSize: 13, fontWeight: 600 }}>Received from</p>
              {senderOptions.length === 0 ? (
                <p style={{ margin: 0, fontSize: 13, color: "#54716c" }}>No sender values loaded yet.</p>
              ) : (
                senderOptions.map((sender) => (
                  <label key={sender} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: "#35514d", marginBottom: 6 }}>
                    <input
                      type="checkbox"
                      checked={selectedFromAddresses.includes(sender)}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedFromAddresses((prev) => Array.from(new Set([...prev, sender])));
                        } else {
                          setSelectedFromAddresses((prev) => prev.filter((value) => value !== sender));
                        }
                      }}
                    />
                    <span>{sender}</span>
                  </label>
                ))
              )}
            </div>
            <input
              style={inputStyle}
              value={emailSubjectFilter}
              onChange={(e) => setEmailSubjectFilter(e.target.value)}
              placeholder="Subject contains"
            />
            <select
              style={inputStyle}
              value={emailHasAttachmentsFilter}
              onChange={(e) => setEmailHasAttachmentsFilter(e.target.value)}
            >
              <option value="any">Attachments: Any</option>
              <option value="yes">Attachments: Yes</option>
              <option value="no">Attachments: No</option>
            </select>
            <select
              style={inputStyle}
              value={emailFilterLogic}
              onChange={(e) => setEmailFilterLogic(e.target.value)}
            >
              <option value="and">Match: AND (all filters)</option>
              <option value="or">Match: OR (any filter)</option>
            </select>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" style={buttonStyle} onClick={refreshEmails} disabled={busy}>
              Apply Email Filters
            </button>
            <button
              type="button"
              style={{ ...buttonStyle, background: "#3a6f69" }}
              onClick={() => {
                setSelectedFromAddresses([]);
                setEmailSubjectFilter("");
                setEmailHasAttachmentsFilter("any");
                setEmailFilterLogic("and");
              }}
              disabled={busy}
            >
              Clear Filter #1
            </button>
          </div>
        </div>
        {filteredEmails.length === 0 ? (
          <p>{emails.length === 0 ? "No synced emails yet." : "No emails match Filter #1."}</p>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {filteredEmails.slice(0, 20).map((email) => (
              <article
                key={email.id}
                onClick={() => previewSingleEmailForOdooBill(email.id)}
                style={{ border: "1px solid #d7e3e1", borderRadius: 12, padding: 10, background: "#f8fbfa", cursor: "pointer" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <label style={{ display: "flex", gap: 8, alignItems: "center" }} onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedEmailIds.includes(email.id)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedEmailIds((prev) => Array.from(new Set([...prev, email.id])));
                        } else {
                          setSelectedEmailIds((prev) => prev.filter((id) => id !== email.id));
                        }
                      }}
                    />
                    <strong>{email.subject || "(no subject)"}</strong>
                  </label>
                  <StatusPill
                    text={renderEmailStatusLabel(email)}
                    tone={email.imported || email.status === "received" ? "good" : "neutral"}
                  />
                </div>
                <p style={{ margin: "6px 0", color: "#2f4b47" }}>From: {email.from_address || "n/a"} | To: {email.to_address || "n/a"}</p>
                <p style={{ margin: 0, fontSize: 12, color: "#54716c" }}>Source: {email.source} | Received: {email.received_at}</p>
                {email.imported && (
                  <p style={{ margin: "4px 0 0", fontSize: 12, color: "#1f5f52", fontWeight: 600 }}>
                    Imported: {email.imported_at || "n/a"}{email.bill_reference ? ` | Bill Reference: ${email.bill_reference}` : ""}
                  </p>
                )}
              </article>
            ))}
          </div>
        )}
        {debugImportEnabled && emailBillImportDebug && (
          <div style={{ marginTop: 12, border: "1px solid #d7e3e1", borderRadius: 10, background: "#f8fbfa", padding: 10 }}>
            <p style={{ margin: "0 0 8px", fontWeight: 700, color: "#2f4b47" }}>Debug Import</p>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 12, color: "#35514d" }}>
              {JSON.stringify(emailBillImportDebug, null, 2)}
            </pre>
          </div>
        )}
        <h2 style={{ marginTop: 18 }}>Operations</h2>
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
        <div style={{ marginTop: 12, border: "1px solid #d7e3e1", borderRadius: 10, background: "#f8fbfa", padding: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <p style={{ margin: 0, fontWeight: 700, color: "#2f4b47" }}>Audit Log</p>
            <button type="button" style={{ ...buttonStyle, background: "#3a6f69" }} onClick={refreshAuditLogs} disabled={busy || !tenantId}>
              Refresh Audit Log
            </button>
          </div>
          {auditLogs.length === 0 ? (
            <p style={{ margin: "8px 0 0", color: "#54716c", fontSize: 13 }}>No audit entries yet.</p>
          ) : (
            <div style={{ overflowX: "auto", marginTop: 8 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #d9e4e2", textAlign: "left" }}>
                    <th style={{ padding: "6px 4px" }}>Timestamp</th>
                    <th style={{ padding: "6px 4px" }}>User</th>
                    <th style={{ padding: "6px 4px" }}>Action</th>
                    <th style={{ padding: "6px 4px" }}>Entity</th>
                    <th style={{ padding: "6px 4px" }}>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.slice(0, 25).map((log) => (
                    <tr key={log.id} style={{ borderBottom: "1px solid #edf3f2" }}>
                      <td style={{ padding: "6px 4px" }}>{log.created_at}</td>
                      <td style={{ padding: "6px 4px" }}>{log.actor}</td>
                      <td style={{ padding: "6px 4px" }}>{log.action}</td>
                      <td style={{ padding: "6px 4px" }}>{`${log.entity_type}:${log.entity_id}`}</td>
                      <td style={{ padding: "6px 4px", maxWidth: 360 }}>
                        <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{JSON.stringify(log.details || {}, null, 2)}</pre>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {showEmailBillPreviewModal && emailBillPreview && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(8, 26, 24, 0.55)",
              zIndex: 1000,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: 16
            }}
          >
            <div
              style={{
                width: "min(1120px, 100%)",
                maxHeight: "90vh",
                overflowY: "auto",
                background: "#ffffff",
                borderRadius: 14,
                border: "1px solid #d3e0dd",
                padding: 16
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <h3 style={{ margin: 0 }}>Bill Preview Before Odoo Import</h3>
                <StatusPill text={`Ready: ${emailBillPreview.ready}/${emailBillPreview.processed}`} tone={emailBillPreview.ready > 0 ? "good" : "neutral"} />
              </div>
              <p style={{ margin: "8px 0 12px", color: "#35514d" }}>
                Review extracted fields and PDF attachment(s) below. Import only after verification.
              </p>
              <div style={{ display: "grid", gap: 12 }}>
                {(Array.isArray(emailBillPreview.items) ? emailBillPreview.items : []).map((item) => {
                  const extracted = item.extracted || {};
                  const edited = previewEditsByEmailId[item.email_id] || extracted;
                  const importResult = previewImportResultByEmailId[item.email_id] || null;
                  const attachment = item.attachment_preview || {};
                  const extractionConfidence = item?.debug?.extraction_confidence || {};
                  const overallConfidenceRaw = Number(extractionConfidence?.overall);
                  const overallConfidence =
                    Number.isFinite(overallConfidenceRaw) && overallConfidenceRaw >= 0
                      ? Math.max(0, Math.min(1, overallConfidenceRaw))
                      : null;
                  const pdfSrc = attachment.content_base64 ? `data:${attachment.mime_type || "application/pdf"};base64,${attachment.content_base64}` : "";
                  const canImport = item.status === "ready";
                  return (
                    <article key={item.email_id} style={{ border: "1px solid #d7e3e1", borderRadius: 12, padding: 12, background: "#f8fbfa" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                        <strong>{item.subject || "(no subject)"}</strong>
                        <StatusPill text={item.status} tone={canImport ? "good" : "neutral"} />
                      </div>
                      <p style={{ margin: "6px 0", color: "#2f4b47", fontSize: 13 }}>From: {item.from_address || "n/a"}</p>
                      {overallConfidence !== null && (
                        <p style={{ margin: "0 0 8px", color: "#2f4b47", fontSize: 12, fontWeight: 700 }}>
                          AI Confidence: {(overallConfidence * 100).toFixed(0)}%
                        </p>
                      )}
                      <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", marginBottom: 10 }}>
                        <label><strong>Vendor</strong><input style={inputStyle} value={edited.vendor || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "vendor", e.target.value)} /></label>
                        <label><strong>Bill Reference</strong><input style={inputStyle} value={edited.bill_reference || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "bill_reference", e.target.value)} /></label>
                        <label><strong>Bill Date</strong><input style={inputStyle} value={edited.bill_date || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "bill_date", e.target.value)} /></label>
                        <label><strong>Invoice Date</strong><input style={inputStyle} value={edited.invoice_date || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "invoice_date", e.target.value)} /></label>
                        <label><strong>Product</strong><input style={inputStyle} value={edited.product || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "product", e.target.value)} /></label>
                        <label><strong>Accounting Date</strong><input style={inputStyle} value={edited.accounting_date || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "accounting_date", e.target.value)} /></label>
                        <label><strong>Account Id</strong><input style={inputStyle} value={edited.account_id || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "account_id", e.target.value)} /></label>
                        <label><strong>%VAT</strong><input style={inputStyle} value={edited.vat_percent || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "vat_percent", e.target.value)} /></label>
                        <label><strong>Billing Id</strong><input style={inputStyle} value={edited.billing_id || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "billing_id", e.target.value)} /></label>
                        <label><strong>Currency</strong><input style={inputStyle} value={edited.currency || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "currency", e.target.value)} placeholder="e.g. GBP, USD, EUR, £, $" /></label>
                        <label><strong>Discount</strong><input style={inputStyle} value={edited.discount || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "discount", e.target.value)} placeholder="e.g. 10% or 10" /></label>
                        <label><strong>Payment Reference</strong><input style={inputStyle} value={edited.payment_reference || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "payment_reference", e.target.value)} /></label>
                        <label><strong>Recipient Bank</strong><input style={inputStyle} value={edited.recipient_bank || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "recipient_bank", e.target.value)} /></label>
                        <label><strong>Price</strong><input style={inputStyle} value={edited.price ?? ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "price", e.target.value)} /></label>
                        <label><strong>Tax</strong><input style={inputStyle} value={edited.tax || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "tax", e.target.value)} /></label>
                        <label><strong>Amount</strong><input style={inputStyle} value={edited.amount ?? ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "amount", e.target.value)} /></label>
                        <label><strong>Due Date</strong><input style={inputStyle} value={edited.due_date || ""} onChange={(e) => onPreviewFieldChanged(item.email_id, "due_date", e.target.value)} /></label>
                      </div>
                      {pdfSrc ? (
                        <div style={{ border: "1px solid #ccd9d6", borderRadius: 10, overflow: "hidden", background: "#ffffff" }}>
                          <div style={{ padding: "6px 10px", borderBottom: "1px solid #e1ebe9", fontSize: 12, color: "#35514d" }}>
                            Attachment: {attachment.filename || "invoice.pdf"}
                          </div>
                          <iframe title={`pdf-preview-${item.email_id}`} src={pdfSrc} style={{ width: "100%", height: 360, border: "none" }} />
                        </div>
                      ) : (
                        <p style={{ margin: "8px 0 0", fontSize: 12, color: "#8e1f1b" }}>PDF preview is not available for this email.</p>
                      )}
                      {item.detail && <p style={{ margin: "8px 0 0", fontSize: 12, color: "#54716c" }}>{item.detail}</p>}
                      {importResult && (
                        <p
                          style={{
                            margin: "8px 0 0",
                            fontSize: 12,
                            color: importResult.status === "created" ? "#1f6d49" : "#8e1f1b",
                            fontWeight: 700
                          }}
                        >
                          Import result: {importResult.status}
                          {importResult.bill_id ? ` | Bill ID: ${importResult.bill_id}` : ""}
                          {importResult.detail ? ` | ${importResult.detail}` : ""}
                        </p>
                      )}
                    </article>
                  );
                })}
              </div>
              {Object.keys(previewImportResultByEmailId).length > 0 && (
                <div style={{ marginTop: 10, border: "1px solid #d7e3e1", borderRadius: 10, background: "#f8fbfa", padding: 10 }}>
                  <p style={{ margin: 0, fontWeight: 700, color: "#2f4b47" }}>Latest Import Result</p>
                  <p style={{ margin: "6px 0 0", fontSize: 13, color: "#35514d" }}>
                    Success: {Object.values(previewImportResultByEmailId).filter((row) => row?.status === "created").length}
                    {" | "}
                    Failed: {Object.values(previewImportResultByEmailId).filter((row) => row?.status === "failed").length}
                    {" | "}
                    Total: {Object.keys(previewImportResultByEmailId).length}
                  </p>
                </div>
              )}
              <div style={{ marginTop: 10, display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                <label>
                  <strong>Audit User</strong>
                  <input style={inputStyle} value={currentUser} onChange={(e) => setCurrentUser(e.target.value)} placeholder="ui-user" />
                </label>
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14, flexWrap: "wrap" }}>
                <button
                  type="button"
                  style={{ ...buttonStyle, background: "#3a6f69" }}
                  onClick={savePreviewEditsAudit}
                  disabled={busy}
                >
                  Save Edits (Audit)
                </button>
                <button
                  type="button"
                  style={{ ...buttonStyle, background: "#5b6d73" }}
                  onClick={() => setShowEmailBillPreviewModal(false)}
                  disabled={busy}
                >
                  Close Preview
                </button>
                <button
                  type="button"
                  style={buttonStyle}
                  onClick={importEditedPreviewBillsToOdoo}
                  disabled={
                    busy ||
                    !(Array.isArray(emailBillPreview.items) && emailBillPreview.items.some((item) => item.status === "ready"))
                  }
                >
                  Import Ready Bills to Odoo ({Array.isArray(emailBillPreview.items) ? emailBillPreview.items.filter((item) => item.status === "ready").length : 0})
                </button>
              </div>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
