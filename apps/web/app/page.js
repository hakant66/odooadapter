import ControlPlaneApp from "./components/ControlPlaneApp";

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
    const data = await response.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

async function fetchBootstrapConfig() {
  try {
    const tenantsResp = await fetch(`${coreBase}/tenants?limit=1`, { cache: "no-store" });
    if (!tenantsResp.ok) {
      return null;
    }
    const tenants = await tenantsResp.json().catch(() => []);
    const latestTenant = Array.isArray(tenants) ? tenants[0] : null;
    if (!latestTenant?.id) {
      return null;
    }

    const [connectionsResp, gmailResp] = await Promise.all([
      fetch(
        `${coreBase}/connections?tenant_id=${encodeURIComponent(latestTenant.id)}&connector=odoo&limit=1`,
        { cache: "no-store" }
      ),
      fetch(`${coreBase}/gmail/accounts?tenant_id=${encodeURIComponent(latestTenant.id)}`, { cache: "no-store" })
    ]);

    const connections = await connectionsResp.json().catch(() => []);
    const gmailAccounts = await gmailResp.json().catch(() => []);
    const latestOdoo = Array.isArray(connections) ? connections[0] : null;
    const latestGmail = Array.isArray(gmailAccounts) ? gmailAccounts[0] : null;

    return {
      tenantId: latestTenant.id,
      tenantName: latestTenant.name || "",
      tenantSlug: latestTenant.slug || "",
      odooBaseUrl: latestOdoo?.metadata?.base_url || "",
      odooDatabase: latestOdoo?.metadata?.database || latestOdoo?.external_account_id || "",
      odooUsername: latestOdoo?.metadata?.username || "",
      gmailAccountId: latestGmail?.account_id || "default",
      gmailEmail: latestGmail?.email || ""
    };
  } catch {
    return null;
  }
}

export default async function HomePage() {
  const [health, jobs, bootstrapConfig] = await Promise.all([fetchHealth(), fetchJobs(), fetchBootstrapConfig()]);
  return <ControlPlaneApp initialHealth={health} initialJobs={jobs} initialConfig={bootstrapConfig || {}} />;
}
