"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  Calendar,
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Copy,
  FileSearch,
  LoaderCircle,
  Mail,
  Search,
  TriangleAlert,
  X,
  Zap,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import type {
  AgentKey,
  AgentRun,
  AgentSnapshot,
  AgentState,
  DataSource,
  RunStatus,
} from "./types";
import s from "./agentTransparency.module.css";

/* ------------------------------------------------------------------ */
/* Static metadata                                                     */
/* ------------------------------------------------------------------ */

const AGENTS: Record<AgentKey, { name: string; blurb: string; icon: React.ElementType; tone: string }> = {
  cv: { name: "CV Agent", blurb: "Analyses resume & builds profile", icon: FileSearch, tone: s.toneCv },
  job: { name: "Job Agent", blurb: "Searches & matches jobs", icon: Search, tone: s.toneJob },
  email: { name: "Email Agent", blurb: "Creates and manages outreach", icon: Mail, tone: s.toneEmail },
};

const AGENT_ORDER: AgentKey[] = ["cv", "job", "email"];

const STATUS_LABEL: Record<RunStatus, string> = {
  running: "Running",
  success: "Success",
  failed: "Failed",
  pending: "Pending",
  waiting: "Waiting",
};

const STATE_LABEL: Record<AgentState, string> = {
  running: "Running",
  idle: "Idle",
  waiting: "Awaiting",
  error: "Error",
};

const STATE_TO_STATUS: Record<AgentState, RunStatus | "idle"> = {
  running: "running",
  idle: "idle",
  waiting: "waiting",
  error: "failed",
};

const RANGES = [
  { value: "1h", label: "Last hour", ms: 3600e3 },
  { value: "24h", label: "Last 24 hours", ms: 24 * 3600e3 },
  { value: "7d", label: "Last 7 days", ms: 7 * 24 * 3600e3 },
];

const TABS = ["Overview", "Input/Output", "Tool Calls", "Logs", "Events"] as const;
type Tab = (typeof TABS)[number];

/* ------------------------------------------------------------------ */
/* Formatting helpers                                                  */
/* ------------------------------------------------------------------ */

const clock = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";

const shortClock = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : "—";

const longStamp = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "—";

function duration(ms: number) {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const sec = total % 60;
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return m > 0 ? `${m}m ${String(sec).padStart(2, "0")}s` : `${sec}s`;
}

function ago(iso: string | null | undefined, now: number) {
  if (!iso) return "—";
  const diff = Math.max(0, now - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return `${Math.floor(diff / 86400)} d ago`;
}

/** Pretty JSON that keeps short arrays of primitives on one line. */
function compactJson(value: unknown): string {
  const raw = JSON.stringify(value, null, 2);
  if (raw === undefined) return "—";
  return raw.replace(/\[\s*\n([^\[\]{}]*?)\n\s*\]/g, (match, inner: string) => {
    const items = inner.split(",\n").map((x) => x.trim());
    const line = `[${items.join(", ")}]`;
    return line.length <= 60 ? line : match;
  });
}

const runDuration = (run: AgentRun, now: number) =>
  duration((run.finished_at ? new Date(run.finished_at).getTime() : now) - new Date(run.started_at).getTime());

/* ------------------------------------------------------------------ */
/* Data hook                                                           */
/* ------------------------------------------------------------------ */

function useAgentSnapshot(range: string) {
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(null);
  const [source, setSource] = useState<DataSource>("loading");
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const data = (await apiFetch(`/agent-runs/snapshot?range=${range}`)) as AgentSnapshot;
      if (!data || !Array.isArray(data.runs)) throw new Error("Malformed snapshot");
      setSnapshot(data);
      setSource("live");
    } catch {
      // No agent-run tracking endpoint is available: show an honest empty state, never sample data.
      setSnapshot(null);
      setSource("unavailable");
    }
    setUpdatedAt(Date.now());
  }, [range]);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 10000);
    return () => window.clearInterval(id);
  }, [load]);

  return { snapshot, source, updatedAt };
}

function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

/* ------------------------------------------------------------------ */
/* Small presentational pieces                                         */
/* ------------------------------------------------------------------ */

function StatusPill({ status, label }: { status: RunStatus | "idle"; label?: string }) {
  const cls = {
    running: s.pillRunning,
    success: s.pillSuccess,
    failed: s.pillFailed,
    pending: s.pillPending,
    waiting: s.pillPending,
    idle: s.pillIdle,
  }[status];
  return (
    <span className={`${s.pill} ${cls}`}>
      {status === "running" && <span className={s.pulseDot} aria-hidden />}
      {label ?? (status === "idle" ? "Idle" : STATUS_LABEL[status])}
    </span>
  );
}

function AgentBadge({ agent, size = "md" }: { agent: AgentKey; size?: "sm" | "md" | "lg" }) {
  const meta = AGENTS[agent];
  const Icon = meta.icon;
  const dims = size === "sm" ? s.badgeSm : size === "lg" ? s.badgeLg : s.badgeMd;
  return (
    <span className={`${s.agentBadge} ${dims} ${meta.tone}`} aria-hidden>
      <Icon strokeWidth={1.8} />
    </span>
  );
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  const [copied, setCopied] = useState(false);
  const text = useMemo(() => (value === undefined ? "—" : compactJson(value)), [value]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };
  return (
    <section className={s.subCard}>
      <header className={s.subCardHead}>
        <h4>
          {title} <span className={s.dim}>(sanitised)</span>
        </h4>
        <button type="button" className={s.ghostBtn} onClick={copy} aria-label={`Copy ${title}`}>
          {copied ? <Check size={13} /> : <Copy size={13} />} {copied ? "Copied" : "Copy"}
        </button>
      </header>
      <pre className={s.code}>{text}</pre>
    </section>
  );
}

function ToolCallList({ run }: { run: AgentRun }) {
  if (!run.tool_calls.length) return <p className={s.empty}>No tool calls recorded for this run.</p>;
  return (
    <ul className={s.toolList}>
      {run.tool_calls.map((tc) => (
        <li key={tc.id} className={s.toolItem}>
          <div className={s.toolTop}>
            <span className={s.toolName}>
              <Zap size={12} /> {tc.name}
            </span>
            <span className={s.mono}>{clock(tc.at)}</span>
            <StatusPill status={tc.status} />
          </div>
          <p className={s.toolMeta}>
            {tc.summary}
            {tc.duration_ms !== undefined && <> · {(tc.duration_ms / 1000).toFixed(1)}s</>}
          </p>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

export default function AgentTransparencyDashboard() {
  const [range, setRange] = useState("24h");
  const [agentFilter, setAgentFilter] = useState<AgentKey | "all">("all");
  const [statusFilter, setStatusFilter] = useState<RunStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  const [showAll, setShowAll] = useState(false);

  const { snapshot, source, updatedAt } = useAgentSnapshot(range);
  const now = useNow();


  const runs = useMemo(() => snapshot?.runs ?? [], [snapshot]);

  // Default selection: the first running run, otherwise the newest.
  useEffect(() => {
    if (!runs.length) return;
    if (selectedId && runs.some((r) => r.id === selectedId)) return;
    setSelectedId((runs.find((r) => r.status === "running") ?? runs[0]).id);
  }, [runs, selectedId]);

  const rangeMs = RANGES.find((r) => r.value === range)?.ms ?? 24 * 3600e3;
  const inRange = useMemo(
    () => runs.filter((r) => now - new Date(r.started_at).getTime() <= rangeMs),
    [runs, now, rangeMs],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return inRange.filter(
      (r) =>
        (agentFilter === "all" || r.agent === agentFilter) &&
        (statusFilter === "all" || r.status === statusFilter) &&
        (!q || r.id.toLowerCase().includes(q) || r.correlation_id.toLowerCase().includes(q)),
    );
  }, [inRange, agentFilter, statusFilter, query]);

  const stats = useMemo(() => {
    const success = inRange.filter((r) => r.status === "success").length;
    const failed = inRange.filter((r) => r.status === "failed").length;
    const running = inRange.filter((r) => r.status === "running").length;
    const today = inRange.filter((r) => new Date(r.started_at).toDateString() === new Date(now).toDateString()).length;
    const finished = success + failed;
    return {
      total: inRange.length,
      today,
      running,
      success,
      failed,
      rate: finished ? Math.round((success / finished) * 100) : null,
    };
  }, [inRange, now]);

  const selected = runs.find((r) => r.id === selectedId) ?? null;
  const visibleRuns = showAll ? filtered : filtered.slice(0, 6);
  const filtersActive = agentFilter !== "all" || statusFilter !== "all" || query !== "" || range !== "24h";

  const clearFilters = () => {
    setAgentFilter("all");
    setStatusFilter("all");
    setQuery("");
    setRange("24h");
  };

  return (
    <div className={s.root}>
      <div className={s.main}>
        <header className={s.header}>
          <div>
            <div className={s.titleRow}>
              <h1>Agent Transparency &amp; Observability</h1>
              {source === "live" ? (
                <span className={s.livePill}>
                  <span className={s.pulseDot} aria-hidden /> Live
                </span>
              ) : source === "unavailable" ? (
                <span className={s.previewPill} title="The backend does not provide GET /agent-runs/snapshot yet">
                  Not connected
                </span>
              ) : (
                <span className={s.previewPill}>Connecting…</span>
              )}
            </div>
            <p className={s.subtitle}>Monitor what your AI agents are doing in real time</p>
          </div>
        </header>

        <div className={s.body}>
          {/* ============ Left / centre column ============ */}
          <div className={s.content}>
            {/* Stats */}
            <div className={s.stats}>
              <StatCard icon={Activity} tone={s.toneNeutral} label="Total Runs" value={stats.total} note={`${stats.today} started today`} />
              <StatCard icon={LoaderCircle} tone={s.toneCv} label="Running Tasks" value={stats.running} note={stats.running ? "Active right now" : "None running"} noteTone={stats.running ? s.noteSaffron : undefined} spin={stats.running > 0} />
              <StatCard icon={CircleCheck} tone={s.toneOk} label="Successful Runs" value={stats.success} note={stats.rate === null ? "No finished runs" : `${stats.rate}% success rate`} noteTone={s.noteOk} />
              <StatCard icon={TriangleAlert} tone={s.toneBad} label="Failed Runs" value={stats.failed} note={stats.failed ? "Needs attention" : "All clear"} noteTone={stats.failed ? s.noteBad : s.noteOk} />
            </div>

            {/* Agent status */}
            <section className={s.card}>
              <header className={s.cardHead}>
                <h2>Agent Status</h2>
                <span className={s.headNote}>
                  <span className={source === "live" ? s.dotOk : s.dotSand} aria-hidden />
                  {source === "live" ? "Live status from backend" : "Backend agent tracking not connected"}
                </span>
              </header>
              <div className={s.agentGrid}>
                {AGENT_ORDER.map((key) => {
                  const st = snapshot?.agents.find((a) => a.agent === key);
                  const meta = AGENTS[key];
                  const state: AgentState = st?.state ?? "idle";
                  const known = Boolean(st);
                  return (
                    <article key={key} className={`${s.agentCard} ${state === "running" ? s.agentCardActive : ""}`}>
                      <div className={s.agentTop}>
                        <AgentBadge agent={key} size="lg" />
                        <div className={s.agentName}>
                          <div className={s.agentNameRow}>
                            <h3>{meta.name}</h3>
                            <StatusPill status={known ? STATE_TO_STATUS[state] : "idle"} label={known ? STATE_LABEL[state] : "No data"} />
                          </div>
                          <p>{meta.blurb}</p>
                        </div>
                      </div>
                      <dl className={s.agentMeta}>
                        <div className={s.agentTask}>
                          <dt>Current task</dt>
                          <dd>{st?.current_task ?? "No activity recorded"}</dd>
                        </div>
                        {state === "running" ? (
                          <>
                            <div className={s.kvRow}>
                              <dt>Started</dt>
                              <dd>{ago(st?.started_at, now)}</dd>
                            </div>
                            <div className={s.kvRow}>
                              <dt>Duration</dt>
                              <dd className={s.mono}>
                                {st?.started_at ? duration(now - new Date(st.started_at).getTime()) : "—"}
                              </dd>
                            </div>
                          </>
                        ) : (
                          <div className={s.kvRow}>
                            <dt>Last activity</dt>
                            <dd>{ago(st?.last_activity_at, now)}</dd>
                          </div>
                        )}
                      </dl>
                    </article>
                  );
                })}
              </div>
            </section>

            {/* Timeline + workflow + recent runs */}
            <div className={s.lower}>
              <section className={`${s.card} ${s.timelineCard}`}>
                <header className={s.cardHead}>
                  <h2>Live Execution Timeline</h2>
                  <span className={s.headNote}>
                    <span className={source === "live" ? s.dotBad : s.dotSand} aria-hidden /> {source === "live" ? "Real-time events" : "Waiting for backend"}
                  </span>
                </header>
                {snapshot?.timeline.length ? (
                  <ol className={s.timeline}>
                    {snapshot.timeline.map((ev) => (
                      <li key={ev.id} className={s.tlItem}>
                        <AgentBadge agent={ev.agent} size="sm" />
                        <span className={`${s.num} ${s.tlTime}`}>{clock(ev.at)}</span>
                        <div className={s.tlText}>
                          <p className={s.tlTitle}>{ev.title}</p>
                          <p className={s.tlDetail}>{ev.detail}</p>
                        </div>
                        <StatusPill status={ev.status} label={ev.status === "running" && ev.agent === "email" ? "In progress" : undefined} />
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className={s.empty}>
                    {source === "unavailable" ? "No agent events available — run tracking is not connected yet." : "No events in this time range."}
                  </p>
                )}
              </section>

              <div className={s.stack}>
                <section className={s.card}>
                  <header className={s.cardHead}>
                    <h2>Workflow Execution</h2>
                  </header>
                  <div className={s.flow}>
                    {AGENT_ORDER.map((key, i) => {
                      const st = snapshot?.agents.find((a) => a.agent === key);
                      const state: AgentState = st?.state ?? "idle";
                      return (
                        <React.Fragment key={key}>
                          <div className={s.flowNode}>
                            <span className={`${s.flowRing} ${state === "running" ? s.flowRingActive : ""}`}>
                              <AgentBadge agent={key} size="lg" />
                            </span>
                            <p>{AGENTS[key].name}</p>
                            <StatusPill
                              status={st ? STATE_TO_STATUS[state] : "idle"}
                              label={!st ? "No data" : state === "idle" ? "Waiting" : state === "waiting" ? "Pending" : STATE_LABEL[state]}
                            />
                          </div>
                          {i < AGENT_ORDER.length - 1 && (
                            <span className={s.flowArrow} aria-hidden>
                              <ArrowRight size={18} />
                            </span>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </div>
                </section>

                <section className={s.card}>
                  <header className={s.cardHead}>
                    <h2>Recent Runs</h2>
                    {filtered.length > 6 && (
                      <button type="button" className={s.linkBtn} onClick={() => setShowAll((v) => !v)}>
                        {showAll ? "Show less" : "View all"}
                      </button>
                    )}
                  </header>
                  <div className={s.tableWrap}>
                    <table className={s.table}>
                      <thead>
                        <tr>
                          <th>Run ID</th>
                          <th>Agent</th>
                          <th>Status</th>
                          <th>Duration</th>
                          <th>Started</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleRuns.map((r) => (
                          <tr
                            key={r.id}
                            className={r.id === selectedId ? s.rowSelected : ""}
                            onClick={() => {
                              setSelectedId(r.id);
                              setTab("Overview");
                            }}
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                setSelectedId(r.id);
                              }
                            }}
                            aria-selected={r.id === selectedId}
                          >
                            <td className={`${s.mono} ${s.runId}`}>#{r.id}</td>
                            <td>
                              <span className={`${s.agentCell} ${s.agentText}`}>
                                <span className={`${s.agentDot} ${AGENTS[r.agent].tone}`} aria-hidden />
                                {AGENTS[r.agent].name}
                              </span>
                            </td>
                            <td>
                              <StatusPill status={r.status} />
                            </td>
                            <td className={s.num}>{runDuration(r, now)}</td>
                            <td className={s.num}>{shortClock(r.started_at)}</td>
                          </tr>
                        ))}
                        {!visibleRuns.length && (
                          <tr>
                            <td colSpan={5} className={s.empty}>
                              No runs match these filters.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            </div>

          </div>

          {/* ============ Right panel ============ */}
          <aside className={s.panel} aria-label="Run details">
            <div className={s.filters}>
              <label className={s.selectWrap}>
                <Calendar size={15} />
                <select value={range} onChange={(e) => setRange(e.target.value)} aria-label="Time range">
                  {RANGES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <ChevronDown size={15} className={s.chev} />
              </label>
              <label className={s.searchWrap}>
                <Search size={15} />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by run ID…"
                  aria-label="Search by run ID"
                />
              </label>
              <label className={s.selectWrap}>
                <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value as AgentKey | "all")} aria-label="Agent filter">
                  <option value="all">All Agents</option>
                  {AGENT_ORDER.map((k) => (
                    <option key={k} value={k}>
                      {AGENTS[k].name}
                    </option>
                  ))}
                </select>
                <ChevronDown size={15} className={s.chev} />
              </label>
              <label className={s.selectWrap}>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as RunStatus | "all")} aria-label="Status filter">
                  <option value="all">All Statuses</option>
                  {(Object.keys(STATUS_LABEL) as RunStatus[]).map((k) => (
                    <option key={k} value={k}>
                      {STATUS_LABEL[k]}
                    </option>
                  ))}
                </select>
                <ChevronDown size={15} className={s.chev} />
              </label>
              <button type="button" className={s.linkBtn} onClick={clearFilters} disabled={!filtersActive}>
                Clear
              </button>
            </div>

            {selected ? (
              <section className={s.details}>
                <header className={s.detailsHead}>
                  <h2>
                    Run Details <span className={s.mono}>#{selected.id}</span>
                  </h2>
                  <StatusPill status={selected.status} />
                  <button type="button" className={s.iconBtn} onClick={() => setSelectedId(null)} aria-label="Close run details">
                    <X size={16} />
                  </button>
                </header>

                <div className={s.tabs} role="tablist">
                  {TABS.map((t) => (
                    <button
                      key={t}
                      type="button"
                      role="tab"
                      aria-selected={tab === t}
                      className={`${s.tab} ${tab === t ? s.tabActive : ""}`}
                      onClick={() => setTab(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>

                {tab === "Overview" && (
                  <>
                    <dl className={s.kvList}>
                      <KV k="Run ID" v={<span className={s.mono}>#{selected.id}</span>} />
                      <KV k="Agent" v={<span className={s.agentCell}><AgentBadge agent={selected.agent} size="sm" /> {AGENTS[selected.agent].name}</span>} />
                      <KV k="Task" v={selected.task} />
                      <KV k="Status" v={<StatusPill status={selected.status} />} />
                      <KV k="Started" v={longStamp(selected.started_at)} />
                      <KV k="Duration" v={<span className={s.mono}>{runDuration(selected, now)}</span>} />
                      <KV k="Correlation ID" v={<span className={s.mono}>{selected.correlation_id}</span>} />
                      <KV k="Retry count" v={selected.retry_count} />
                    </dl>

                    {selected.current_step && selected.status === "running" && (
                      <section className={s.subCard}>
                        <h4 className={s.subTitle}>Current Step</h4>
                        <div className={s.step}>
                          <LoaderCircle size={22} className={s.spin} />
                          <div className={s.stepBody}>
                            <p>{selected.current_step.label}</p>
                            <p className={s.dim}>
                              Step {selected.current_step.index} of {selected.current_step.total} · {selected.current_step.pct}% complete
                            </p>
                            <div className={s.bar} role="progressbar" aria-valuenow={selected.current_step.pct} aria-valuemin={0} aria-valuemax={100}>
                              <span style={{ width: `${selected.current_step.pct}%` }} />
                            </div>
                          </div>
                        </div>
                      </section>
                    )}

                    <JsonBlock title="Input" value={selected.input} />
                    <JsonBlock title="Output" value={selected.output} />
                    <section className={s.subCard}>
                      <h4 className={s.subTitle}>Tool Calls</h4>
                      <ToolCallList run={selected} />
                    </section>
                  </>
                )}

                {tab === "Input/Output" && (
                  <>
                    <JsonBlock title="Input" value={selected.input} />
                    <JsonBlock title="Output" value={selected.output} />
                  </>
                )}

                {tab === "Tool Calls" && (
                  <section className={s.subCard}>
                    <ToolCallList run={selected} />
                  </section>
                )}

                {tab === "Logs" && (
                  <section className={s.subCard}>
                    {selected.logs.length ? (
                      <ul className={s.logList}>
                        {selected.logs.map((l, i) => (
                          <li key={i} className={s[`log_${l.level}`]}>
                            <span className={s.mono}>{clock(l.at)}</span>
                            <span className={s.logLevel}>{l.level.toUpperCase()}</span>
                            <span>{l.message}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className={s.empty}>No logs recorded for this run.</p>
                    )}
                  </section>
                )}

                {tab === "Events" && (
                  <section className={s.subCard}>
                    {selected.events.length ? (
                      <ul className={s.logList}>
                        {selected.events.map((ev, i) => (
                          <li key={i}>
                            <span className={s.mono}>{clock(ev.at)}</span>
                            <span className={s.eventType}>{ev.type}</span>
                            <span>{ev.detail}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className={s.empty}>No events recorded for this run.</p>
                    )}
                  </section>
                )}
              </section>
            ) : (
              <section className={`${s.details} ${s.detailsEmpty}`}>
                <FileSearch size={22} />
                <p>{runs.length ? "Select a run from Recent Runs to inspect its trace." : "No runs to inspect yet."}</p>
              </section>
            )}

            <div className={source === "live" ? s.sourceLive : s.sourcePreview} role="status">
              {source === "live" ? <CircleCheck size={16} /> : <CircleAlert size={16} />}
              <p>
                {source === "live" ? (
                  <>
                    Real execution data from the backend.
                    <br />
                    <span>Updated {updatedAt ? clock(new Date(updatedAt).toISOString()) : "—"}</span>
                  </>
                ) : (
                  <>
                    Agent run tracking is not connected.
                    <br />
                    <span>Real runs appear here once the backend provides GET /agent-runs/snapshot. No sample data is shown.</span>
                  </>
                )}
              </p>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function StatCard({
  icon: Icon,
  tone,
  label,
  value,
  note,
  noteTone,
  spin,
}: {
  icon: React.ElementType;
  tone: string;
  label: string;
  value: number;
  note: string;
  noteTone?: string;
  spin?: boolean;
}) {
  return (
    <div className={s.stat}>
      <span className={`${s.statIcon} ${tone}`}>
        <Icon size={20} strokeWidth={1.8} className={spin ? s.spin : undefined} />
      </span>
      <div>
        <p className={s.statLabel}>{label}</p>
        <p className={s.statValue}>{value}</p>
        <p className={`${s.statNote} ${noteTone ?? ""}`}>{note}</p>
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className={s.kvItem}>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </div>
  );
}
