'use client';

import React from 'react';
import Link from 'next/link';
import { ArrowRight, User, FileSearch, Search, Mail, UserCheck } from 'lucide-react';
import { StatusPill, cx } from '@/components/ui';
import type { Tone } from '@/components/ui';

export type StageState = 'loading' | 'todo' | 'active' | 'done' | 'attention';

export interface WorkflowStage {
  key: 'profile' | 'cv' | 'job' | 'email' | 'review';
  title: string;
  system: string;
  href: string;
  state: StageState;
  detail: string;
}

const ICONS: Record<WorkflowStage['key'], React.ElementType> = {
  profile: User,
  cv: FileSearch,
  job: Search,
  email: Mail,
  review: UserCheck,
};

const ICON_TONE: Record<WorkflowStage['key'], string> = {
  profile: 'bg-surface-2 text-fg border border-line-strong',
  cv: 'bg-agent-cv/15 text-agent-cv',
  job: 'bg-agent-job/15 text-agent-job',
  email: 'bg-agent-email/15 text-agent-email',
  review: 'bg-ok-soft text-ok',
};

const STATE_PILL: Record<StageState, { tone: Tone; label: string }> = {
  loading: { tone: 'neutral', label: 'Loading…' },
  todo: { tone: 'neutral', label: 'Not started' },
  active: { tone: 'accent', label: 'In progress' },
  done: { tone: 'ok', label: 'Has data' },
  attention: { tone: 'accent', label: 'Needs you' },
};

/** End-to-end pipeline: User Profile → CV Agent → Job Agent → Email Agent → User Review. */
export function WorkflowStrip({ stages }: { stages: WorkflowStage[] }) {
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="JobPilot workflow">
      {stages.map((stage, i) => {
        const Icon = ICONS[stage.key];
        const pill = STATE_PILL[stage.state];
        return (
          <li key={stage.key} className="relative">
            <Link
              href={stage.href}
              className={cx(
                'flex h-full flex-col gap-3 rounded-lg border bg-surface p-4 transition-colors hover:border-line-strong',
                stage.state === 'attention' ? 'border-accent/50' : 'border-line',
              )}
            >
              <div className="flex items-center gap-2.5">
                <span className={cx('grid h-9 w-9 shrink-0 place-items-center rounded-full', ICON_TONE[stage.key])}>
                  <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
                </span>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-subtle">
                    Step {i + 1} · {stage.system}
                  </p>
                  <p className="truncate text-sm font-semibold text-fg">{stage.title}</p>
                </div>
              </div>
              <p className="text-xs text-fg-2">{stage.detail}</p>
              <div className="mt-auto flex items-center justify-between">
                <StatusPill tone={pill.tone}>{pill.label}</StatusPill>
                <ArrowRight className="h-4 w-4 text-faint" aria-hidden />
              </div>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
