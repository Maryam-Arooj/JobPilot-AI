'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft, Building2, MapPin, ExternalLink, Briefcase } from 'lucide-react';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { PageHeader, Card, CardHeader, EmptyState, StatusPill, buttonClass } from '@/components/ui';

/** Job detail backed by the existing GET /jobs/{id} endpoint. Shows only what the API returns. */
interface JobDetailData {
  title: string;
  company: string;
  location?: string;
  description?: string;
  requirements?: string[];
  application_url?: string;
  match?: { overall_alignment?: string } | null;
}

export default function JobDetail() {
  const params = useParams<{ id: string }>();
  const [job, setJob] = useState<JobDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    apiFetch(`/jobs/${params.id}`)
      .then(setJob)
      .catch((e) => setError(e?.message || 'Could not load this job.'));
  }, [params?.id]);

  return (
    <AppShell>
      <div className="space-y-6">
        <Link href="/jobs" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
          <ArrowLeft className="h-4 w-4" /> Back to Job Discovery
        </Link>

        {error ? (
          <EmptyState icon={Briefcase} title="Job not available" description={error} />
        ) : !job ? (
          <EmptyState icon={Briefcase} title="Loading job…" />
        ) : (
          <>
            <PageHeader
              title={job.title}
              subtitle={
                <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className="flex items-center gap-1.5"><Building2 className="h-4 w-4" /> {job.company}</span>
                  {job.location && <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" /> {job.location}</span>}
                </span>
              }
              status={job.match?.overall_alignment && <StatusPill tone="accent">{job.match.overall_alignment}</StatusPill>}
              actions={
                job.application_url && (
                  <a href={job.application_url} target="_blank" rel="noopener noreferrer" className={buttonClass('primary', 'md')}>
                    View posting <ExternalLink className="h-4 w-4" />
                  </a>
                )
              }
            />
            <Card>
              <CardHeader title="Description" />
              <p className="whitespace-pre-line text-sm leading-relaxed text-fg-2">{job.description || 'No description provided by the source.'}</p>
            </Card>
            {Array.isArray(job.requirements) && job.requirements.length > 0 && (
              <Card>
                <CardHeader title="Requirements" />
                <div className="flex flex-wrap gap-1.5">
                  {job.requirements.map((r, i) => (
                    <span key={i} className="rounded border border-line-strong bg-surface-2 px-2 py-0.5 text-xs text-fg-2">{r}</span>
                  ))}
                </div>
              </Card>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}
