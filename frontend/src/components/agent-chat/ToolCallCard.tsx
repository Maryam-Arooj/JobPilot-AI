"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";
import {
  ChevronDown,
  Search,
  FileText,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Copy,
  Check,
  Briefcase,
  Target,
  Sparkles,
  MapPin,
  DollarSign,
  Award,
  Layers,
  Calendar,
  Send,
  ArrowRight,
} from "lucide-react";

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status: "pending" | "running" | "completed" | "error";
  startedAt: Date;
  completedAt?: Date;
  duration?: number;
}

interface ToolCallCardProps {
  toolCall: ToolCall;
  onAction?: (action: string, payload?: unknown) => void;
}

const TOOL_META: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }>; description: string }
> = {
  search_realtime_jobs: {
    label: "Live Google Jobs Search",
    icon: Search,
    description: "Realtime SERP search for active market openings",
  },
  extract_career_profile: {
    label: "Canonical Profile Extraction",
    icon: FileText,
    description: "Extracting structured facts, competencies & gaps",
  },
  analyze_job_match: {
    label: "Role Alignment & Match Matrix",
    icon: Target,
    description: "Evaluating candidate stack vs job requirements",
  },
  calculate_ats_score: {
    label: "ATS Resume Diagnostic",
    icon: Award,
    description: "Auditing keyword density, metrics & ATS layout",
  },
  generate_tailored_resume: {
    label: "Tailored ATS Resume Synthesis",
    icon: Layers,
    description: "Generating role-optimized executive resume document",
  },
  draft_application_materials: {
    label: "Outreach & Cover Letter Drafter",
    icon: Send,
    description: "Crafting cold email, LinkedIn hook & cover letter",
  },
  build_career_roadmap: {
    label: "Strategic 90-Day Career Roadmap",
    icon: Calendar,
    description: "Phased progression milestones & salary benchmarks",
  },
};

export function ToolCallCard({ toolCall, onAction }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const meta = TOOL_META[toolCall.name] || {
    label: toolCall.name.replace(/_/g, " "),
    icon: Sparkles,
    description: "Executing agent capability",
  };
  const Icon = meta.icon;

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return null;
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const res = toolCall.result as any;

  return (
    <div className="rounded-xl border border-line dark:border-line bg-surface dark:bg-surface/60 overflow-hidden shadow-sm transition-all">
      {/* Header bar */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-inset dark:hover:bg-surface/80 transition-colors select-none"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={cn(
              "w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 border",
              toolCall.status === "completed"
                ? "bg-surface-2 dark:bg-surface-2 border-line dark:border-line text-fg dark:text-fg"
                : toolCall.status === "running"
                ? "bg-surface-2 dark:bg-surface-2 border-line dark:border-line text-fg-2 dark:text-fg-2 animate-pulse"
                : "bg-bad-soft dark:bg-bad-soft/40 border-bad/30 dark:border-bad/30 text-bad dark:text-bad"
            )}
          >
            <Icon className="w-4 h-4" />
          </div>

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h4 className="text-xs font-semibold text-fg dark:text-fg truncate">
                {meta.label}
              </h4>
              <span
                className={cn(
                  "px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider",
                  toolCall.status === "completed"
                    ? "bg-surface-2 dark:bg-surface-2 text-fg-2 dark:text-fg-2 border border-line dark:border-line"
                    : toolCall.status === "running"
                    ? "bg-pending-soft dark:bg-pending-soft/60 text-pending dark:text-pending border border-pending/30 dark:border-pending/30"
                    : "bg-bad-soft dark:bg-bad-soft/60 text-bad dark:text-bad border border-bad/30 dark:border-bad/30"
                )}
              >
                {toolCall.status}
              </span>
            </div>
            <p className="text-[11px] text-muted dark:text-muted truncate">
              {meta.description}
              {toolCall.duration && ` • ${formatDuration(toolCall.duration)}`}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {toolCall.status === "running" && (
            <span className="w-2 h-2 rounded-full bg-pending animate-ping" />
          )}
          <ChevronDown
            className={cn(
              "w-4 h-4 text-muted transition-transform duration-200",
              expanded && "rotate-180"
            )}
          />
        </div>
      </div>

      {/* Expanded Details & Practical Interactive Result */}
      {expanded && (
        <div className="border-t border-line dark:border-line bg-inset/50 dark:bg-canvas/50 p-4 space-y-4 text-xs">
          {/* Running State */}
          {toolCall.status === "running" && (
            <div className="flex items-center gap-2.5 text-muted dark:text-muted py-3">
              <span className="w-2 h-2 rounded-full bg-muted animate-bounce" />
              <span className="font-mono text-xs">Executing query in realtime...</span>
            </div>
          )}

          {/* 1. REALTIME JOBS RESULT */}
          {toolCall.status === "completed" && toolCall.name === "search_realtime_jobs" && res?.jobs && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-muted dark:text-muted font-mono text-[11px]">
                <span>
                  Discovered {res.jobs.length} verified roles (Query: "{res.query_used}")
                </span>
                <span className="text-fg-2 dark:text-fg-2 font-semibold">
                  Source: {res.provider || "Google Jobs"}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {res.jobs.map((job: any, i: number) => (
                  <div
                    key={job.id || i}
                    className="p-3.5 rounded-lg border border-line dark:border-line bg-surface dark:bg-surface/70 hover:border-line dark:hover:border-line transition-all flex flex-col justify-between space-y-2.5"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h5 className="font-semibold text-fg dark:text-fg text-xs">
                            {job.title}
                          </h5>
                          <p className="text-[11px] font-medium text-muted dark:text-muted">
                            {job.company}
                          </p>
                        </div>
                        {job.remote && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface-2 dark:bg-surface-2 text-fg-2 dark:text-fg-2 border border-line dark:border-line flex-shrink-0">
                            Remote
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-3 text-[10px] text-muted dark:text-muted mt-2 font-mono">
                        <span className="flex items-center gap-1">
                          <MapPin className="w-3 h-3 text-muted" />
                          {job.location}
                        </span>
                        {job.salary && (
                          <span className="flex items-center gap-1 text-fg dark:text-fg font-semibold">
                            <DollarSign className="w-3 h-3 text-muted" />
                            {job.salary}
                          </span>
                        )}
                      </div>

                      <p className="text-[11px] text-muted dark:text-muted line-clamp-2 mt-2 leading-relaxed">
                        {job.description_snippet}
                      </p>

                      {job.required_skills && job.required_skills.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2.5">
                          {job.required_skills.map((skill: string) => (
                            <span
                              key={skill}
                              className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface-2 dark:bg-surface-2/80 text-fg-2 dark:text-fg-2 border border-line dark:border-line"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="pt-2 border-t border-line dark:border-line flex items-center justify-between gap-2 text-[11px]">
                      <button
                        onClick={() =>
                          onAction?.(
                            `Analyze how well my profile matches the ${job.title} position at ${job.company}`
                          )
                        }
                        className="text-fg-2 dark:text-fg-2 hover:text-fg dark:hover:text-white font-medium flex items-center gap-1 transition-colors"
                      >
                        <Target className="w-3.5 h-3.5" />
                        Run Fit Match
                      </button>

                      <a
                        href={job.application_url}
                        target="_blank"
                        rel="noreferrer"
                        className="px-2.5 py-1 rounded bg-surface dark:bg-surface-2 text-white dark:text-fg font-medium hover:opacity-90 transition-opacity flex items-center gap-1 text-[11px]"
                      >
                        Apply Directly <ExternalLink className="w-3 h-3" />
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 2. PROFILE EXTRACTION RESULT */}
          {toolCall.status === "completed" && toolCall.name === "extract_career_profile" && res?.summary && (
            <div className="space-y-3">
              <div className="p-3.5 rounded-lg border border-line dark:border-line bg-surface dark:bg-surface/60 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h5 className="font-semibold text-fg dark:text-fg text-xs">
                      {res.summary.name || "Candidate"}
                    </h5>
                    <p className="text-[11px] text-muted dark:text-muted">
                      {res.summary.headline} • {res.summary.experience_years} Years Commercial Exp.
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-mono font-bold text-fg dark:text-fg">
                      {res.completeness_pct}%
                    </span>
                    <p className="text-[10px] text-muted font-mono">Profile Completeness</p>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="w-full h-1.5 bg-surface-2 dark:bg-surface-2 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-surface-2 dark:bg-surface-2 rounded-full transition-all"
                    style={{ width: `${res.completeness_pct}%` }}
                  />
                </div>

                {/* Extracted Skills Chips */}
                <div>
                  <span className="text-[10px] font-mono text-muted uppercase tracking-wider block mb-1.5">
                    Verified Competencies
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {res.summary.skills.map((s: string) => (
                      <span
                        key={s}
                        className="px-2 py-0.5 rounded text-[11px] font-mono bg-surface-2 dark:bg-surface-2 text-fg dark:text-fg border border-line dark:border-line flex items-center gap-1"
                      >
                        <CheckCircle2 className="w-3 h-3 text-ok" />
                        {s}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Missing critical fields alert if any */}
                {res.missing_critical_fields?.length > 0 && (
                  <div className="p-2.5 rounded border border-pending/30 dark:border-pending/50 bg-pending-soft/50 dark:bg-pending-soft/20 text-[11px] text-pending dark:text-pending flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <AlertCircle className="w-3.5 h-3.5 text-pending dark:text-pending flex-shrink-0" />
                      Recommended addition: {res.missing_critical_fields.join(", ")}
                    </span>
                    <button
                      onClick={() => onAction?.(res.suggested_followups[0] || "Update my profile details")}
                      className="underline font-semibold hover:text-pending dark:hover:text-pending"
                    >
                      Fill Now
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. JOB MATCH MATRIX RESULT */}
          {toolCall.status === "completed" && toolCall.name === "analyze_job_match" && res?.match_percentage !== undefined && (
            <div className="p-3.5 rounded-lg border border-line dark:border-line bg-surface dark:bg-surface/60 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h5 className="font-semibold text-fg dark:text-fg text-xs">
                    {res.job_title} @ {res.company}
                  </h5>
                  <span className="text-[11px] font-medium text-ok dark:text-ok">
                    {res.overall_alignment}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-xl font-mono font-extrabold text-fg dark:text-fg">
                    {res.match_percentage}%
                  </span>
                  <p className="text-[10px] text-muted font-mono">Role Match Score</p>
                </div>
              </div>

              {/* Match Score Bar */}
              <div className="w-full h-2 bg-surface-2 dark:bg-surface-2 rounded-full overflow-hidden">
                <div
                  className="h-full bg-surface-2 dark:bg-surface-2 rounded-full transition-all duration-500"
                  style={{ width: `${res.match_percentage}%` }}
                />
              </div>

              {/* Matched vs Missing Skills */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                <div>
                  <span className="text-[10px] font-mono text-muted uppercase tracking-wider block mb-1">
                    Matched Skills ({res.matched_skills.length})
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {res.matched_skills.map((s: string) => (
                      <span
                        key={s}
                        className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface-2 dark:bg-surface-2 text-fg dark:text-fg border border-line dark:border-line"
                      >
                        ✓ {s}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <span className="text-[10px] font-mono text-muted uppercase tracking-wider block mb-1">
                    Skill Gaps / Enhancements ({res.missing_skills.length})
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {res.missing_skills.map((s: string) => (
                      <span
                        key={s}
                        className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-pending-soft dark:bg-pending-soft/40 text-pending dark:text-pending border border-pending/30 dark:border-pending/30"
                      >
                        • {s}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Action Plan */}
              {res.action_plan && (
                <div className="border-t border-line dark:border-line pt-2 text-[11px] space-y-1">
                  <span className="font-semibold text-fg-2 dark:text-fg-2">
                    Recommended Bridge Strategy:
                  </span>
                  <ul className="list-disc pl-4 text-muted dark:text-muted space-y-0.5">
                    {res.action_plan.map((act: string, idx: number) => (
                      <li key={idx}>{act}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* 4. ATS SCORE REPORT */}
          {toolCall.status === "completed" && toolCall.name === "calculate_ats_score" && res?.overall_score !== undefined && (
            <div className="p-3.5 rounded-lg border border-line dark:border-line bg-surface dark:bg-surface/60 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h5 className="font-semibold text-fg dark:text-fg text-xs">
                    ATS Resume Health Diagnostic
                  </h5>
                  <p className="text-[11px] text-muted">
                    Algorithmic Screening Rating:{" "}
                    <strong className="text-fg dark:text-fg">{res.rating}</strong>
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-2xl font-mono font-extrabold text-fg dark:text-fg">
                    {res.overall_score}
                  </span>
                  <span className="text-xs text-muted">/100</span>
                </div>
              </div>

              {/* Category Health Bars */}
              {res.categories && (
                <div className="space-y-2 pt-2 border-t border-line dark:border-line">
                  {Object.entries(res.categories).map(([k, cat]: any) => (
                    <div key={k} className="space-y-0.5">
                      <div className="flex justify-between text-[11px]">
                        <span className="font-medium text-fg-2 dark:text-fg-2">
                          {cat.label}
                        </span>
                        <span className="font-mono text-muted">{cat.score}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-surface-2 dark:bg-surface-2 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-surface-2 dark:bg-surface-2 rounded-full"
                          style={{ width: `${cat.score}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Recommendations */}
              {res.high_impact_recommendations && (
                <div className="border-t border-line dark:border-line pt-2 text-[11px] space-y-1">
                  <span className="font-semibold text-fg dark:text-fg">
                    Priority Fixes:
                  </span>
                  <ul className="list-disc pl-4 text-muted dark:text-muted space-y-0.5">
                    {res.high_impact_recommendations.map((rec: string, idx: number) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* 5. TAILORED RESUME RESULT */}
          {toolCall.status === "completed" && toolCall.name === "generate_tailored_resume" && res?.header && (
            <div className="p-3.5 rounded-lg border border-line dark:border-line bg-surface dark:bg-surface/60 space-y-3 font-sans">
              <div className="flex items-center justify-between pb-2 border-b border-line dark:border-line">
                <div>
                  <h5 className="font-bold text-sm text-fg dark:text-fg">
                    {res.header.name}
                  </h5>
                  <p className="text-[11px] text-muted font-mono">{res.target_role}</p>
                </div>
                <button
                  onClick={() =>
                    handleCopy(
                      "resume",
                      `# ${res.header.name}\n${res.target_role}\n\n## Executive Summary\n${res.executive_summary}\n\n## Experience\n` +
                        res.tailored_experience
                          ?.map(
                            (e: any) =>
                              `### ${e.title} @ ${e.company} (${e.period})\n` +
                              e.bullets?.map((b: string) => `- ${b}`).join("\n")
                          )
                          .join("\n\n")
                    )
                  }
                  className="px-2.5 py-1 border border-line dark:border-line hover:bg-surface-2 dark:hover:bg-surface-2 rounded text-[11px] font-medium flex items-center gap-1 transition-colors"
                >
                  {copiedId === "resume" ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-ok" /> Copied Markdown
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" /> Copy Document
                    </>
                  )}
                </button>
              </div>

              {/* Summary */}
              <div>
                <span className="text-[10px] font-mono text-muted uppercase tracking-wider block mb-1">
                  Executive Summary
                </span>
                <p className="text-fg-2 dark:text-fg-2 text-[11px] leading-relaxed">
                  {res.executive_summary}
                </p>
              </div>

              {/* Experience Highlights */}
              <div className="space-y-2">
                <span className="text-[10px] font-mono text-muted uppercase tracking-wider block">
                  Tailored Work History
                </span>
                {res.tailored_experience?.map((exp: any, idx: number) => (
                  <div key={idx} className="p-2 rounded bg-inset dark:bg-canvas/60 border border-line dark:border-line">
                    <div className="flex justify-between font-semibold text-fg dark:text-fg text-[11px]">
                      <span>{exp.title}</span>
                      <span className="font-mono text-[10px] text-muted">{exp.period}</span>
                    </div>
                    <p className="text-[10px] text-muted mb-1.5">{exp.company} • {exp.location}</p>
                    <ul className="list-disc pl-4 text-muted dark:text-muted text-[11px] space-y-1">
                      {exp.bullets?.map((b: string, bIdx: number) => (
                        <li key={bIdx}>{b}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>

              {/* Action Banner: Find Jobs for this CV */}
              <div className="pt-2 border-t border-line dark:border-line flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 bg-gradient-to-r from-accent-soft/70 to-accent-soft/70 dark:from-accent-soft/30 dark:to-accent-soft/30 p-3 rounded-lg">
                <div>
                  <span className="text-xs font-bold text-accent dark:text-accent flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-accent dark:text-accent" /> Start Finding Relevant Jobs for this CV
                  </span>
                  <p className="text-[11px] text-muted dark:text-muted">
                    Search active market openings aligned with {res.target_role}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => onAction?.(`Search live jobs for ${res.target_role}`)}
                    className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accent text-white font-semibold text-xs transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer"
                  >
                    <Search className="w-3.5 h-3.5" />
                    <span>Search in Chat</span>
                  </button>
                  <a
                    href={`/jobs?query=${encodeURIComponent(res.target_role)}&source=cv`}
                    className="px-3 py-1.5 rounded-lg bg-surface dark:bg-surface-2 hover:bg-surface-2 dark:hover:bg-line-strong text-fg dark:text-fg border border-line dark:border-line-strong font-semibold text-xs transition-colors flex items-center gap-1.5 shadow-2xs cursor-pointer"
                  >
                    <Briefcase className="w-3.5 h-3.5 text-accent dark:text-accent" />
                    <span>Open in Jobs Page</span>
                  </a>
                </div>
              </div>
            </div>
          )}

          {/* 6. OUTREACH & COVER LETTER */}
          {toolCall.status === "completed" && toolCall.name === "draft_application_materials" && res?.cold_email && (
            <div className="p-3.5 rounded-lg border border-line dark:border-line bg-surface dark:bg-surface/60 space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-line dark:border-line">
                <span className="font-semibold text-fg dark:text-fg text-xs">
                  Recruiter Outreach Package ({res.target_company})
                </span>
                <button
                  onClick={() =>
                    handleCopy(
                      "cold_email",
                      `Subject: ${res.cold_email.subject}\n\n${res.cold_email.body}`
                    )
                  }
                  className="px-2.5 py-1 border border-line dark:border-line hover:bg-surface-2 dark:hover:bg-surface-2 rounded text-[11px] font-medium flex items-center gap-1 transition-colors"
                >
                  {copiedId === "cold_email" ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-ok" /> Copied Email
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" /> Copy Email
                    </>
                  )}
                </button>
              </div>

              {/* Cold Email */}
              <div className="p-2.5 rounded bg-inset dark:bg-canvas/60 border border-line dark:border-line space-y-1.5">
                <span className="text-[10px] font-mono text-muted">
                  Subject: <strong>{res.cold_email.subject}</strong>
                </span>
                <pre className="whitespace-pre-wrap font-sans text-[11px] text-fg-2 dark:text-fg-2 leading-relaxed">
                  {res.cold_email.body}
                </pre>
              </div>

              {/* LinkedIn Note */}
              {res.linkedin_outreach && (
                <div className="p-2 rounded bg-inset dark:bg-canvas/60 border border-line dark:border-line flex items-center justify-between">
                  <span className="text-[11px] text-muted dark:text-muted">
                    LinkedIn Note: "{res.linkedin_outreach.connection_note}"
                  </span>
                  <button
                    onClick={() => handleCopy("li", res.linkedin_outreach.connection_note)}
                    className="text-muted dark:text-fg-2 hover:text-fg dark:hover:text-white p-1"
                    title="Copy note"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* 7. CAREER ROADMAP */}
          {toolCall.status === "completed" && toolCall.name === "build_career_roadmap" && res?.phases && (
            <div className="p-3.5 rounded-lg border border-line dark:border-line bg-surface dark:bg-surface/60 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h5 className="font-semibold text-fg dark:text-fg text-xs">
                    Career Trajectory: {res.current_role} → {res.target_milestone}
                  </h5>
                  <p className="text-[11px] text-ok dark:text-ok font-mono">
                    Projected Comp Growth: {res.estimated_salary_growth?.potential_increase}
                  </p>
                </div>
                <span className="text-xs font-mono font-bold text-fg-2 dark:text-fg-2">
                  {res.timeline_months} Month Sprint
                </span>
              </div>

              {/* Phases */}
              <div className="space-y-2 pt-1">
                {res.phases.map((ph: any, idx: number) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded border border-line dark:border-line bg-inset dark:bg-canvas/50 space-y-1.5"
                  >
                    <div className="flex justify-between items-center text-[11px]">
                      <span className="font-semibold text-fg dark:text-fg">
                        {ph.phase}
                      </span>
                      <span className="text-[10px] font-mono text-muted">{ph.timeframe}</span>
                    </div>
                    <ul className="list-disc pl-4 text-muted dark:text-muted text-[11px] space-y-0.5">
                      {ph.objectives?.map((obj: string, oIdx: number) => (
                        <li key={oIdx}>{obj}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Raw Arguments & Result Toggle for Debug / Verification */}
          <details className="pt-2 border-t border-line dark:border-line text-[10px] text-muted">
            <summary className="cursor-pointer hover:text-muted dark:hover:text-fg font-mono">
              View Raw JSON Telemetry
            </summary>
            <div className="mt-2 space-y-2 font-mono">
              <div className="bg-surface-2 dark:bg-canvas p-2.5 rounded overflow-x-auto max-h-36">
                <span className="text-muted font-bold block mb-1">Arguments:</span>
                <code>{JSON.stringify(toolCall.arguments, null, 2)}</code>
              </div>
              {toolCall.result !== undefined && (
                <div className="bg-surface-2 dark:bg-canvas p-2.5 rounded overflow-x-auto max-h-48">
                  <span className="text-muted font-bold block mb-1">Result:</span>
                  <code>{JSON.stringify(toolCall.result, null, 2)}</code>
                </div>
              )}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

export function ToolCallTimeline({
  toolCalls,
  onAction,
}: {
  toolCalls: ToolCall[];
  onAction?: (action: string, payload?: unknown) => void;
}) {
  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="space-y-2.5 my-2">
      <div className="flex items-center justify-between text-muted text-[11px] font-mono">
        <span className="flex items-center gap-1.5 font-medium">
          <Layers className="w-3.5 h-3.5 text-muted" />
          Active Tool Pipeline ({toolCalls.length})
        </span>
        <span>
          {toolCalls.filter((t) => t.status === "completed").length} Completed •{" "}
          {toolCalls.filter((t) => t.status === "running").length} In Flight
        </span>
      </div>

      <div className="space-y-2">
        {toolCalls.map((tc) => (
          <ToolCallCard key={tc.id} toolCall={tc} onAction={onAction} />
        ))}
      </div>
    </div>
  );
}