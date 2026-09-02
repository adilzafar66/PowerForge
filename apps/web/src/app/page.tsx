import { StatusDashboard } from "@/components/status-dashboard";
import { apiBaseUrlServer, fetchStackStatus } from "@/lib/health";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const { health, ready } = await fetchStackStatus(apiBaseUrlServer());

  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col gap-8 px-6 py-10">
      <header className="space-y-2 border-b border-slate-200 pb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Resa Power</p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">PowerForge</h1>
        <p className="max-w-2xl text-sm leading-6 text-slate-600">
          Engineering data extraction platform. Phase 0 is architecture and a running skeleton:
          the API, database connection, job broker, and this status page. Extraction, OCR, and
          analysis-software integrations are intentionally not implemented.
        </p>
      </header>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">System status</h2>
        <StatusDashboard initialHealth={health} initialReady={ready} />
      </section>
    </main>
  );
}
