'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import {
  Building2,
  Mail,
  FileText,
  Sparkles,
  CheckCircle2,
  ShieldCheck,
  ExternalLink,
  RefreshCw,
  Send,
  Lock,
  UserCheck,
  X,
  Plus,
  Briefcase,
  Layers,
  ChevronRight,
  AlertCircle
} from 'lucide-react';

interface CompanyResearch {
  status?: 'found' | 'not_found' | 'unavailable' | 'not_researched' | 'unverified';
  message?: string;
  official_website?: string;
  sources?: { source_url: string; provider: string }[];
  claims?: { claim_text: string; source_url: string; fact_type: string }[];
  overview?: string;
  industry?: string;
  products_services?: string[];
  technology_info?: string[];
  mission_info?: string;
  careers_url?: string;
}

interface ApplicationData {
  id: number;
  status: string;
  job: {
    id: number;
    title: string;
    company: string;
    location: string;
    remote: boolean;
    salary?: string;
    application_url?: string;
    contact_emails?: string[];
  };
  company: {
    id: number;
    name: string;
    official_website?: string;
    research?: CompanyResearch;
  };
  resume_version_id?: number;
  email_version?: {
    tone: string;
    subject: string;
    body: string;
    greeting?: string;
    closing?: string;
    referenced_profile_facts?: string[];
    referenced_job_requirements?: string[];
    referenced_company_claims?: string[];
    removed_claims?: string[];
    method?: 'ai' | 'template';
  };
  contacts?: Contact[];
  cv_attachment?: { source: 'resume_version' | 'profile' | null; version_id?: number | null; label: string };
  gmail_draft?: {
    draft_id: string;
    recipient: string;
    subject: string;
    created_at: string;
  };
}

interface Contact {
  email: string;
  kind: 'job_posting' | 'hiring' | 'general' | 'other';
  source_url: string;
  on_site?: boolean;
}

const CONTACT_LABEL: Record<string, string> = {
  job_posting: 'From the job posting', hiring: 'HR / careers', general: 'General company email', other: 'Company email',
};

interface ApplicationSummary {
  id: number;
  job_id: number;
  job_title: string;
  company_name: string;
  status: string;
  created_at?: string;
}

function ApplicationStudioContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const jobIdParam = searchParams.get('job_id');
  const appIdParam = searchParams.get('id');

  const [apps, setApps] = useState<ApplicationSummary[]>([]);
  const [selectedApp, setSelectedApp] = useState<ApplicationData | null>(null);
  const [availableJobs, setAvailableJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // User Account Info
  const [currentUserEmail, setCurrentUserEmail] = useState<string>('');
  const [currentUserName, setCurrentUserName] = useState<string>('');

  // Email Studio State
  const [emailTone, setEmailTone] = useState<string>('Formal');
  const [emailSubject, setEmailSubject] = useState<string>('');
  const [emailBody, setEmailBody] = useState<string>('');
  const [isGeneratingEmail, setIsGeneratingEmail] = useState(false);
  const [isResearchingCompany, setIsResearchingCompany] = useState(false);

  // Gmail Connection & Draft Modal State
  const [gmailConnected, setGmailConnected] = useState<boolean>(false);
  const [gmailEmail, setGmailEmail] = useState<string>('');
  const [gmailConfigError, setGmailConfigError] = useState<string | null>(null);
  const [isConnectingGmail, setIsConnectingGmail] = useState(false);
  const [showDraftModal, setShowDraftModal] = useState(false);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [findingRecipient, setFindingRecipient] = useState(false);
  const [recipientMessage, setRecipientMessage] = useState('');
  const [searchedFor, setSearchedFor] = useState<number | null>(null);
  const [draftRecipient, setDraftRecipient] = useState('');
  const [includeAttachment, setIncludeAttachment] = useState(true);
  const [userConfirmed, setUserConfirmed] = useState(false);
  const [isCreatingDraft, setIsCreatingDraft] = useState(false);
  const [draftSuccessMsg, setDraftSuccessMsg] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);

  const loadAccountInfo = async () => {
    try {
      const me = await apiFetch('/auth/me');
      if (me && me.email) {
        setCurrentUserEmail(me.email);
        setCurrentUserName(me.name || me.email.split('@')[0]);
      }
    } catch {
      const stored = typeof window !== 'undefined' ? localStorage.getItem('user_email') : null;
      if (stored) {
        setCurrentUserEmail(stored);
        setCurrentUserName(stored.split('@')[0]);
      }
    }
  };

  const loadGmailStatus = async () => {
    try {
      const status = await apiFetch('/gmail/status');
      setGmailConnected(status.connected === true);
      setGmailEmail(status.email || '');
      if (status.configuration_error) {
        setGmailConfigError(status.configuration_error);
      }
    } catch (err) {
      setGmailConnected(false);
    }
  };

  const handleConnectGmail = async () => {
    setIsConnectingGmail(true);
    try {
      const res = await apiFetch('/gmail/oauth/start');
      if (res && res.oauth_url) {
        window.location.href = res.oauth_url;
      }
    } catch (err: any) {
      console.error('Gmail OAuth start failed:', err);
      setGmailConfigError(err?.message || 'Failed to initiate Google OAuth. Please check client credentials in backend/.env');
    } finally {
      setIsConnectingGmail(false);
    }
  };

  const fetchFullApplication = async (appId: number) => {
    try {
      const fullApp = await apiFetch(`/applications/${appId}`);
      setSelectedApp(fullApp);
      
      // Run company research once (the backend caches it per company)
      const researchStatus = fullApp.company?.research?.status;
      if (fullApp.company?.id && (!researchStatus || researchStatus === 'not_researched')) {
        setIsResearchingCompany(true);
        apiFetch(`/companies/${fullApp.company.id}/research?force=false`, { method: 'POST' })
          .then((resData) => {
            setSelectedApp(prev => prev && prev.id === appId ? {
              ...prev, company: { ...prev.company, official_website: resData.official_website, research: resData }
            } : prev);
          })
          .catch((err) => console.warn('Company research notice:', err))
          .finally(() => setIsResearchingCompany(false));
      }

      if (fullApp.email_version) {
        setEmailSubject(fullApp.email_version.subject || '');
        setEmailBody(fullApp.email_version.body || '');
        if (fullApp.email_version.tone) {
          setEmailTone(fullApp.email_version.tone);
        }
      } else {
        // Auto-generate grounded email draft if not present yet
        generateEmailForApp(fullApp.id, fullApp.resume_version_id);
      }

      // Only real addresses (job posting, company website, Google) are used; nothing is guessed
      setContacts(fullApp.contacts || []);
      setDraftRecipient(fullApp.contacts?.[0]?.email || fullApp.job?.contact_emails?.[0] || '');
      setRecipientMessage('');
      setSearchedFor(null);
      // Start the recipient search in the background right away, so it is ready before "Create Gmail Draft"
      if (!fullApp.contacts?.length) findRecipient(fullApp.id);
      return fullApp;
    } catch (err: any) {
      console.error(`Failed to fetch full application ${appId}:`, err);
      return null;
    }
  };

  const findRecipient = async (appId: number, force = false) => {
    setFindingRecipient(true);
    setRecipientMessage('');
    try {
      const data = await apiFetch(`/applications/${appId}/find-recipient${force ? '?force=true' : ''}`, { method: 'POST' });
      setContacts(data.contacts || []);
      if (data.recipient) setDraftRecipient(prev => (prev.trim() ? prev : data.recipient));
      setRecipientMessage(data.message || '');
    } catch (err: any) {
      setRecipientMessage(err?.message || 'Could not search for a recipient right now.');
    } finally {
      setFindingRecipient(false);
      setSearchedFor(appId);
    }
  };

  const openDraftModal = () => {
    setShowDraftModal(true);
    if (selectedApp && !draftRecipient.trim() && searchedFor !== selectedApp.id) {
      findRecipient(selectedApp.id);
    }
  };

  const generateEmailForApp = async (appId: number, resumeVersionId?: number) => {
    setIsGeneratingEmail(true);
    try {
      const resData = await apiFetch(`/applications/${appId}/generate-email`, {
        method: 'POST',
        body: JSON.stringify({ tone: emailTone, resume_version_id: resumeVersionId })
      });
      setEmailSubject(resData.subject || '');
      setEmailBody(resData.body || '');
      setSelectedApp(prev => prev && prev.id === appId ? { ...prev, email_version: resData, status: 'DRAFT_READY' } : prev);
    } catch (err) {
      console.warn('Auto email generation warning:', err);
    } finally {
      setIsGeneratingEmail(false);
    }
  };

  const loadAllApplicationsAndJobs = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      // 1. Fetch existing applications list
      const appsData: ApplicationSummary[] = await apiFetch('/applications/');
      const hasApps = Array.isArray(appsData) && appsData.length > 0;
      if (hasApps) {
        setApps(appsData);
      }

      // 2. Fetch jobs list for selector / fallback
      let jobsList: any[] = [];
      try {
        const jData = await apiFetch('/jobs/');
        if (Array.isArray(jData)) {
          jobsList = jData;
          setAvailableJobs(jData);
        }
      } catch (jErr) {
        console.warn('Jobs list fetch notice:', jErr);
      }

      // 3. Determine which application to load
      if (appIdParam) {
        // Load explicitly requested application
        await fetchFullApplication(Number(appIdParam));
      } else if (jobIdParam) {
        // Prepare or fetch application for requested job_id
        const targetJobId = Number(jobIdParam);
        const existingApp = hasApps ? appsData.find(a => a.job_id === targetJobId) : null;
        if (existingApp) {
          await fetchFullApplication(existingApp.id);
        } else {
          // Prepare new application workspace for this job
          const createdApp = await apiFetch('/applications/', {
            method: 'POST',
            body: JSON.stringify({ job_id: targetJobId })
          });
          if (createdApp && createdApp.id) {
            setSelectedApp(createdApp);
            setApps(prev => [
              {
                id: createdApp.id,
                job_id: createdApp.job?.id || targetJobId,
                job_title: createdApp.job?.title || 'Target Job',
                company_name: createdApp.company?.name || 'Company',
                status: createdApp.status || 'PREPARING'
              },
              ...prev.filter(a => a.id !== createdApp.id)
            ]);
            if (createdApp.email_version) {
              setEmailSubject(createdApp.email_version.subject || '');
              setEmailBody(createdApp.email_version.body || '');
            } else {
              generateEmailForApp(createdApp.id, createdApp.resume_version_id);
            }
          }
        }
      } else if (hasApps) {
        // Default to the first application in the list
        await fetchFullApplication(appsData[0].id);
      } else if (jobsList.length > 0) {
        // Auto-prepare application for the first available job so user never gets a blank page
        const firstJob = jobsList[0];
        const createdApp = await apiFetch('/applications/', {
          method: 'POST',
          body: JSON.stringify({ job_id: firstJob.id })
        });
        if (createdApp && createdApp.id) {
          setSelectedApp(createdApp);
          setApps([
            {
              id: createdApp.id,
              job_id: firstJob.id,
              job_title: firstJob.title,
              company_name: firstJob.company,
              status: createdApp.status || 'PREPARING'
            }
          ]);
          if (createdApp.email_version) {
            setEmailSubject(createdApp.email_version.subject || '');
            setEmailBody(createdApp.email_version.body || '');
          } else {
            generateEmailForApp(createdApp.id, createdApp.resume_version_id);
          }
        }
      }
    } catch (err: any) {
      console.error('Applications load error:', err);
      setErrorMsg(err?.message || 'Failed to load applications studio');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAccountInfo();
    loadAllApplicationsAndJobs();
    loadGmailStatus();
  }, [jobIdParam, appIdParam]);

  const handleSelectApp = (appId: number) => {
    fetchFullApplication(appId);
  };

  const handleCreateNewAppForJob = async (jobId: number) => {
    setLoading(true);
    try {
      const createdApp = await apiFetch('/applications/', {
        method: 'POST',
        body: JSON.stringify({ job_id: jobId })
      });
      if (createdApp && createdApp.id) {
        setSelectedApp(createdApp);
        const updatedApps = await apiFetch('/applications/');
        if (Array.isArray(updatedApps)) {
          setApps(updatedApps);
        }
        if (!createdApp.email_version) {
          generateEmailForApp(createdApp.id, createdApp.resume_version_id);
        }
      }
    } catch (err: any) {
      console.error('Create application error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateEmail = async () => {
    if (!selectedApp) return;
    setIsGeneratingEmail(true);
    try {
      const resData = await apiFetch(`/applications/${selectedApp.id}/generate-email`, {
        method: 'POST',
        body: JSON.stringify({ tone: emailTone, resume_version_id: selectedApp.resume_version_id })
      });
      setEmailSubject(resData.subject);
      setEmailBody(resData.body);
      setSelectedApp(prev => prev ? { ...prev, email_version: resData, status: 'DRAFT_READY' } : null);
    } catch (err) {
      console.error('Failed to generate email via backend:', err);
    } finally {
      setIsGeneratingEmail(false);
    }
  };

  const handleTriggerCompanyResearch = async () => {
    if (!selectedApp || !selectedApp.company?.id) return;
    setIsResearchingCompany(true);
    try {
      const data = await apiFetch(`/companies/${selectedApp.company.id}/research`, {
        method: 'POST'
      });
      setSelectedApp(prev => prev ? {
        ...prev, company: { ...prev.company, official_website: data.official_website, research: data }
      } : null);
    } catch (err) {
      console.error('Company research failed:', err);
    } finally {
      setIsResearchingCompany(false);
    }
  };

  const handleCreateGmailDraft = async () => {
    if (!userConfirmed || !draftRecipient.trim()) return;
    if (!selectedApp) return;
    setIsCreatingDraft(true);
    setDraftSuccessMsg(null);
    setDraftError(null);
    try {
      const data = await apiFetch(`/applications/${selectedApp.id}/gmail-draft`, {
        method: 'POST',
        body: JSON.stringify({
          recipient: draftRecipient.trim(),
          subject: emailSubject,
          body: emailBody,
          user_confirmed: true,
          include_attachment: includeAttachment,
          attachment_format: 'pdf'
        })
      });
      setDraftSuccessMsg(data.message || 'Gmail draft created successfully in your Gmail account!');
      setSelectedApp(prev => prev ? {
        ...prev,
        status: 'DRAFT_READY',
        gmail_draft: {
          draft_id: data.draft_id || 'DRAFT_CONFIRMED',
          recipient: data.recipient || draftRecipient,
          subject: data.subject || emailSubject,
          created_at: new Date().toISOString()
        }
      } : null);
      setTimeout(() => setShowDraftModal(false), 2200);
    } catch (err: any) {
      console.error('Draft creation error:', err);
      setDraftError(err?.message || 'Failed to create Gmail draft. Ensure Gmail is connected.');
    } finally {
      setIsCreatingDraft(false);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6">
        
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-line pb-5">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/20 bg-accent-soft text-xs font-semibold text-accent mb-2">
              <Sparkles className="w-3.5 h-3.5 text-accent" />
              <span>Grounded Evidence Assembly & Gmail Integration</span>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-fg">
              Application Studio & Outreach
            </h1>
            <p className="text-xs md:text-sm text-muted mt-1">
              Assemble personalized application packages, research target companies, generate grounded emails, and prepare verified Gmail drafts.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => { loadAllApplicationsAndJobs(); loadGmailStatus(); }}
              className="p-2.5 rounded-xl bg-surface border border-line-strong text-muted hover:text-fg hover:border-accent/60 transition-all shadow-2xs"
              title="Refresh Workspace"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            {/* Gmail Connection Status & Connect Button */}
            {gmailConnected ? (
              <div className="p-2.5 px-4 bg-ok-soft border border-ok/30 rounded-xl flex items-center gap-2.5 text-xs shadow-2xs">
                <span className="w-2.5 h-2.5 rounded-full bg-ok animate-pulse" />
                <span className="font-bold text-ok">
                  Gmail: {gmailEmail}
                </span>
              </div>
            ) : (
              <button
                onClick={handleConnectGmail}
                disabled={isConnectingGmail}
                className="p-2.5 px-4 bg-accent hover:bg-accent-hover text-white rounded-xl flex items-center gap-2 text-xs font-bold transition-all shadow-xs"
              >
                <Mail className="w-4 h-4" />
                <span>{isConnectingGmail ? 'Connecting...' : 'Connect Gmail'}</span>
              </button>
            )}
          </div>
        </div>

        {/* Gmail Config Error Banner */}
        {gmailConfigError && (
          <div className="p-4 bg-pending-soft border border-pending/30 rounded-xl text-xs text-pending flex items-start gap-3 shadow-xs">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-bold block">Gmail Integration Notice</span>
              <p>{gmailConfigError}</p>
            </div>
          </div>
        )}

        {/* Applications Selector Tabs */}
        {apps.length > 0 && (
          <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-line">
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted mr-2 shrink-0 font-mono">
              Active Applications ({apps.length}):
            </span>
            {apps.map((app) => {
              const isActive = selectedApp?.id === app.id;
              return (
                <button
                  key={app.id}
                  onClick={() => handleSelectApp(app.id)}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold shrink-0 transition-all flex items-center gap-2 border ${
                    isActive
                      ? 'bg-accent text-white border-accent shadow-xs'
                      : 'bg-surface text-fg-2 border-line-strong hover:border-accent/60 hover:text-accent'
                  }`}
                >
                  <Briefcase className="w-3.5 h-3.5" />
                  <span className="truncate max-w-[180px]">{app.job_title}</span>
                  <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                    isActive ? 'bg-surface/20 text-white' : 'bg-surface-2 text-muted'
                  }`}>
                    {app.company_name}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {/* Workspace Layout */}
        {loading && !selectedApp ? (
          <div className="p-16 text-center bg-surface rounded-2xl border border-line-strong space-y-3">
            <RefreshCw className="w-6 h-6 animate-spin text-accent mx-auto" />
            <p className="text-xs font-semibold text-muted">Assembling application workspace and evidence...</p>
          </div>
        ) : selectedApp ? (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            
            {/* Left Column: Job Target & Company Intelligence (5 cols) */}
            <div className="lg:col-span-5 space-y-5">
              
              {/* Card 1: Job Target */}
              <div className="p-5 bg-surface border border-line-strong rounded-2xl space-y-3 shadow-xs">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-xs font-bold text-muted">
                      Target Position
                    </span>
                    <h3 className="text-base font-bold text-fg mt-0.5">{selectedApp.job?.title}</h3>
                    <p className="text-xs font-semibold text-accent">{selectedApp.job?.company}</p>
                  </div>
                  <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-ok-soft text-ok border border-ok/30">
                    {selectedApp.status}
                  </span>
                </div>

                <div className="flex flex-wrap gap-1.5 text-xs text-fg-2">
                  {selectedApp.job?.location && (
                    <span className="bg-inset px-2.5 py-1 rounded-lg border border-line">{selectedApp.job.location}</span>
                  )}
                  {selectedApp.job?.salary && (
                    <span className="bg-ok-soft text-ok px-2.5 py-1 rounded-lg border border-ok/30 font-bold">
                      {selectedApp.job.salary}
                    </span>
                  )}
                </div>

                {selectedApp.job?.application_url && (
                  <a
                    href={selectedApp.job.application_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-xs text-accent hover:underline font-bold pt-1"
                  >
                    <span>View Official Job Posting</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>

              {/* Card 2: Company Intelligence */}
              <div className="p-5 bg-surface border border-line-strong rounded-2xl space-y-4 shadow-xs">
                <div className="flex items-center justify-between border-b border-line pb-3">
                  <h4 className="text-sm font-bold text-fg flex items-center gap-1.5">
                    <Building2 className="w-4 h-4 text-accent" /> Company Intelligence
                  </h4>
                  <button
                    onClick={handleTriggerCompanyResearch}
                    disabled={isResearchingCompany}
                    className="px-3 py-1.5 rounded-lg bg-accent-soft hover:bg-accent-soft text-accent text-xs font-bold border border-accent/30 transition-all flex items-center gap-1.5"
                  >
                    <RefreshCw className={`w-3 h-3 ${isResearchingCompany ? 'animate-spin' : ''}`} />
                    <span>{isResearchingCompany ? 'Researching...' : 'Research Live'}</span>
                  </button>
                </div>

                {(() => {
                  const r = selectedApp.company?.research;
                  if (isResearchingCompany) {
                    return <div className="text-xs text-muted py-4 text-center bg-inset rounded-xl border border-dashed border-line-strong">Finding the official website and reading it...</div>;
                  }
                  if (!r || r.status === 'not_researched') {
                    return <div className="text-xs text-muted py-4 text-center bg-inset rounded-xl border border-dashed border-line-strong">Click &quot;Research Live&quot; to read the company&apos;s own website.</div>;
                  }
                  if (r.status !== 'found') {
                    return (
                      <div className="text-xs text-fg-2 p-3 bg-inset rounded-xl border border-dashed border-line-strong space-y-1">
                        <span className="font-bold text-fg block">No company facts used</span>
                        <p>{r.message}</p>
                        {r.official_website && <a href={r.official_website} target="_blank" rel="noreferrer" className="text-accent underline break-all">{r.official_website}</a>}
                      </div>
                    );
                  }
                  return (
                    <div className="space-y-3 text-xs text-fg-2 leading-relaxed">
                      {r.overview && (
                        <div>
                          <span className="text-fg font-bold block mb-1">Overview</span>
                          <p className="bg-inset p-3 rounded-xl border border-line">{r.overview}</p>
                        </div>
                      )}
                      {[['Products & services', r.products_services], ['Technology', r.technology_info]].map(([label, items]) =>
                        Array.isArray(items) && items.length > 0 ? (
                          <div key={label as string}>
                            <span className="text-fg font-bold block mb-1">{label as string}</span>
                            <div className="flex flex-wrap gap-1.5">
                              {(items as string[]).map((t, idx) => (
                                <span key={idx} className="bg-accent-soft text-accent font-semibold px-2.5 py-0.5 rounded-lg border border-accent/30 text-xs">{t}</span>
                              ))}
                            </div>
                          </div>
                        ) : null)}
                      {r.mission_info && <p><span className="text-fg font-bold">Mission: </span>{r.mission_info}</p>}
                      {r.sources && r.sources.length > 0 && (
                        <div className="text-[11px] text-muted">
                          Source: {r.sources.map((src, i) => (
                            <a key={i} href={src.source_url} target="_blank" rel="noreferrer" className="text-accent underline break-all mr-2">{src.source_url}</a>
                          ))}
                          <span className="block">Read from the company&apos;s own website; every line above appears on that page.</span>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>

              {/* Card 3: Resume Attachment */}
              <div className="p-5 bg-surface border border-line-strong rounded-2xl space-y-2 shadow-xs">
                <h4 className="text-sm font-bold text-fg flex items-center gap-1.5">
                  <FileText className="w-4 h-4 text-accent" /> Resume Attachment
                </h4>
                {selectedApp.cv_attachment?.source ? (
                  <div className="p-3.5 bg-inset rounded-xl border border-line flex items-center justify-between text-xs">
                    <div>
                      <span className="font-bold text-fg">{selectedApp.cv_attachment.label}</span>
                      <p className="text-muted text-[11px]">Attached automatically as a PDF when you create the Gmail draft</p>
                    </div>
                    <span className="bg-ok-soft text-ok border border-ok/30 text-xs font-bold px-2.5 py-1 rounded-lg flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5 text-ok" /> Ready
                    </span>
                  </div>
                ) : (
                  <div className="p-3.5 bg-bad-soft rounded-xl border border-bad/30 text-xs">
                    <span className="font-bold text-bad">No CV found</span>
                    <p className="text-fg-2 text-[11px] mt-0.5">Upload your CV on the Confirm page first, so it can be attached to the draft.</p>
                  </div>
                )}
              </div>

            </div>

            {/* Right Column: Email Studio & Gmail Action (7 cols) */}
            <div className="lg:col-span-7 space-y-4">
              <div className="p-6 bg-surface border border-line-strong rounded-2xl space-y-5 shadow-xs">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-line pb-4">
                  <div>
                    <h3 className="text-base font-bold text-fg flex items-center gap-2">
                      <Mail className="w-4 h-4 text-accent" /> Application Email Studio
                    </h3>
                    <p className="text-xs text-muted mt-0.5">
                      Generates factual emails authored as <strong className="text-accent">{currentUserEmail || 'your account'}</strong> based strictly on verified profile facts.
                    </p>
                  </div>

                  {/* Tone Selector & Generator */}
                  <div className="flex items-center gap-2">
                    <select
                      value={emailTone}
                      onChange={(e) => setEmailTone(e.target.value)}
                      className="bg-inset border border-line-strong text-xs text-fg rounded-xl px-3 py-2 focus:outline-none focus:border-accent font-semibold"
                    >
                      {['Formal', 'Technical', 'Concise', 'Networking', 'Cold Outreach'].map((tone) => (
                        <option key={tone} value={tone}>{tone} Tone</option>
                      ))}
                    </select>
                    <button
                      onClick={handleGenerateEmail}
                      disabled={isGeneratingEmail}
                      className="bg-accent hover:bg-accent-hover text-white font-bold text-xs px-4 py-2 rounded-xl transition-all flex items-center gap-1.5 shadow-xs"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>{isGeneratingEmail ? 'Drafting...' : 'Regenerate'}</span>
                    </button>
                  </div>
                </div>

                {/* Subject Line */}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-fg">Subject Line</label>
                  <input
                    type="text"
                    value={emailSubject}
                    onChange={(e) => setEmailSubject(e.target.value)}
                    placeholder="e.g. Application for Software Engineer Role - Alex Chen"
                    className="w-full bg-inset border border-line-strong rounded-xl p-3 text-xs text-fg focus:outline-none focus:border-accent font-medium"
                  />
                </div>

                {/* Email Body */}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-fg">Email Body</label>
                  <textarea
                    rows={9}
                    value={emailBody}
                    onChange={(e) => setEmailBody(e.target.value)}
                    placeholder="Application email body will appear here..."
                    className="w-full bg-inset border border-line-strong rounded-xl p-3.5 text-xs text-fg leading-relaxed font-sans focus:outline-none focus:border-accent"
                  />
                </div>

                {selectedApp.email_version?.method && (
                  <p className="text-[11px] text-muted">
                    {selectedApp.email_version.method === 'ai' ? 'Written by AI from your CV, the job and the company website, then fact-checked.' : 'AI was unavailable, so a plain template filled with your real CV facts was used.'}
                  </p>
                )}
                {selectedApp.email_version?.removed_claims && selectedApp.email_version.removed_claims.length > 0 && (
                  <div className="p-3 bg-bad-soft border border-bad/30 rounded-xl text-[11px] space-y-1">
                    <span className="font-bold text-bad block">Removed by the fact checker ({selectedApp.email_version.removed_claims.length})</span>
                    {selectedApp.email_version.removed_claims.map((c, i) => <p key={i} className="text-fg-2">{c}</p>)}
                  </div>
                )}

                {/* Grounded Fact Provenance */}
                {selectedApp.email_version?.referenced_profile_facts && selectedApp.email_version.referenced_profile_facts.length > 0 && (
                  <div className="p-3.5 bg-ok-soft rounded-xl border border-ok/30 space-y-1.5 text-xs">
                    <span className="font-bold text-ok flex items-center gap-1.5 text-xs">
                      <ShieldCheck className="w-4 h-4 text-ok" /> Grounded Fact Provenance Citations
                    </span>
                    <div className="flex flex-wrap gap-1.5 text-[11px] text-ok">
                      {selectedApp.email_version.referenced_profile_facts.map((fact, idx) => (
                        <span key={idx} className="bg-surface border border-ok/30 px-2.5 py-0.5 rounded-md font-medium shadow-2xs">
                          {fact}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Gmail Draft Info or Creation Trigger */}
                {selectedApp.gmail_draft ? (
                  <div className="p-4 bg-ok-soft border border-ok/30 rounded-xl flex items-center justify-between">
                    <div className="space-y-0.5">
                      <span className="text-xs font-bold text-ok flex items-center gap-1.5">
                        <CheckCircle2 className="w-4 h-4 text-ok" /> Gmail Draft Created
                      </span>
                      <p className="text-[11px] text-ok">
                        Recipient: {selectedApp.gmail_draft.recipient} • Draft ID: {selectedApp.gmail_draft.draft_id}
                      </p>
                    </div>
                    <a
                      href="https://mail.google.com/mail/#drafts"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="px-3 py-1.5 bg-accent text-white rounded-lg text-xs font-bold hover:bg-accent-hover flex items-center gap-1 shadow-xs"
                    >
                      <span>Open in Gmail</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                ) : (
                  <div className="pt-3 flex items-center justify-between border-t border-line">
                    <span className="text-xs text-pending flex items-center gap-1.5 font-semibold">
                      <Lock className="w-3.5 h-3.5" /> Explicit Human Approval Mandatory
                    </span>

                    <button
                      onClick={openDraftModal}
                      className="bg-accent hover:bg-accent-hover text-white font-bold text-xs px-5 py-2.5 rounded-xl transition-all shadow-xs flex items-center gap-2"
                    >
                      <Send className="w-3.5 h-3.5" /> Create Gmail Draft
                    </button>
                  </div>
                )}

              </div>
            </div>

          </div>
        ) : (
          <div className="p-12 text-center bg-surface rounded-2xl border border-line-strong space-y-4 max-w-lg mx-auto shadow-xs">
            <Briefcase className="w-8 h-8 text-accent mx-auto" />
            <div>
              <h3 className="text-base font-bold text-fg">No Active Application Selected</h3>
              <p className="text-xs text-muted mt-1">
                Choose a job from the list below to begin tailoring your application package.
              </p>
            </div>

            {availableJobs.length > 0 && (
              <div className="space-y-2 pt-2 text-left">
                {availableJobs.slice(0, 3).map((j) => (
                  <button
                    key={j.id}
                    onClick={() => handleCreateNewAppForJob(j.id)}
                    className="w-full p-3 rounded-xl border border-line-strong hover:border-accent/60 bg-inset hover:bg-surface text-left flex items-center justify-between transition-all"
                  >
                    <div>
                      <div className="font-bold text-xs text-fg">{j.title}</div>
                      <div className="text-[11px] text-muted">{j.company} • {j.location}</div>
                    </div>
                    <span className="text-xs font-bold text-accent flex items-center gap-1">
                      <span>Prepare</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* MANDATORY HUMAN APPROVAL DRAFT MODAL */}
      {showDraftModal && (
        <div className="fixed inset-0 z-50 bg-canvas/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-surface border border-line-strong rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl animate-in fade-in zoom-in duration-150">
            <div className="border-b border-line pb-3 flex items-start justify-between">
              <div>
                <span className="text-xs font-bold text-pending flex items-center gap-1 mb-0.5">
                  <UserCheck className="w-3.5 h-3.5" /> Human Approval Security Boundary
                </span>
                <h3 className="text-base font-bold text-fg">Confirm Gmail Draft Creation</h3>
                <p className="text-xs text-muted mt-0.5">
                  Emails are <strong>NEVER</strong> sent automatically. This will safely place a draft in your account.
                </p>
              </div>
              <button
                onClick={() => setShowDraftModal(false)}
                className="text-muted hover:text-fg p-1 rounded-lg hover:bg-surface-2"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-fg">
              {/* SENDER IDENTITY CONFIRMATION */}
              <div className="p-3 bg-accent-soft border border-accent/30 rounded-xl space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-accent text-xs">Sender Account (From)</span>
                  {gmailConnected ? (
                    <span className="text-[10px] bg-ok-soft border border-ok/30 text-ok font-bold px-2 py-0.5 rounded-md">Connected</span>
                  ) : (
                    <button
                      onClick={handleConnectGmail}
                      disabled={isConnectingGmail}
                      className="text-[11px] bg-accent hover:bg-accent-hover text-white font-bold px-2.5 py-1 rounded-md"
                    >
                      {isConnectingGmail ? 'Opening Google...' : 'Connect Gmail'}
                    </button>
                  )}
                </div>
                <div className="font-semibold text-xs text-fg flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-accent" />
                  <span>{gmailEmail || (gmailConnected ? 'Your connected Gmail account' : 'Gmail not connected')}</span>
                </div>
                <p className="text-[11px] text-muted">
                  The draft is saved in this Gmail account and sent from it only when you press Send in Gmail.
                </p>
              </div>

              {/* RECIPIENT */}
              <div className="space-y-1">
                <label className="font-bold text-fg">Recipient Email Address (To)</label>
                <input
                  type="email"
                  value={draftRecipient}
                  onChange={(e) => setDraftRecipient(e.target.value)}
                  placeholder="Paste the recruiter's real email address"
                  className="w-full bg-inset border border-line-strong rounded-xl p-2.5 text-xs text-fg focus:outline-none focus:border-accent"
                />
                {findingRecipient ? (
                  <p className="text-[11px] text-pending flex items-center gap-1.5">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Looking for a real email on the company&apos;s website and Google...
                  </p>
                ) : contacts.length > 0 ? (
                  <div className="space-y-1">
                    {contacts.map((c) => (
                      <button
                        key={c.email}
                        type="button"
                        onClick={() => setDraftRecipient(c.email)}
                        className={`w-full text-left p-2 rounded-lg border text-[11px] transition-all ${draftRecipient === c.email ? 'border-accent bg-accent-soft' : 'border-line bg-inset hover:border-accent/50'}`}
                      >
                        <span className="font-bold text-fg block">{c.email}</span>
                        <span className="text-muted">{CONTACT_LABEL[c.kind] || 'Company email'}{c.source_url ? ` · found on ${c.source_url.replace(/^https?:\/\//, '').slice(0, 60)}` : ''}</span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-[11px] text-muted space-y-1">
                    <p>{recipientMessage || 'Searching the company website for a contact email...'} You can also type the recruiter&apos;s address.</p>
                    {recipientMessage && selectedApp?.job?.application_url && (
                      <a href={selectedApp.job.application_url} target="_blank" rel="noreferrer" className="text-accent font-bold underline">
                        Open the job&apos;s Apply page
                      </a>
                    )}
                  </div>
                )}
                {selectedApp && !findingRecipient && (
                  <button type="button" onClick={() => findRecipient(selectedApp.id, true)}
                          className="text-[11px] text-accent font-bold underline">
                    Search again
                  </button>
                )}
              </div>

              <div className="p-3 bg-inset rounded-xl border border-line space-y-1">
                <span className="font-bold text-fg block">Attachment</span>
                <label className="flex items-center gap-2 cursor-pointer text-xs">
                  <input
                    type="checkbox"
                    checked={includeAttachment}
                    onChange={(e) => setIncludeAttachment(e.target.checked)}
                    className="accent-accent rounded"
                  />
                  <span className="font-medium text-fg-2">
                    Attach my CV (PDF){selectedApp?.cv_attachment?.label ? ` — ${selectedApp.cv_attachment.label}` : ''}
                  </span>
                </label>
              </div>

              {/* Explicit Confirmation Checkbox */}
              <div className="p-3.5 bg-pending-soft border border-pending/30 rounded-xl">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={userConfirmed}
                    onChange={(e) => setUserConfirmed(e.target.checked)}
                    className="accent-accent mt-0.5 rounded"
                  />
                  <span className="text-[11px] text-pending leading-relaxed font-semibold">
                    I have reviewed the email content, verified recipient details, and explicitly approve creating this Gmail Draft.
                  </span>
                </label>
              </div>

              {draftSuccessMsg && (
                <div className="p-3 bg-ok-soft border border-ok/30 text-ok rounded-xl text-xs flex items-center gap-2 font-bold">
                  <CheckCircle2 className="w-4 h-4 shrink-0 text-ok" />
                  <span>{draftSuccessMsg}</span>
                </div>
              )}

              {draftError && (
                <div className="p-3 bg-bad-soft border border-bad/30 text-bad rounded-xl text-xs flex items-center gap-2 font-semibold">
                  <AlertCircle className="w-4 h-4 shrink-0 text-bad" />
                  <span>{draftError}</span>
                </div>
              )}
            </div>

            {/* Modal Action Buttons */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
              <button
                onClick={() => setShowDraftModal(false)}
                className="bg-surface hover:bg-inset border border-line-strong text-fg text-xs font-bold px-4 py-2 rounded-xl transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateGmailDraft}
                disabled={!userConfirmed || isCreatingDraft || !draftRecipient.trim()}
                className={`text-xs font-bold px-4 py-2 rounded-xl transition-all flex items-center gap-1.5 ${
                  userConfirmed
                    ? 'bg-accent hover:bg-accent-hover text-white shadow-xs'
                    : 'bg-line-strong text-subtle cursor-not-allowed'
                }`}
              >
                <Send className="w-3.5 h-3.5" />
                <span>{isCreatingDraft ? 'Creating Draft...' : 'Confirm & Create Draft'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}

export default function ApplicationsPage() {
  return (
    <Suspense fallback={
      <AppShell>
        <div className="p-16 text-center">
          <RefreshCw className="w-6 h-6 animate-spin text-accent mx-auto mb-2" />
          <p className="text-xs font-semibold text-muted">Loading Application Studio...</p>
        </div>
      </AppShell>
    }>
      <ApplicationStudioContent />
    </Suspense>
  );
}

