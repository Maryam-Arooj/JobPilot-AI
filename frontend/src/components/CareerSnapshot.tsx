'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { User, FileText, Bookmark, Send, CheckCircle2 } from 'lucide-react';
import { apiFetch } from '@/lib/api';

interface MetricCardProps {
  label: string;
  value: string | number;
  sublabel: string;
  href: string;
  icon: React.ElementType;
}

function MetricItem({ label, value, sublabel, href, icon: Icon }: MetricCardProps) {
  return (
    <Link
      href={href}
      className="flex flex-col justify-between rounded-lg border border-line bg-surface p-4 transition-colors hover:border-line-strong group"
    >
      <div className="flex items-center justify-between text-muted">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-subtle">{label}</span>
        <Icon className="h-3.5 w-3.5 text-subtle transition-colors group-hover:text-accent" />
      </div>
      <div className="my-2">
        <div className="text-2xl font-semibold tracking-tight tabular-nums text-fg">{value}</div>
        <div className="mt-0.5 text-xs text-muted">{sublabel}</div>
      </div>
    </Link>
  );
}

/** Career snapshot built from the user's saved data. Shows "—" when a value can't be loaded. */
export function CareerSnapshot() {
  const [data, setData] = useState<{ completeness?: number; facts?: number; resumes?: number; jobs?: number; apps?: number; sent?: number }>({});

  useEffect(() => {
    Promise.allSettled([apiFetch('/profiles/me'), apiFetch('/resumes/'), apiFetch('/jobs/'), apiFetch('/applications/')]).then(
      ([p, r, j, a]) => {
        setData({
          completeness: p.status === 'fulfilled' ? p.value?.completeness_pct ?? 0 : undefined,
          facts: p.status === 'fulfilled' ? (p.value?.facts || []).filter((f: { verified?: boolean }) => f.verified).length : undefined,
          resumes: r.status === 'fulfilled' && Array.isArray(r.value) ? r.value.length : undefined,
          jobs: j.status === 'fulfilled' && Array.isArray(j.value) ? j.value.length : undefined,
          apps: a.status === 'fulfilled' && Array.isArray(a.value) ? a.value.length : undefined,
          sent: a.status === 'fulfilled' && Array.isArray(a.value) ? a.value.filter((x: { status?: string }) => x.status === 'SUBMITTED').length : undefined,
        });
      },
    );
  }, []);

  const show = (v: number | undefined, suffix = '') => (typeof v === 'number' ? `${v}${suffix}` : '—');

  const metrics: MetricCardProps[] = [
    { label: 'Profile', value: show(data.completeness, '%'), sublabel: 'Complete', href: '/profile', icon: User },
    { label: 'Resumes', value: show(data.resumes), sublabel: 'Saved CV versions', href: '/resume', icon: FileText },
    { label: 'Jobs', value: show(data.jobs), sublabel: 'Discovered', href: '/jobs', icon: Bookmark },
    { label: 'Applications', value: show(data.apps), sublabel: `${show(data.sent)} sent`, href: '/applications', icon: Send },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-subtle">Career Snapshot</h3>
        <span className="flex items-center gap-1 text-xs font-medium text-ok">
          <CheckCircle2 className="h-3.5 w-3.5" /> {show(data.facts)} facts verified
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {metrics.map((m) => (
          <MetricItem key={m.label} {...m} />
        ))}
      </div>
    </div>
  );
}
