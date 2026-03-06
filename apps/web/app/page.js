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

export default async function HomePage() {
  const [health, jobs] = await Promise.all([fetchHealth(), fetchJobs()]);
  return <ControlPlaneApp initialHealth={health} initialJobs={jobs} />;
}
