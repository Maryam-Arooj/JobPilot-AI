'use client';

import React, { useEffect, useState } from 'react';
import { CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { EmptyState } from '@/components/ui';

interface AIInsightPanelProps {
  /** Skills from the user's career profile. When omitted the panel loads them itself. */
  skills?: string[];
  /** Missing skills reported by real job recommendations. When omitted the panel loads them itself. */
  gaps?: string[];
}

interface ProfileSkillsLike {
  skills?: unknown;
  professional?: { skills?: unknown } | null;
}

interface RecommendationLike {
  missing_skills?: unknown[];
}

/** Flatten the profile `skills` field, which may be a list or a dict of lists. */
export function flattenProfileSkills(profile: ProfileSkillsLike | null | undefined): string[] {
  const out: string[] = [];
  const add = (v: unknown) => {
    if (Array.isArray(v)) v.forEach((x) => typeof x === 'string' && x && out.push(x));
    else if (typeof v === 'string' && v) out.push(v);
  };
  const skills = profile?.skills;
  if (Array.isArray(skills)) add(skills);
  else if (skills && typeof skills === 'object') Object.values(skills).forEach(add);
  add(profile?.professional?.skills);
  return Array.from(new Map(out.map((s) => [s.toLowerCase(), s])).values());
}

/** Count missing skills across real recommendations, most frequent first. */
export function topGaps(recommendations: RecommendationLike[] | null | undefined, limit = 8): string[] {
  const counts = new Map<string, number>();
  for (const r of recommendations || []) {
    for (const g of r?.missing_skills || []) {
      if (typeof g === 'string' && g) counts.set(g, (counts.get(g) || 0) + 1);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit).map(([g]) => g);
}

/**
 * Skills snapshot built only from real data: profile skills and the
 * missing-skill lists returned by /jobs/recommendations. Nothing is invented.
 */
export function AIInsightPanel({ skills, gaps }: AIInsightPanelProps) {
  const [loaded, setLoaded] = useState<{ skills: string[]; gaps: string[] } | null>(null);
  const selfLoad = skills === undefined || gaps === undefined;

  useEffect(() => {
    if (!selfLoad) return;
    Promise.allSettled([apiFetch('/profiles/me'), apiFetch('/jobs/recommendations?limit=20')]).then(([p, r]) => {
      setLoaded({
        skills: p.status === 'fulfilled' ? flattenProfileSkills(p.value) : [],
        gaps: r.status === 'fulfilled' ? topGaps(r.value?.results || []) : [],
      });
    });
  }, [selfLoad]);

  const skillList = (selfLoad ? loaded?.skills : skills) || [];
  const gapList = (selfLoad ? loaded?.gaps : gaps) || [];

  return (
    <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
      <header className="mb-4 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-accent" />
        <h2 className="text-base font-semibold text-fg">Skills snapshot</h2>
        <span className="text-xs text-muted">From your profile and current job matches</span>
      </header>

      {skillList.length === 0 && gapList.length === 0 ? (
        <EmptyState
          title="No skills data yet"
          description="Add skills to your career profile or run a job search to see matched skills and gaps here."
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-line bg-inset p-3.5">
            <div className="mb-2.5 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 font-semibold text-ok">
                <CheckCircle2 className="h-3.5 w-3.5" /> Your profile skills
              </span>
              <span className="text-muted">{skillList.length}</span>
            </div>
            {skillList.length ? (
              <div className="flex flex-wrap gap-1.5">
                {skillList.slice(0, 16).map((skill) => (
                  <span key={skill} className="rounded border border-ok/25 bg-ok-soft px-2 py-0.5 text-xs text-fg-2">
                    {skill}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted">No skills saved in your profile yet.</p>
            )}
          </div>
          <div className="rounded-lg border border-line bg-inset p-3.5">
            <div className="mb-2.5 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 font-semibold text-bad">
                <AlertTriangle className="h-3.5 w-3.5" /> Skills missing from your matches
              </span>
              <span className="text-muted">{gapList.length}</span>
            </div>
            {gapList.length ? (
              <div className="flex flex-wrap gap-1.5">
                {gapList.map((gap) => (
                  <span key={gap} className="rounded border border-bad/25 bg-bad-soft px-2 py-0.5 text-xs text-fg-2">
                    {gap}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted">No gaps reported by your current job recommendations.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
