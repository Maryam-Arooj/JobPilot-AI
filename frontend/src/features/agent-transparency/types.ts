// Data contract for the Agent Transparency dashboard.
// Served by the backend: GET /agent-runs/snapshot?range=1h|24h|7d -> AgentSnapshot
// (backend/api/agent_runs.py, recorded by backend/services/agent_runs.py).
// If the backend is unreachable the page shows an honest "not connected" state (no sample data).

export type AgentKey = "cv" | "job" | "email";

export type RunStatus = "running" | "success" | "failed" | "pending" | "waiting";

export type AgentState = "running" | "idle" | "waiting" | "error";

export interface ToolCall {
  id: string;
  name: string;
  at: string; // ISO timestamp
  summary: string;
  duration_ms?: number;
  status: "success" | "failed" | "running";
}

export interface LogLine {
  at: string;
  level: "info" | "warn" | "error";
  message: string;
}

export interface RunEvent {
  at: string;
  type: string;
  detail: string;
}

export interface RunStep {
  label: string;
  index: number; // 1-based
  total: number;
  pct: number; // 0-100
}

export interface AgentRun {
  id: string;
  agent: AgentKey;
  task: string;
  status: RunStatus;
  started_at: string;
  finished_at?: string | null;
  correlation_id: string;
  retry_count: number;
  current_step?: RunStep | null;
  input?: unknown;
  output?: unknown;
  tool_calls: ToolCall[];
  logs: LogLine[];
  events: RunEvent[];
}

export interface AgentStatus {
  agent: AgentKey;
  state: AgentState;
  current_task: string;
  started_at?: string | null;
  last_activity_at?: string | null;
}

export interface TimelineEvent {
  id: string;
  at: string;
  agent: AgentKey;
  title: string;
  detail: string;
  status: RunStatus;
}

export interface AgentSnapshot {
  generated_at: string;
  agents: AgentStatus[];
  runs: AgentRun[];
  timeline: TimelineEvent[];
}

export type DataSource = "loading" | "live" | "unavailable";
