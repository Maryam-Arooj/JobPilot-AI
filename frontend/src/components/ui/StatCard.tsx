import React from 'react';
import Link from 'next/link';
import { cx } from './cn';

const iconTones = {
  neutral: 'bg-surface-2 text-fg border border-line-strong',
  accent: 'bg-accent-soft text-accent',
  ok: 'bg-ok-soft text-ok',
  bad: 'bg-bad-soft text-bad',
  pending: 'bg-pending-soft text-pending',
} as const;

export function StatCard({
  icon: Icon,
  label,
  value,
  note,
  tone = 'neutral',
  href,
}: {
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
  tone?: keyof typeof iconTones;
  href?: string;
}) {
  const body = (
    <>
      <span className={cx('grid h-10 w-10 shrink-0 place-items-center rounded-full', iconTones[tone])}>
        <Icon className="h-5 w-5" strokeWidth={1.8} />
      </span>
      <div className="min-w-0">
        <p className="text-[13px] text-fg-2">{label}</p>
        <p className="mt-0.5 text-2xl font-semibold leading-tight tabular-nums text-fg">{value}</p>
        {note && <p className="mt-0.5 text-xs text-muted">{note}</p>}
      </div>
    </>
  );
  const cls = 'flex gap-3.5 rounded-lg border border-line bg-surface p-4';
  return href ? (
    <Link href={href} className={cx(cls, 'transition-colors hover:border-line-strong')}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}
