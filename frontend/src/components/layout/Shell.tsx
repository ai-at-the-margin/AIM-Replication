import {
  IconAlertTriangle, IconChartDots3, IconCircles, IconCloudDownload, IconCpu, IconFileAnalytics, IconHourglass,
  IconLayoutDashboard, IconListSearch, IconMoon, IconRefresh, IconRoute, IconSun, IconTargetArrow, IconUsersGroup,
  IconWorldSearch,
} from "@tabler/icons-react";
import { motion } from "motion/react";
import React, { useState } from "react";
import { Sidebar, SidebarBody, SidebarLink } from "@/components/ui/sidebar";
import { useData } from "@/lib/data";
import { cn } from "@/lib/utils";

export const NAV = [
  { route: "overview", label: "Overview", icon: IconLayoutDashboard, group: "Project" },
  { route: "pipeline", label: "Pipeline & data", icon: IconRoute, group: "Project" },
  { route: "collection", label: "Collection", icon: IconCloudDownload, group: "Project" },
  { route: "overlap", label: "Name overlap", icon: IconCircles, group: "Paper figures" },
  { route: "factors", label: "Factor profiles", icon: IconChartDots3, group: "Paper figures" },
  { route: "mandates", label: "Mandates", icon: IconTargetArrow, group: "Paper figures" },
  { route: "search", label: "Search & queries", icon: IconWorldSearch, group: "Paper figures" },
  { route: "crowding", label: "AI crowd book", icon: IconUsersGroup, group: "New analytics" },
  { route: "information", label: "Information date", icon: IconHourglass, group: "New analytics" },
  { route: "models", label: "Models", icon: IconCpu, group: "New analytics" },
  { route: "explorer", label: "Portfolio explorer", icon: IconListSearch, group: "Data" },
  { route: "results", label: "Results vs paper", icon: IconFileAnalytics, group: "Data" },
];

function Logo({ open }: { open: boolean }) {
  return (
    <a href="#/overview" className="relative z-20 flex items-center gap-2 py-1 text-sm font-normal">
      <svg viewBox="0 0 32 32" className="h-7 w-7 shrink-0"><rect width="32" height="32" rx="8" fill="#0a0a0a" />
        <path d="M7 22 L13 12 L18 18 L25 8" stroke="#3987e5" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="25" cy="8" r="2.5" fill="#d95926" /></svg>
      {open && (
        <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="font-semibold whitespace-pre text-[var(--ink)]">
          AI at the Margin
        </motion.span>
      )}
    </a>
  );
}

export function Shell({ route, children }: { route: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const { datasets, current, setCurrent, bundle, dark, setDark, reload, loading } = useData();
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  return (
    <div className="flex h-screen w-full flex-col overflow-hidden md:flex-row">
      <Sidebar open={open} setOpen={setOpen}>
        <SidebarBody className="justify-between gap-6 border-r border-black/5 bg-white/70 backdrop-blur dark:border-white/5 dark:bg-neutral-950">
          <div className="flex flex-1 flex-col overflow-x-hidden overflow-y-auto">
            <Logo open={open} />
            <div className="mt-6 flex flex-col gap-0.5">
              {groups.map((g) => (
                <div key={g} className="mb-2">
                  {open && <div className="px-2 pt-2 pb-1 text-[10px] font-semibold tracking-[0.16em] text-[var(--muted)] uppercase">{g}</div>}
                  {NAV.filter((n) => n.group === g).map((n) => {
                    const Icon = n.icon;
                    const active = route === n.route;
                    return (
                      <SidebarLink key={n.route}
                        className={cn("rounded-lg px-2", active ? "bg-black/[0.06] dark:bg-white/[0.08]" : "hover:bg-black/[0.03] dark:hover:bg-white/[0.04]")}
                        link={{ label: n.label, href: `#/${n.route}`, icon: <Icon className={cn("h-5 w-5 shrink-0", active ? "text-[var(--s1)]" : "text-neutral-500 dark:text-neutral-400")} /> }} />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
          <div className="text-[10px] text-[var(--muted)]">{open ? `v${bundle?.meta.experiment_version ?? ""}` : ""}</div>
        </SidebarBody>
      </Sidebar>
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-black/5 bg-[var(--page)]/80 px-4 py-2.5 backdrop-blur md:px-8 dark:border-white/5">
          <div className="flex items-center gap-2 text-xs text-[var(--ink-2)]">
            <span className="hidden sm:inline">Dataset</span>
            <div className="inline-flex rounded-full border border-black/10 p-0.5 dark:border-white/10">
              {datasets.map((d) => (
                <button key={d.name} onClick={() => setCurrent(d.name)}
                  className={cn("rounded-full px-3 py-1 text-xs font-medium capitalize transition",
                    current === d.name ? "bg-neutral-900 text-white dark:bg-white dark:text-black" : "text-[var(--ink-2)] hover:text-[var(--ink)]")}>
                  {d.name}{d.meta?.synthetic ? " · synthetic" : ""}
                </button>
              ))}
            </div>
            {bundle?.meta.asof && <span className="hidden md:inline">as-of <b className="text-[var(--ink)]">{bundle.meta.asof}</b> · universe <b className="text-[var(--ink)]">{bundle.meta.universe}</b></span>}
          </div>
          <div className="flex items-center gap-1">
            <button onClick={reload} className="rounded-lg p-2 text-[var(--ink-2)] hover:bg-black/5 dark:hover:bg-white/5" aria-label="Reload data" title="Reload data">
              <IconRefresh size={18} className={loading ? "animate-spin" : ""} />
            </button>
            <button onClick={() => setDark(!dark)} className="rounded-lg p-2 text-[var(--ink-2)] hover:bg-black/5 dark:hover:bg-white/5" aria-label="Toggle theme" title="Toggle theme">
              {dark ? <IconSun size={18} /> : <IconMoon size={18} />}
            </button>
          </div>
        </header>
        {bundle?.meta.synthetic && (
          <div className="flex items-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-800 md:px-8 dark:text-amber-200">
            <IconAlertTriangle size={16} className="shrink-0" />
            <span><b>Synthetic demo data.</b> Model responses are simulated and the market is synthetic, so the pipeline can run end to end without API keys or WRDS. These are not research results. Real tickers are used only so the resolver sees real formats.</span>
          </div>
        )}
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1400px] px-4 py-8 md:px-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
