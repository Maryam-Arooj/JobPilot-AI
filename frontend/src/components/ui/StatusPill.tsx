import React from 'react';
import { cx } from './cn';

export type Tone = 'accent' | 'ok' | 'bad' | 'pending' | 'neutral';

const tones: Record<Tone, string> = {
  accent: 'text-accent bg-accent-soft border-accent/30',
  ok: 'text-ok bg-ok-soft border-ok/30',
  bad: 'text-bad bg-bad-soft border-bad/30',
  pending: 'text-pending bg-pending-soft border-pending/30',
  neutral: 'text-muted bg-surface-2 border-line-strong',
};

export function StatusPill({
  tone = 'neutral',
  pulse = false,
  children,
  className,
}: {
  tone?: Tone;
  pulse?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2 py-0.5 text-[11.5px] font-semibold',
        tones[tone],
        className,
      )}
    >
      {pulse && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" aria-hidden />}
      {children}
    </span>
  );
}
