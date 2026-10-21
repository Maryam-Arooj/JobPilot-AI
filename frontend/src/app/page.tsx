'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { AICommandComposer } from '@/components/AICommandComposer';
import { AIInsightPanel, flattenProfileSkills, topGaps } from '@/components/AIInsightPanel';
import { WorkflowStrip, type WorkflowStage } from '@/components/WorkflowStrip';
import { LiveAgentActivity } from '@/components/LiveAgentActivity';
import { ApplyWithAI } from '@/components/ApplyWithAI';
import { PageHeader, Card, CardHeader, StatusPill, EmptyState, buttonClass } from '@/components/ui';
import type { Tone } from '@/components/ui';
import {
  Briefcase,
  ArrowRight,
  ChevronRight,
  Building2,
  MapPin,
  Activity,
  CircleAlert,
  Inbox,
  Bot,
} from 'lucide-react';

/** Application statuses produced by the backend, mapped to honest labels. */
const APP_STATUS: Record<string, { label: string; tone: Tone }> = {
  PREPARING: { label: 'Preparing', tone: 'pending' },
  DRAFT_READY: { label: 'Draft ready', tone: 'accent' },
  READY_FOR_REVIEW: { label: 'Ready for review', tone: 'accent' },
  SUBMITTED: { label: 'Sent', tone: 'ok' },
};
const REVIEW_STATUSES = new Set(['DRAFT_READY', 'READY_FOR_REVIEW']);

interface ProfileData {
  personal?: { name?: string } | null;
  completeness_pct?: number;
  facts?: { verified?: boolean }[];
  skills?: unknown;
  professional?: { skills?: unknown } | null;
}
interface Recommendation {
  id: number;
  title: string;
  company: string;
  location?: string;
  match_score?: number;
  matched_skills?: string[];
  missing_skills?: string[];
}
interface ApplicationRow {
  id: number;
  job_id: number;
  job_title?: string;
  company_name?: string;
  status?: string;
}

export default function DashboardPage() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [jobsCount, setJobsCount] = useState<number>(0);
  const [resumesCount, setResumesCount] = useState<number>(0);
  const [appsCount, setAppsCount] = useState<number>(0);
  const [recentApps, setRecentApps] = useState<ApplicationRow[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState<string[]>([]);

  useEffect(() => {
    const loadDashboardData = async () => {
      setLoading(true);
      try {
        const [profData, jobsData, resumesData, appsData, recsData] = await Promise.allSettled([
          apiFetch('/profiles/me'),
          apiFetch('/jobs/'),
          apiFetch('/resumes/'),
          apiFetch('/applications/'),
          apiFetch('/jobs/recommendations?limit=4')
        ]);

        const failures: string[] = [];
        if (profData.status === 'fulfilled') {
          setProfile(profData.value);
        } else failures.push('profile');
        if (jobsData.status === 'fulfilled' && Array.isArray(jobsData.value)) {
          setJobsCount(jobsData.value.length);
        } else failures.push('jobs');
        if (resumesData.status === 'fulfilled' && Array.isArray(resumesData.value)) {
          setResumesCount(resumesData.value.length);
        } else failures.push('resumes');
        if (appsData.status === 'fulfilled' && Array.isArray(appsData.value)) {
          setAppsCount(appsData.value.length);
          setRecentApps(appsData.value);
        } else failures.push('applications');
        if (recsData.status === 'fulfilled' && recsData.value?.results) {
          setRecommendations(recsData.value.results);
        } else failures.push('recommendations');
        setFailed(failures);
      } catch (err) {
        console.warn('Dashboard data fetch notice:', err);
      } finally {
        setLoading(false);
      }
    };
    loadDashboardData();
  }, []);

  const name = profile?.personal?.name || '';
  const completeness = profile?.completeness_pct || 0;
  const verifiedFactsCount = (profile?.facts || []).filter((f) => f.verified).length;
  const awaitingReview = recentApps.filter((a) => REVIEW_STATUSES.has(a.status || '')).length;
  const sentCount = recentApps.filter((a) => a.status === 'SUBMITTED').length;
  const backendDown = !loading && failed.length === 5;

  const stage = (hasData: boolean, inProgress = false): WorkflowStage['state'] =>
    loading ? 'loading' : hasData ? 'done' : inProgress ? 'active' : 'todo';

  const stages: WorkflowStage[] = [
    {
      key: 'profile',
      title: 'User Profile',
      system: 'You',
      href: '/profile',
      state: stage(completeness >= 80, completeness > 0),
      detail: profile ? `${completeness}% complete · ${verifiedFactsCount} verified facts` : 'No profile data loaded',
    },
    {
      key: 'cv',
      title: 'CV Agent',
      system: 'Profile & CV',
      href: '/resume',
      state: stage(resumesCount > 0, verifiedFactsCount > 0),
      detail: `${resumesCount} saved CV version${resumesCount === 1 ? '' : 's'}`,
    },
    {
      key: 'job',
      title: 'Job Agent',
      system: 'Jobs',
      href: '/jobs',
      state: stage(jobsCount > 0),
      detail: `${jobsCount} job${jobsCount === 1 ? '' : 's'} discovered`,
    },
    {
      key: 'email',
      title: 'Email Agent',
      system: 'Outreach',
      href: '/applications',
      state: stage(appsCount > 0),
      detail: `${appsCount} application workspace${appsCount === 1 ? '' : 's'}`,
    },
    {
      key: 'review',
      title: 'Review & Action',
      system: 'You',
      href: '/applications',
      state: loading ? 'loading' : awaitingReview > 0 ? 'attention' : sentCount > 0 ? 'done' : 'todo',
      detail: `${awaitingReview} awaiting your review · ${sentCount} sent`,
    },
  ];

  return (
    <AppShell>
      <div className="space-y-6">
        <PageHeader
          title={name ? <>Welcome back, <span className="text-accent">{name}</span></> : 'Overview'}
          subtitle="Profile, CVs, job matches and outreach. All figures come from your saved data."
          actions={
            <>
              <Link href="/agent-transparency" className={buttonClass('secondary', 'md')}>
                <Activity className="h-4 w-4" /> Agent Transparency
              </Link>
              <Link href="/agent" className={buttonClass('primary', 'md')}>
                <Bot className="h-4 w-4" /> Career Counsellor
              </Link>
            </>
          }
        />

        {backendDown && (
          <div className="flex items-start gap-3 rounded-lg border border-bad/30 bg-bad-soft p-4 text-sm" role="alert">
            <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
            <div>
              <p className="font-semibold text-bad">Can&apos;t reach the JobPilot backend</p>
              <p className="mt-0.5 text-fg-2">The figures below are empty because no data could be loaded. Start the backend server and refresh.</p>
            </div>
          </div>
        )}

        {/* End-to-end workflow */}
        <section aria-labelledby="workflow-heading" className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="workflow-heading" className="text-base font-semibold text-fg">Your workflow</h2>
            <span className="hidden text-xs text-muted sm:inline">Profile → CV Agent → Job Agent → Email Agent → You</span>
          </div>
          <WorkflowStrip stages={stages} />
        </section>

        <ApplyWithAI />

        <LiveAgentActivity />

        <AICommandComposer />

        <div className="grid gap-6 xl:grid-cols-2">
          {/* Recommended jobs */}
          <Card>
            <CardHeader
              title="Top job matches"
              note="Ranked by overlap with your profile skills"
              action={
                <Link href="/jobs" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
                  All jobs <ChevronRight className="h-4 w-4" />
                </Link>
              }
            />
            {recommendations.length > 0 ? (
              <ul className="divide-y divide-line">
                {recommendations.map((rec) => (
                  <li key={rec.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-fg">{rec.title}</p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted">
                          <span className="flex items-center gap-1"><Building2 className="h-3.5 w-3.5" /> {rec.company}</span>
                          {rec.location && <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {rec.location}</span>}
                        </p>
                      </div>
                      {typeof rec.match_score === 'number' && (
                        <StatusPill tone={rec.match_score >= 85 ? 'ok' : rec.match_score >= 65 ? 'accent' : 'pending'}>
                          {rec.match_score}% match
                        </StatusPill>
                      )}
                    </div>
                    {rec.matched_skills && rec.matched_skills.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {rec.matched_skills.slice(0, 4).map((sk, i) => (
                          <span key={i} className="rounded border border-line-strong bg-surface-2 px-2 py-0.5 text-[11px] text-fg-2">
                            {sk}
                          </span>
                        ))}
                      </div>
                    )}
                    <Link href="/jobs" className="inline-flex items-center gap-1 self-start text-xs font-semibold text-accent hover:underline">
                      Open in Job Discovery <ArrowRight className="h-3.5 w-3.5" />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={Briefcase}
                title={loading ? 'Loading matches…' : 'No job matches yet'}
                description={loading ? undefined : 'Run a search in Job Discovery. Matches are scored against the skills in your profile.'}
                action={!loading && <Link href="/jobs" className={buttonClass('secondary', 'sm')}>Go to Job Discovery</Link>}
              />
            )}
          </Card>

          {/* Recent applications */}
          <Card>
            <CardHeader
              title="Recent applications"
              note="Drafts are never sent without your approval"
              action={
                <Link href="/applications" className="inline-flex items-center gap-1 text-sm text-accent hover:underline">
                  View all <ChevronRight className="h-4 w-4" />
                </Link>
              }
            />
            {recentApps.length > 0 ? (
              <div className="-mx-4 overflow-x-auto sm:-mx-5">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-y border-line text-xs text-muted">
                      <th className="px-4 py-2 font-medium sm:px-5">Position</th>
                      <th className="px-3 py-2 font-medium">Company</th>
                      <th className="px-3 py-2 font-medium">Status</th>
                      <th className="px-4 py-2 sm:px-5"><span className="sr-only">Open</span></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {recentApps.slice(0, 6).map((app) => {
                      const st = APP_STATUS[app.status || ''] || { label: app.status || 'Unknown', tone: 'neutral' as Tone };
                      return (
                        <tr key={app.id} className="hover:bg-surface-2/60">
                          <td className="max-w-[220px] truncate px-4 py-2.5 font-medium text-fg sm:px-5">{app.job_title || '—'}</td>
                          <td className="max-w-[160px] truncate px-3 py-2.5 text-fg-2">{app.company_name || '—'}</td>
                          <td className="px-3 py-2.5"><StatusPill tone={st.tone}>{st.label}</StatusPill></td>
                          <td className="px-4 py-2.5 text-right sm:px-5">
                            <Link href={`/applications?job_id=${app.job_id}`} className="text-xs font-semibold text-accent hover:underline">
                              Open
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                icon={Inbox}
                title={loading ? 'Loading applications…' : 'No applications yet'}
                description={loading ? undefined : 'Pick a job in Job Discovery to prepare a tailored application and email draft.'}
                action={!loading && <Link href="/jobs" className={buttonClass('secondary', 'sm')}>Find a job</Link>}
              />
            )}
          </Card>
        </div>

        <AIInsightPanel skills={flattenProfileSkills(profile)} gaps={topGaps(recommendations)} />
      </div>
    </AppShell>
  );
}
