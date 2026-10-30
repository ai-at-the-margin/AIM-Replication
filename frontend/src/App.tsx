import { IconLoader2 } from "@tabler/icons-react";
import React from "react";
import { Shell } from "@/components/layout/Shell";
import { DataProvider, useData } from "@/lib/data";
import { useRoute } from "@/lib/router";
import { Collection } from "@/pages/Collection";
import { Crowding } from "@/pages/Crowding";
import { Explorer } from "@/pages/Explorer";
import { Factors } from "@/pages/Factors";
import { Information } from "@/pages/Information";
import { Mandates } from "@/pages/Mandates";
import { Models } from "@/pages/Models";
import { Overlap } from "@/pages/Overlap";
import { Overview } from "@/pages/Overview";
import { Pipeline } from "@/pages/Pipeline";
import { Results } from "@/pages/Results";
import { Search } from "@/pages/Search";

const PAGES: Record<string, () => React.ReactElement> = {
  overview: Overview, pipeline: Pipeline, collection: Collection, overlap: Overlap, factors: Factors,
  mandates: Mandates, search: Search, crowding: Crowding, information: Information, models: Models,
  explorer: Explorer, results: Results,
};

class Boundary extends React.Component<{ children: React.ReactNode; route: string }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) { return { error: String(e) }; }
  componentDidUpdate(prev: { route: string }) { if (prev.route !== this.props.route && this.state.error) this.setState({ error: null }); }
  render() {
    if (this.state.error) return <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-600">This page failed to render: {this.state.error}</div>;
    return this.props.children;
  }
}

function Body() {
  const route = useRoute();
  const { bundle, loading, error } = useData();
  const Page = PAGES[route] ?? Overview;
  return (
    <Shell route={route}>
      {!bundle && loading && <div className="flex items-center gap-2 text-sm text-[var(--ink-2)]"><IconLoader2 className="animate-spin" size={18} /> Loading data…</div>}
      {!bundle && !loading && error && <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm">{error}</div>}
      {bundle && <Boundary route={route}><Page /></Boundary>}
    </Shell>
  );
}

export default function App() {
  return <DataProvider><Body /></DataProvider>;
}
