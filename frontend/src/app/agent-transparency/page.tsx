"use client";

import { AppShell } from "@/components/AppShell";
import AgentTransparencyDashboard from "@/features/agent-transparency/AgentTransparencyDashboard";

export default function AgentTransparencyPage() {
  return (
    <AppShell fullBleed>
      <AgentTransparencyDashboard />
    </AppShell>
  );
}
