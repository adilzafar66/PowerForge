import { AppShell } from "@/components/app-shell";
import { StatusDashboard } from "@/components/status-dashboard";
import { apiBaseUrlServer, fetchStackStatus } from "@/lib/health";

export const dynamic = "force-dynamic";

export default async function StatusPage() {
  const { health, ready } = await fetchStackStatus(apiBaseUrlServer());

  return (
    <AppShell active="status">
      <StatusDashboard initialHealth={health} initialReady={ready} />
    </AppShell>
  );
}
