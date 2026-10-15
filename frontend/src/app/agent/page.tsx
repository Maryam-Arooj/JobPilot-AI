"use client";

import { AppShell } from "@/components/AppShell";
import { AgentChat } from "@/components/agent-chat/AgentChat";

export default function AgentPage() {
  return (
    <AppShell fullBleed>
      <AgentChat />
    </AppShell>
  );
}
