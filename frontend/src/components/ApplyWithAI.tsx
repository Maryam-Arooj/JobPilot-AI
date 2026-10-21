'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { CheckCircle2, Circle, Loader2, XCircle, Clock, Sparkles, ArrowRight, Mail } from 'lucide-react';
import { apiFetch } from '@/lib/api';

type StepStatus = 'pending' | 'running' | 'done' | 'failed' | 'waiting';
interface PipelineStep { agent: string; name: string; status: StepStatus; detail: string }
interface PipelineState {
  status: 'running' | 'ready' | 'failed';
  steps: PipelineStep[];
  application_id: number | null;
  job: { title: string; company: string; location?: string; match_score?: number | null } | null;
  recipient: string;
  message: string;
  error: string | null;
  elapsed: number;
}

const WHERE = [
  { label: 'My CV location', location: null as string | null, mode: 'auto' },
  { label: 'Pakistan', location: 'Pakistan', mode: 'location' },
  { label: 'Remote', location: null, mode: 'remote' },
];

function StepIcon({ status }: { status: StepStatus }) {
  if (status === 'done') return <CheckCircle2 className="w-4 h-4 text-ok shrink-0" />;
  if (status === 'running') return <Loader2 className="w-4 h-4 text-accent animate-spin shrink-0" />;
  if (status === 'failed') return <XCircle className="w-4 h-4 text-bad shrink-0" />;
  if (status === 'waiting') return <Clock className="w-4 h-4 text-accent shrink-0" />;
  return <Circle className="w-4 h-4 text-subtle shrink-0" />;
}

/** One click: CV -> live jobs -> recruiter email -> best match -> research + email + CV -> your approval. */
export function ApplyWithAI() {
  const [where, setWhere] = useState(0);
  const [requireEmail, setRequireEmail] = useState(true);
  const [state, setState] = useState<PipelineState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const poll = (id: string) => {
    timer.current = setTimeout(async () => {
      try {
        const s: PipelineState = await apiFetch(`/pipeline/${id}`);
        setState(s);
        if (s.status === 'running') poll(id);
      } catch (e: any) {
        setError(e?.message || 'Lost contact with the pipeline.');
      }
    }, 2000);
  };

  const start = async () => {
    setError(null);
    setState(null);
    try {
      const w = WHERE[where];
      const { pipeline_id } = await apiFetch('/pipeline/apply', {
        method: 'POST',
        body: JSON.stringify({ location: w.location, mode: w.mode, require_email: requireEmail, max_jobs: 10 }),
      });
      setState({ status: 'running', steps: [], application_id: null, job: null, recipient: '', message: '', error: null, elapsed: 0 });
      poll(pipeline_id);
    } catch (e: any) {
      setError(e?.message || 'Could not start. Is the backend running?');
    }
  };

  const running = state?.status === 'running';

  return (
    <section className="p-5 bg-surface border border-line-strong rounded-2xl space-y-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-fg flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-accent" /> Apply with AI
          </h2>
          <p className="text-xs text-muted mt-0.5">
            One click: your CV → live jobs → real recruiter email → best match → company research, email and CV.
            Nothing is sent: you approve the Gmail draft.
          </p>
        </div>
        <button
          onClick={start}
          disabled={running}
          className="bg-accent hover:bg-accent-hover disabled:opacity-60 text-white font-bold text-sm px-5 py-2.5 rounded-xl flex items-center gap-2 shrink-0"
        >
          {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {running ? `Working... ${state?.elapsed ?? 0}s` : 'Apply with AI'}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted">Where:</span>
        {WHERE.map((w, i) => (
          <button key={w.label} disabled={running} onClick={() => setWhere(i)}
                  className={`px-3 py-1.5 rounded-lg border ${where === i ? 'bg-accent text-white border-accent font-semibold' : 'bg-inset text-muted border-line hover:text-fg'}`}>
            {w.label}
          </button>
        ))}
        <label className="flex items-center gap-1.5 ml-2 text-fg-2 cursor-pointer">
          <input type="checkbox" checked={requireEmail} disabled={running} onChange={e => setRequireEmail(e.target.checked)} />
          <Mail className="w-3.5 h-3.5" /> Only jobs with a recruiter email
        </label>
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}

      {state && state.steps.length > 0 && (
        <ol className="space-y-2">
          {state.steps.map((s, i) => (
            <li key={i} className={`flex items-start gap-2.5 p-2.5 rounded-xl border text-xs ${
              s.status === 'running' ? 'border-accent/40 bg-accent-soft' :
              s.status === 'failed' ? 'border-bad/30 bg-bad-soft' :
              s.status === 'done' ? 'border-ok/20 bg-inset' : 'border-line bg-inset'}`}>
              <StepIcon status={s.status} />
              <div className="min-w-0">
                <span className="font-semibold text-fg">{s.name}</span>
                {s.detail && <p className="text-muted mt-0.5 break-words">{s.detail}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}

      {state?.status === 'ready' && state.application_id && (
        <div className="p-3.5 rounded-xl border border-ok/30 bg-ok-soft flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
          <div>
            <span className="font-bold text-ok block">Ready for your approval</span>
            <span className="text-fg-2">
              {state.job?.title} at {state.job?.company}
              {state.recipient ? ` · To: ${state.recipient}` : ' · no published recruiter email'}
            </span>
          </div>
          <Link href={`/applications?id=${state.application_id}`}
                className="bg-accent hover:bg-accent-hover text-white font-bold px-4 py-2 rounded-lg flex items-center gap-1.5 shrink-0">
            Review email & create draft <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}
      {state?.status === 'failed' && state.error && (
        <p className="text-xs text-bad">Stopped: {state.error}</p>
      )}
      <p className="text-[11px] text-muted">
        Each agent&apos;s work is shown live on <Link href="/agent-transparency" className="text-accent underline">Agent Transparency</Link>.
      </p>
    </section>
  );
}
