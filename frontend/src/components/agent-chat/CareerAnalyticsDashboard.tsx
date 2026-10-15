"use client";

import React, { useState } from "react";
import { BarChart3, CheckCircle2, AlertTriangle, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/ui";

export interface AnalyticsMetrics {
  completeness_pct?: number;
  ats_score?: number;
  ats_rating?: string;
  active_jobs_found?: number;
  role_match_pct?: number;
  verified_facts_count?: number;
  detected_skills?: string[];
  skill_gaps?: string[];
  search_provider?: string;
}

interface CareerAnalyticsDashboardProps {
  metrics: AnalyticsMetrics;
  onQuickAction?: (actionPrompt: string) => void;
  className?: string;
}

const fmt = (v: number | undefined, suffix = "") => (typeof v === "number" ? `${v}${suffix}` : "—");

/**
 * Career panel for the counsellor chat. It only shows values that come from the
 * user's saved data (profile, verified facts, saved jobs, recommendation gaps).
 * Metrics without a real data source are shown as unavailable, never estimated.
 */
export function CareerAnalyticsDashboard({ metrics, onQuickAction, className }: CareerAnalyticsDashboardProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "skills" | "salary" | "ats">("overview");

  const skills = metrics.detected_skills ?? [];
  const gaps = metrics.skill_gaps ?? [];

  return (
    <aside className={cn("flex flex-col overflow-y-auto border-l border-line bg-panel text-fg", className)}>
      {/* Header */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-panel/95 p-4 backdrop-blur-sm">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-lg border border-line-strong bg-surface-2">
            <BarChart3 className="h-4 w-4 text-accent" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight text-fg">Career snapshot</h3>
            <p className="text-[11px] text-muted">From your saved profile and jobs</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-line p-1 text-xs" role="tablist">
        {[
          { id: "overview", label: "Readiness" },
          { id: "skills", label: "Skills" },
          { id: "salary", label: "Compensation" },
          { id: "ats", label: "ATS Health" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id as typeof activeTab)}
            className={cn(
              "flex-1 rounded-md px-2 py-1.5 text-center font-medium transition-colors",
              activeTab === tab.id ? "border border-line-strong bg-surface-2 text-accent" : "text-muted hover:text-fg",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-5 p-4 text-xs">
        {activeTab === "overview" && (
          <>
            <div className="rounded-lg border border-line bg-surface p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-subtle">Profile completeness</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-fg">{fmt(metrics.completeness_pct, "%")}</p>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full rounded-full bg-accent" style={{ width: `${metrics.completeness_pct ?? 0}%` }} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-line bg-surface p-3">
                <p className="text-[11px] text-muted">Verified facts</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">{fmt(metrics.verified_facts_count)}</p>
              </div>
              <div className="rounded-lg border border-line bg-surface p-3">
                <p className="text-[11px] text-muted">Saved jobs</p>
                <p className="mt-1 text-xl font-semibold tabular-nums">{fmt(metrics.active_jobs_found)}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => onQuickAction?.("Extract and verify more technical skills from my background")}
              className="flex w-full items-center justify-between rounded-lg border border-line-strong bg-surface-2 px-3 py-2 text-fg-2 transition-colors hover:border-accent/60 hover:text-fg"
            >
              Ask the counsellor how to complete my profile <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </>
        )}

        {activeTab === "skills" && (
          <>
            <div>
              <p className="mb-2 flex items-center gap-1.5 font-semibold text-ok">
                <CheckCircle2 className="h-3.5 w-3.5" /> Skills in your profile ({skills.length})
              </p>
              {skills.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {skills.map((s) => (
                    <span key={s} className="rounded border border-ok/25 bg-ok-soft px-2 py-0.5 text-fg-2">{s}</span>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No skills saved in your profile yet.</p>
              )}
            </div>
            <div>
              <p className="mb-2 flex items-center gap-1.5 font-semibold text-bad">
                <AlertTriangle className="h-3.5 w-3.5" /> Missing from your job matches ({gaps.length})
              </p>
              {gaps.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {gaps.map((g) => (
                    <span key={g} className="rounded border border-bad/25 bg-bad-soft px-2 py-0.5 text-fg-2">{g}</span>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No gaps reported by your current job recommendations.</p>
              )}
            </div>
          </>
        )}

        {activeTab === "salary" && (
          <EmptyState
            title="No compensation data"
            description="JobPilot has no salary data source connected, so no benchmark is shown. Salaries appear on individual jobs when the listing includes them."
          />
        )}

        {activeTab === "ats" && (
          typeof metrics.ats_score === "number" ? (
            <div className="rounded-lg border border-line bg-surface p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-subtle">ATS score</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">{metrics.ats_score}/100</p>
              {metrics.ats_rating && <p className="mt-1 text-muted">{metrics.ats_rating}</p>}
            </div>
          ) : (
            <EmptyState
              title="No ATS score yet"
              description="Run an ATS audit in the chat. No score is shown until one has been calculated."
              action={
                <button
                  type="button"
                  onClick={() => onQuickAction?.("Run complete ATS audit on my current resume text")}
                  className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent-hover"
                >
                  Run ATS audit
                </button>
              }
            />
          )
        )}
      </div>
    </aside>
  );
}
