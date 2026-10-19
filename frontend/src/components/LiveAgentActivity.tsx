'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Activity, ChevronRight, PlugZap } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { Card, CardHeader, StatusPill, EmptyState, AgentBadge, AGENT_META } from '@/components/ui';
import type { Tone } from '@/components/ui';
import type { AgentSnapshot, AgentState, RunStatus } from '@/features/agent-transparency/types';

const STATE_PILL: Record<AgentState, { label: string; tone: Tone; pulse?: boolean }> = {
  running: { label: 'Running', tone: 'accent', pulse: true },
  idle: { label: 'Idle', tone: 'neutral' },
  waiting: { label: 'Waiting', tone: 'pending' },
  error: { label: 'Last run failed', tone: 'bad' },
};

const EVENT_TONE: Record<RunStatus, Tone> = {
  running: 'accent',
  success: 'ok',
  failed: 'bad',
  pending: 'pending',
  waiting: 'pending',
};

function ago(iso?: string | null, now = Date.now()) {
  if (!iso) return '—';
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

/** Live view of the CV, Job and Email agents, fed by GET /agent-runs/snapshot. Real runs only. */
export function LiveAgentActivity() {
  const [snapshot, setSnapshot] = useState<AgentSnapshot | null>(null);
  const [status, setStatus] = useState<'loading' | 'live' | 'unavailable'>('loading');
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    try {
      const data = (await apiFetch('/agent-runs/snapshot?range=24h')) as AgentSnapshot;
      if (!data || !Array.isArray(data.agents)) throw new Error('Malformed snapshot');
      setSnapshot(data);
      setStatus('live');
    } catch {
      setSnapshot(null);
      setStatus('unavailable');
    }
    setNow(Date.now());
  }, []);

  const anyRunning = !!snapshot?.agents.some((a) => a.state === 'running');

  useEffect(() => {
    load();
    const id = window.setInterval(load, anyRunning ? 3000 : 10000);
    return () => window.clearInterval(id);
  }, [load, anyRunning]);

  const events = (snapshot?.timeline ?? []).slice(0, 5);

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <Activity className="h-4 w-4 text-accent" /> Live agent activity
          </span>
        }
        note={status === 'live' ? (anyRunning ? 'Updating every 3 s' : 'Last 24 hours · updates every 10 s') : undefined}
        action={
          <Link href="/agent-transparency" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
            Open dashboard <ChevronRight className="h-4 w-4" />
          </Link>
        }
      />

      {status === 'unavailable' ? (
        <EmptyState
          icon={PlugZap}
          title="Agent activity is not connected"
          description="The backend did not answer /agent-runs/snapshot. Start the backend and refresh."
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <ul className="space-y-2.5" aria-label="Agent status">
            {(['cv', 'job', 'email'] as const).map((key) => {
              const st = snapshot?.agents.find((a) => a.agent === key);
              const pill = st ? STATE_PILL[st.state] : { label: status === 'loading' ? 'Loading…' : 'Idle', tone: 'neutral' as Tone };
              return (
                <li key={key} className="flex items-center gap-3 rounded-lg border border-line bg-surface-2/40 px-3 py-2.5">
                  <AgentBadge agent={key} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-fg">{AGENT_META[key].name}</p>
                    <p className="truncate text-xs text-muted">
                      {st?.current_task || '—'}
                      {st?.last_activity_at ? ` · ${ago(st.last_activity_at, now)}` : ''}
                    </p>
                  </div>
                  <StatusPill tone={pill.tone} pulse={'pulse' in pill && !!pill.pulse}>{pill.label}</StatusPill>
                </li>
              );
            })}
          </ul>

          {events.length > 0 ? (
            <ol className="space-y-2.5" aria-label="Recent agent events">
              {events.map((ev) => (
                <li key={ev.id} className="flex items-start gap-3">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${AGENT_META[ev.agent].dot}`} aria-hidden />
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm text-fg">
                      <span className="font-medium">{ev.title}</span>
                      <StatusPill tone={EVENT_TONE[ev.status] ?? 'neutral'}>{AGENT_META[ev.agent].name}</StatusPill>
                    </p>
                    <p className="truncate text-xs text-muted">{ev.detail} · {ago(ev.at, now)}</p>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState
              icon={Activity}
              title={status === 'loading' ? 'Loading activity…' : 'No agent runs in the last 24 hours'}
              description={status === 'loading' ? undefined : 'Upload a CV, search for jobs or prepare an application — every run appears here live.'}
            />
          )}
        </div>
      )}
    </Card>
  );
}
