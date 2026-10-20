'use client';

import React, { useState, useEffect, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { FormattedJobDescription } from '@/components/FormattedJobDescription';
import {
  Search,
  MapPin,
  Briefcase,
  DollarSign,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Bookmark,
  Sparkles,
  Filter,
  Building2,
  ShieldCheck,
  X,
  RefreshCw,
  Globe,
  Award,
  Send,
  ArrowRight
} from 'lucide-react';

interface Evidence {
  evidence_type?: string;
  career_profile_fact_path?: string;
  job_requirement_text?: string;
  explanation?: string;
}

interface MatchDetails {
  overall_alignment: string;
  matched_requirements?: string[];
  gaps?: string[];
  evidence?: Evidence[];
}

interface JobItem {
  id: number;
  title: string;
  company: string;
  location: string;
  country?: string;
  remote: boolean;
  employment_type?: string;
  salary?: string;
  description?: string;
  requirements?: string[];
  preferred_skills?: string[];
  responsibilities?: string[];
  technologies?: string[];
  seniority?: string;
  application_url?: string;
  alignment?: string;
  match_score?: number;
  badge?: string;
  matched_skills?: string[];
  missing_skills?: string[];
  recommendation?: string;
  match?: MatchDetails;
}

const COUNTRIES = [
  { code: 'ALL', label: 'All Countries', flag: '🌍' },
  { code: 'Pakistan', label: 'Pakistan', flag: '🇵🇰' },
  { code: 'United States', label: 'United States', flag: '🇺🇸' },
  { code: 'United Kingdom', label: 'United Kingdom', flag: '🇬🇧' },
  { code: 'Canada', label: 'Canada', flag: '🇨🇦' },
  { code: 'United Arab Emirates', label: 'UAE / Gulf', flag: '🇦🇪' },
  { code: 'Germany', label: 'Germany', flag: '🇩🇪' },
  { code: 'Remote Worldwide', label: 'Remote', flag: '🌐' },
];

function JobsContent() {
  const searchParams = useSearchParams();
  const queryParam = searchParams.get('query') || searchParams.get('role');
  const sourceParam = searchParams.get('source');
  const fromCv = searchParams.get('from') === 'cv';

  const [viewMode, setViewMode] = useState<'all' | 'recommended' | 'saved'>('recommended');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [recommendations, setRecommendations] = useState<JobItem[]>([]);
  const [candidateSkills, setCandidateSkills] = useState<string[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedCountry, setSelectedCountry] = useState<string>('ALL');
  const [filterRemote, setFilterRemote] = useState<boolean | null>(null);
  const [filterAlignment, setFilterAlignment] = useState<string>('ALL');
  const [selectedJob, setSelectedJob] = useState<JobItem | null>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'match'>('overview');
  const [savedJobs, setSavedJobs] = useState<Set<number>>(new Set());
  const [isMatching, setIsMatching] = useState(false);
  const [cvSearchActive, setCvSearchActive] = useState(false);
  const [cvInfo, setCvInfo] = useState<{ query: string; location?: string | null; providers?: Record<string, any> } | null>(null);
  const [cvLoading, setCvLoading] = useState(false);

  /** Upload-your-CV quick path: the Job Agent searches live jobs for the CV's role and location. */
  const runCvSearch = async () => {
    setCvLoading(true);
    setLoading(true);
    setSearchError(null);
    let profileData: any = null;
    try { const raw = sessionStorage.getItem('jobpilot_cv_profile'); if (raw) profileData = JSON.parse(raw); } catch { /* ignore */ }
    try {
      const data = await apiFetch('/jobs/from-cv', {
        method: 'POST',
        body: JSON.stringify(profileData ? { profile_data: profileData } : {}),
      });
      setRecommendations(data.results || []);
      if (Array.isArray(data.candidate_skills)) setCandidateSkills(data.candidate_skills);
      setCvInfo({ query: data.query, location: data.location, providers: data.provider_status });
      setSearchQuery(data.query || '');
      setCvSearchActive(true);
      setViewMode('recommended');
      if (!data.results || data.results.length === 0) {
        setSearchError(`No live jobs found for "${data.query}"${data.location ? ` in ${data.location}` : ''}. Try another location below.`);
      }
    } catch (err: any) {
      setSearchError(`Could not find jobs for your CV: ${err.message || err}`);
    } finally {
      setCvLoading(false);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (fromCv) runCvSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromCv]);

  const loadJobs = async (countryFilter: string = selectedCountry) => {
    setLoading(true);
    setSearchError(null);
    try {
      const url = countryFilter !== 'ALL' 
        ? `/jobs/?country=${encodeURIComponent(countryFilter)}`
        : '/jobs/';
      const data = await apiFetch(url);
      if (Array.isArray(data)) {
        setJobs(data);
      }
    } catch (err: any) {
      console.warn('Failed to load backend jobs:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadRecommendations = async () => {
    setLoading(true);
    try {
      const recData = await apiFetch('/jobs/recommendations?limit=30');
      if (recData?.results) {
        setRecommendations(recData.results);
        if (recData.candidate_skills) {
          setCandidateSkills(recData.candidate_skills);
        }
      }
    } catch (err: any) {
      console.warn('Failed to load job recommendations:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRecommendations();
    loadJobs(selectedCountry);
  }, [selectedCountry]);

  // Handle incoming query param from CV builder
  useEffect(() => {
    if (queryParam) {
      setSearchQuery(queryParam);
      setCvSearchActive(true);
      handleSearch(queryParam, selectedCountry);
    }
  }, [queryParam]);

  const handleSearch = async (queryToSearch: string, countryToUse: string = selectedCountry) => {
    if (!queryToSearch.trim()) return;
    setLoading(true);
    setSearchError(null);
    setViewMode('all');
    try {
      const countryParam = countryToUse !== 'ALL' ? `&country=${encodeURIComponent(countryToUse)}` : '';
      const data = await apiFetch(`/jobs/search?query=${encodeURIComponent(queryToSearch)}${countryParam}`, {
        method: 'POST'
      });
      if (data.results && data.results.length > 0) {
        setJobs(data.results);
      } else if (data.results && data.results.length === 0) {
        setSearchError('No jobs found for this query. Try a different search term.');
      }
    } catch (err: any) {
      const msg = err.message || String(err);
      setSearchError(`Job search failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRunMatch = async (jobId: number) => {
    setIsMatching(true);
    try {
      const matchData = await apiFetch(`/jobs/${jobId}/match`, {
        method: 'POST'
      });
      setSelectedJob(prev => prev ? {
        ...prev,
        alignment: matchData.overall_alignment,
        match: matchData
      } : null);
      setSelectedJob(prev => prev ? { ...prev, match_score: matchData.match_score ?? prev.match_score } : null);
      setJobs(prev => prev.map(j => j.id === jobId ? { ...j, alignment: matchData.overall_alignment, match_score: matchData.match_score ?? j.match_score } : j));
      setRecommendations(prev => prev.map(j => j.id === jobId ? { ...j, alignment: matchData.overall_alignment, match_score: matchData.match_score ?? j.match_score } : j));
    } catch (err) {
      console.error('Match evaluation failed:', err);
    } finally {
      setIsMatching(false);
    }
  };

  const toggleSaveJob = (id: number) => {
    setSavedJobs(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const currentList = viewMode === 'recommended' 
    ? recommendations 
    : viewMode === 'saved' 
    ? jobs.filter(j => savedJobs.has(j.id))
    : jobs;

  const filteredJobs = currentList.filter(job => {
    if (filterRemote !== null && job.remote !== filterRemote) return false;
    if (filterAlignment !== 'ALL' && job.alignment !== filterAlignment) return false;
    if (selectedCountry !== 'ALL') {
      const cLower = selectedCountry.toLowerCase();
      const jobCLower = (job.country || '').toLowerCase();
      const jobLocLower = (job.location || '').toLowerCase();
      if (!jobCLower.includes(cLower) && !jobLocLower.includes(cLower)) return false;
    }
    return true;
  });

  return (
    <AppShell>
      <div className="space-y-8">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-line pb-6">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/20 bg-accent-soft text-xs font-mono text-accent mb-2 font-medium shadow-2xs">
              <Sparkles className="w-3.5 h-3.5 text-accent" />
              <span>Real-Time Job Intelligence & CV Match Engine</span>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-fg">
              Jobs & Career Opportunities
            </h1>
            <p className="text-xs md:text-sm text-muted mt-1">
              Live market opportunities matched against your verified CV and skills.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => { try { sessionStorage.removeItem('jobpilot_cv_profile'); } catch { /* ignore */ } runCvSearch(); }}
              disabled={cvLoading}
              className="px-3.5 py-2 rounded-xl bg-accent text-white text-xs font-bold flex items-center gap-1.5 hover:opacity-90 shadow-2xs disabled:opacity-60"
            >
              <Sparkles className={`w-3.5 h-3.5 ${cvLoading ? 'animate-spin' : ''}`} /> {cvLoading ? 'Searching live jobs…' : 'Find jobs for my CV'}
            </button>
            <button
              onClick={() => { loadRecommendations(); loadJobs(); }}
              className="px-3.5 py-2 rounded-xl bg-surface border border-line text-xs font-bold text-fg flex items-center gap-1.5 hover:bg-inset shadow-2xs hover:border-accent/50 transition-all cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-accent ${loading ? 'animate-spin' : ''}`} /> Refresh Feed
            </button>
          </div>
        </div>

        {/* CV Match Active Banner */}
        {cvSearchActive && searchQuery && (
          <div className="p-4 bg-gradient-to-r from-accent-soft to-accent-soft border border-accent/30 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs animate-in fade-in duration-300">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-accent text-white flex items-center justify-center shrink-0 shadow-xs">
                <Sparkles className="w-5 h-5 text-accent" />
              </div>
              <div>
                <span className="font-bold text-xs text-accent block">
                  Jobs for your CV: <span className="text-fg underline">{cvInfo?.query || searchQuery}</span>
                  {cvInfo?.location ? <> in <span className="text-fg underline">{cvInfo.location}</span></> : null}
                </span>
                <p className="text-[11px] text-fg-2">
                  Live jobs from Google Jobs and LinkedIn, ranked by how many of each job&apos;s skills are in your CV.
                  {cvInfo?.providers && Object.entries(cvInfo.providers).filter(([, s]: any) => !s.ok).length > 0 && (
                    <> Unavailable right now: {Object.entries(cvInfo.providers).filter(([, s]: any) => !s.ok).map(([n]) => n.split(':')[0]).join(', ')}.</>
                  )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => {
                  setCvSearchActive(false);
                  setViewMode('recommended');
                }}
                className="px-3 py-1.5 rounded-lg bg-surface border border-accent/30 text-accent text-xs font-bold hover:bg-accent-soft transition-colors shadow-2xs"
              >
                Reset to All Recommendations
              </button>
            </div>
          </div>
        )}

        {/* View Mode Tabs */}
        <div className="inline-flex flex-wrap p-1.5 bg-surface-2 rounded-2xl border border-line text-xs font-semibold gap-1.5 shadow-2xs">
          <button
            onClick={() => setViewMode('recommended')}
            className={`px-4 py-2.5 rounded-xl transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              viewMode === 'recommended'
                ? 'bg-surface text-accent shadow-xs border border-accent/30 font-bold'
                : 'text-muted hover:text-fg hover:bg-surface/50 border border-transparent'
            }`}
          >
            <Award className={`w-4 h-4 ${viewMode === 'recommended' ? 'text-accent' : 'text-muted'}`} />
            <span>Recommended for You</span>
            <span className={`px-2 py-0.5 rounded-full text-[11px] font-mono font-bold ${
              viewMode === 'recommended' ? 'bg-accent-soft text-accent' : 'bg-line-strong text-fg-2'
            }`}>
              {recommendations.length}
            </span>
          </button>
          
          <button
            onClick={() => setViewMode('all')}
            className={`px-4 py-2.5 rounded-xl transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              viewMode === 'all'
                ? 'bg-surface text-fg shadow-xs border border-line font-bold'
                : 'text-muted hover:text-fg hover:bg-surface/50 border border-transparent'
            }`}
          >
            <Briefcase className={`w-4 h-4 ${viewMode === 'all' ? 'text-accent' : 'text-muted'}`} />
            <span>All Market Jobs</span>
            <span className={`px-2 py-0.5 rounded-full text-[11px] font-mono font-bold ${
              viewMode === 'all' ? 'bg-accent-soft text-accent' : 'bg-line-strong text-fg-2'
            }`}>
              {jobs.length}
            </span>
          </button>
          
          <button
            onClick={() => setViewMode('saved')}
            className={`px-4 py-2.5 rounded-xl transition-all flex items-center gap-2 whitespace-nowrap cursor-pointer ${
              viewMode === 'saved'
                ? 'bg-surface text-fg shadow-xs border border-line font-bold'
                : 'text-muted hover:text-fg hover:bg-surface/50 border border-transparent'
            }`}
          >
            <Bookmark className={`w-4 h-4 ${viewMode === 'saved' ? 'text-accent' : 'text-muted'}`} />
            <span>Saved</span>
            <span className={`px-2 py-0.5 rounded-full text-[11px] font-mono font-bold ${
              viewMode === 'saved' ? 'bg-accent-soft text-accent' : 'bg-line-strong text-fg-2'
            }`}>
              {savedJobs.size}
            </span>
          </button>
        </div>

        {/* Candidate Skills Profile Banner */}
        {candidateSkills.length > 0 && viewMode === 'recommended' && (
          <div className="p-4 bg-surface border border-line rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
            <div>
              <span className="font-semibold text-fg block mb-1">
                Active Skills from Your Career Profile / CV:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {candidateSkills.map((sk, i) => (
                  <span key={i} className="px-2 py-0.5 rounded-md bg-surface-2 border border-line font-mono text-[11px] text-fg">
                    {sk}
                  </span>
                ))}
              </div>
            </div>
            <Link
              href="/profile"
              className="text-fg font-semibold underline shrink-0 flex items-center gap-1"
            >
              <span>Edit CV Profile</span>
              <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
        )}

        {/* Natural Language Search Bar */}
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-subtle w-4 h-4" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch(searchQuery)}
              placeholder="Describe what role you want... (e.g., 'Find remote Python FastAPI jobs' or 'Senior Frontend React Engineer')"
              className="w-full bg-surface border border-line rounded-xl pl-11 pr-32 py-3.5 text-sm text-fg placeholder-faint focus:outline-none focus:border-accent transition-all shadow-xs font-sans"
            />
            <button
              onClick={() => handleSearch(searchQuery)}
              disabled={loading}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 bg-accent hover:bg-accent-hover text-white font-medium px-4 py-2 rounded-lg transition-colors flex items-center gap-1.5 text-xs shadow-xs"
            >
              {loading ? (
                <span>Searching Live...</span>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Discover</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Search Error Banner */}
        {searchError && (
          <div className="p-4 bg-bad-soft border border-bad/30 rounded-xl text-xs text-bad flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block mb-0.5">Search Notice</span>
              {searchError}
            </div>
          </div>
        )}

        {/* Country Selector Tabs Bar */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-fg">
            <Globe className="w-3.5 h-3.5 text-fg" />
            <span>Select Target Location / Market Region:</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 bg-surface p-2.5 rounded-xl border border-line shadow-2xs">
            {COUNTRIES.map((c) => (
              <button
                key={c.code}
                onClick={() => {
                  setSelectedCountry(c.code);
                  if (searchQuery.trim()) {
                    handleSearch(searchQuery, c.code);
                  } else {
                    loadJobs(c.code);
                  }
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  selectedCountry === c.code
                    ? 'bg-accent text-white shadow-xs font-semibold'
                    : 'bg-inset hover:bg-line-strong text-muted hover:text-fg border border-line'
                }`}
              >
                <span>{c.flag}</span>
                <span>{c.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Filter Controls Bar */}
        <div className="flex flex-wrap items-center justify-between gap-4 bg-surface p-3.5 rounded-xl border border-line">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <div className="flex items-center gap-1.5 text-muted font-medium mr-2">
              <Filter className="w-3.5 h-3.5 text-fg" /> Filters:
            </div>

            <button
              onClick={() => setFilterRemote(prev => prev === true ? null : true)}
              className={`px-3 py-1.5 rounded-lg border transition-all ${
                filterRemote === true
                  ? 'bg-accent text-white border-accent font-semibold'
                  : 'bg-inset text-muted border-line hover:text-fg'
              }`}
            >
              Remote Only
            </button>
          </div>

          <div className="text-xs font-mono text-muted">
            Showing <strong className="text-fg">{filteredJobs.length}</strong> opportunities
          </div>
        </div>

        {/* Jobs Layout Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* Job List Column */}
          <div className="lg:col-span-6 space-y-3">
            {loading ? (
              <div className="p-12 text-center text-xs text-muted bg-surface rounded-xl border border-line">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-fg" />
                Searching authentic job feeds across live providers...
              </div>
            ) : filteredJobs.length > 0 ? (
              filteredJobs.map((job) => {
                const isSelected = selectedJob?.id === job.id;
                const isSaved = savedJobs.has(job.id);
                return (
                  <div
                    key={job.id}
                    onClick={() => setSelectedJob(job)}
                    className={`card-base p-4 bg-surface border rounded-xl cursor-pointer transition-all space-y-3 ${
                      isSelected
                        ? 'border-accent shadow-sm ring-1 ring-accent'
                        : 'border-line hover:border-line-strong'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h3 className="text-sm font-bold text-fg hover:underline">
                            {job.title}
                          </h3>
                          {typeof job.match_score === 'number' ? (
                            <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                              job.match_score >= 75 ? 'bg-ok-soft text-ok border-ok/30'
                              : job.match_score >= 50 ? 'bg-accent-soft text-accent border-accent/30'
                              : 'bg-pending-soft text-pending border-pending/30'}`}>
                              {job.match_score}% Match
                            </span>
                          ) : viewMode === 'recommended' && job.alignment ? (
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono border bg-surface-2 text-muted border-line">
                              {job.alignment}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-muted">
                          <span className="flex items-center gap-1 font-medium text-fg">
                            <Building2 className="w-3.5 h-3.5 text-subtle" />
                            {job.company}
                          </span>
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3.5 h-3.5 text-subtle" />
                            {job.location}
                          </span>
                        </div>
                      </div>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleSaveJob(job.id);
                        }}
                        className={`p-1.5 rounded-lg border transition-colors ${
                          isSaved
                            ? 'bg-accent text-white border-accent'
                            : 'bg-inset text-subtle border-line hover:text-fg'
                        }`}
                      >
                        <Bookmark className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {job.recommendation && (
                      <p className="text-[11px] text-ok bg-ok-soft p-2 rounded-lg border border-ok/30">
                        ★ {job.recommendation}
                      </p>
                    )}

                    {/* Matched Skills Badges */}
                    {job.matched_skills && job.matched_skills.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1">
                        {job.matched_skills.slice(0, 4).map((sk, i) => (
                          <span key={i} className="px-2 py-0.5 rounded text-[10px] font-mono bg-surface-2 border border-line text-fg">
                            ✓ {sk}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="pt-2 border-t border-line flex items-center justify-between text-[11px]">
                      <span className="text-muted font-mono">
                        {job.employment_type || 'Full-time'} · {job.remote ? 'Remote' : 'On-site'}
                      </span>
                      <span className="font-semibold text-fg flex items-center gap-1">
                        View Dossier <ArrowRight className="w-3 h-3" />
                      </span>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="p-12 text-center text-xs text-muted bg-surface rounded-xl border border-line">
                No jobs found matching your filters. Try clearing country or remote filters.
              </div>
            )}
          </div>

          {/* Job Detail Column */}
          <div className="lg:col-span-6 sticky top-20">
            {selectedJob ? (
              <div className="card-base p-6 bg-surface border border-line rounded-xl space-y-6 shadow-sm">
                
                {/* Header Actions */}
                <div className="flex items-start justify-between gap-4 border-b border-line pb-5">
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <h2 className="text-lg font-bold text-fg">{selectedJob.title}</h2>
                      {typeof selectedJob.match_score === 'number' && (
                        <span className="px-2.5 py-0.5 rounded text-xs font-mono font-bold bg-ok-soft text-ok border border-ok/30">
                          {selectedJob.match_score}% Match
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted">
                      <span className="font-medium text-fg flex items-center gap-1">
                        <Building2 className="w-3.5 h-3.5 text-subtle" /> {selectedJob.company}
                      </span>
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3.5 h-3.5 text-subtle" /> {selectedJob.location}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => handleRunMatch(selectedJob.id)}
                      disabled={isMatching}
                      className="px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white font-medium text-xs transition-colors flex items-center gap-1.5 shadow-xs"
                    >
                      <Sparkles className={`w-3.5 h-3.5 ${isMatching ? 'animate-spin' : ''}`} />
                      <span>{isMatching ? 'Evaluating...' : 'Match CV'}</span>
                    </button>
                  </div>
                </div>

                {/* Tab Navigation */}
                <div className="flex border-b border-line text-xs font-semibold gap-6">
                  <button
                    onClick={() => setActiveTab('overview')}
                    className={`pb-2 transition-colors relative ${
                      activeTab === 'overview' ? 'text-fg' : 'text-muted hover:text-fg'
                    }`}
                  >
                    Job Overview
                    {activeTab === 'overview' && (
                      <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
                    )}
                  </button>
                  <button
                    onClick={() => setActiveTab('match')}
                    className={`pb-2 transition-colors relative ${
                      activeTab === 'match' ? 'text-fg' : 'text-muted hover:text-fg'
                    }`}
                  >
                    CV Alignment Matrix
                    {activeTab === 'match' && (
                      <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent" />
                    )}
                  </button>
                </div>

                {/* Tab Content */}
                {activeTab === 'overview' ? (
                  <div className="space-y-5 text-xs text-fg">
                    {selectedJob.description ? (
                      <FormattedJobDescription
                        description={selectedJob.description}
                        requirements={selectedJob.requirements}
                        preferredSkills={selectedJob.preferred_skills}
                        responsibilities={selectedJob.responsibilities}
                        technologies={selectedJob.technologies}
                        location={selectedJob.location}
                        country={selectedJob.country}
                        employmentType={selectedJob.employment_type}
                        salary={selectedJob.salary}
                        company={selectedJob.company}
                      />
                    ) : (
                      <p className="text-muted">No detailed description provided for this job listing.</p>
                    )}

                    {selectedJob.application_url && (
                      <div className="pt-4 border-t border-line flex items-center justify-between">
                        <Link
                          href={`/applications?job_id=${selectedJob.id}`}
                          className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white font-medium text-xs transition-all flex items-center gap-2 shadow-xs"
                        >
                          <Send className="w-3.5 h-3.5" />
                          <span>Create Tailored Application</span>
                        </Link>
                        <a
                          href={selectedJob.application_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-muted hover:text-fg underline flex items-center gap-1 font-mono"
                        >
                          <span>Official Portal</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-4 text-xs">
                    <div className="p-4 bg-inset rounded-xl border border-line space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-fg">Alignment Level</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-ok-soft text-ok border border-ok/30">
                          {selectedJob.alignment || selectedJob.badge || 'Not evaluated yet — run the match'}
                        </span>
                      </div>
                      <p className="text-[11px] text-muted">
                        Evaluated strictly against your confirmed facts in Canonical Career Profile.
                      </p>
                    </div>

                    {selectedJob.match?.matched_requirements && selectedJob.match.matched_requirements.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="font-semibold text-fg">Matched Requirements:</span>
                        <ul className="space-y-1">
                          {selectedJob.match.matched_requirements.map((r, i) => (
                            <li key={i} className="flex items-start gap-1.5 text-ok">
                              <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                              <span>{r}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {selectedJob.match?.gaps && selectedJob.match.gaps.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="font-semibold text-fg">Skill Gaps / Development Areas:</span>
                        <ul className="space-y-1">
                          {selectedJob.match.gaps.map((g, i) => (
                            <li key={i} className="flex items-start gap-1.5 text-pending">
                              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                              <span>{g}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <Link
                      href={`/applications?job_id=${selectedJob.id}`}
                      className="w-full py-2.5 rounded-lg bg-accent hover:bg-accent-hover text-white font-medium text-xs transition-all flex items-center justify-center gap-2 shadow-xs mt-4"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>Prepare Application with Grounded Evidence</span>
                    </Link>
                  </div>
                )}

              </div>
            ) : (
              <div className="p-12 text-center text-xs text-muted bg-surface rounded-xl border border-line">
                Select a job from the list to inspect requirements, match analysis, and application actions.
              </div>
            )}
          </div>

        </div>

      </div>
    </AppShell>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={
      <AppShell>
        <div className="p-8 text-center text-xs text-muted flex items-center justify-center gap-2">
          <RefreshCw className="w-4 h-4 animate-spin text-accent" />
          <span>Loading Career Intelligence...</span>
        </div>
      </AppShell>
    }>
      <JobsContent />
    </Suspense>
  );
}
