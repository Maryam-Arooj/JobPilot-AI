'use client';

import React, { useState, useEffect, useRef } from 'react';
import { AppShell } from '@/components/AppShell';
import { apiFetch } from '@/lib/api';
import { ResumePreview } from '@/components/ResumePreview';
import { ResumeFormEditor, ResumeFormData } from '@/components/ResumeFormEditor';
import {
  FileText,
  Sparkles,
  Download,
  Plus,
  CheckCircle2,
  SlidersHorizontal,
  ShieldCheck,
  RefreshCw,
  Edit3,
  Save,
  Globe,
  Award,
  Layers,
  LayoutTemplate,
  FileCheck,
  Briefcase,
  Code2
} from 'lucide-react';

interface ResumeVersionItem {
  id: number;
  title: string;
  template_type: string;
  target_role?: string;
  score?: number;
  created_at?: string;
  content_snapshot?: any;
}

const TEMPLATES = [
  { id: 'Europass Standard', label: 'EU Europass Official', icon: Globe },
  { id: 'ATS Clean', label: 'ATS Modern Clean', icon: FileCheck },
  { id: 'Modern Executive', label: 'Executive Leadership', icon: Briefcase },
  { id: 'Technical Specialist', label: 'Technical Specialist', icon: Code2 }
];

const EMPTY_FORM: ResumeFormData = {
  title: '',
  name: '',
  email: '',
  phone: '',
  location: '',
  linkedin: '',
  github: '',
  website: '',
  summary: '',
  experience: [],
  education: [],
  skills: [],
  certifications: []
};

// Preview-only sample (the original git HEAD default). Never saved.
const SAMPLE_FORM: ResumeFormData = {
  title: 'Digital Marketing | SEO | SEM | Content Marketing',
  name: 'Michael Harris',
  email: 'michael.harris@email.com',
  phone: '+61 412 345 678',
  location: 'Sydney, Australia',
  linkedin: 'linkedin.com/in/michaelharris',
  github: '',
  website: '',
  summary: 'Results-oriented marketing professional with over 5 years of experience in digital marketing, brand strategy, and content creation. Proven ability to drive brand growth, increase online engagement, and deliver data-driven results. Expert in utilizing digital tools and analytics to optimize marketing campaigns and achieve business objectives.',
  experience: [
    {
      role: 'Marketing Manager',
      company: 'XYZ Corporation',
      location: 'Sydney, NSW',
      period: 'January 2022 – Present',
      bullets: [
        'Lead a team of 5 in creating and executing digital marketing strategies across multiple platforms, including social media, SEO, and email campaigns.',
        'Achieved a 35% increase in website traffic and 50% boost in social media engagement within the first year.',
        'Managed a marketing budget of $200,000, ensuring maximum ROI through cost-effective advertising strategies.'
      ]
    },
    {
      role: 'Digital Marketing Specialist',
      company: 'ABC Solutions',
      location: 'Melbourne, VIC',
      period: 'June 2018 – December 2021',
      bullets: [
        'Developed and executed SEO and SEM strategies that increased organic search traffic by 25%.',
        'Created and managed Google Ads and Facebook Ads campaigns, resulting in a 20% increase in qualified leads.',
        'Produced engaging content for blogs, newsletters, and social media platforms to attract target audiences.'
      ]
    }
  ],
  education: [
    {
      degree: 'Bachelor of Marketing',
      institution: 'University of Sydney',
      location: 'Sydney, NSW',
      year: '2018'
    }
  ],
  skills: [
    'Digital Marketing Strategy, SEO & SEM, Google Analytics & SEMrush',
    'Social Media Marketing, Content Creation & Copywriting, Budget Management, Data Analysis'
  ],
  certifications: [
    'Google Analytics Certified',
    'Facebook Blueprint Certification',
    'HubSpot Inbound Marketing Certification'
  ]
};

// "Empty" means no CV content. Name and email are ignored because /profiles/me
// always fills them from the account, even for a profile the user never completed.
const isFormEmpty = (d: ResumeFormData) =>
  ![d.title, d.phone, d.location, d.summary, d.linkedin, d.github, d.website].some(v => v && String(v).trim()) &&
  !(d.experience?.length || d.education?.length || d.skills?.length || d.certifications?.length);

// Same field mapping Sync from Profile has always used.
const mapExperience = (list: any[]) => list.map((e: any) => ({
  role: e.title || e.role || '',
  company: e.company || '',
  location: e.location || '',
  period: e.period || [e.start_date, e.end_date].filter(Boolean).join(' — '),
  bullets: Array.isArray(e.highlights) ? e.highlights : Array.isArray(e.bullets) ? e.bullets : e.description ? [e.description] : []
}));

const mapEducation = (list: any[]) => list.map((ed: any) => ({
  degree: ed.degree || ed.field || '',
  institution: ed.institution || ed.school || '',
  location: ed.location || '',
  year: ed.year || ed.end_year ? String(ed.year || ed.end_year) : ''
}));

const flattenSkills = (skills: any): string[] => {
  if (Array.isArray(skills)) return skills.map(String);
  if (skills && typeof skills === 'object') {
    const flattened: string[] = [];
    Object.values(skills).forEach((v: any) => {
      if (Array.isArray(v)) flattened.push(...v);
      else if (typeof v === 'string') flattened.push(v);
    });
    return flattened;
  }
  return [];
};

const mapCertifications = (list: any[]) =>
  list.map((c: any) => typeof c === 'string' ? c : c.name || c.title || String(c));

// Saved versions come back either in the editor's own shape or in the backend
// ResumeArchitect shape ({ header, professional_summary, experience[{title, start_date…}] }).
const snapshotToForm = (snap: any): ResumeFormData => {
  const header = snap?.header || {};
  return {
    ...EMPTY_FORM,
    title: snap?.title || snap?.target_role || '',
    name: snap?.name || header.name || '',
    email: snap?.email || header.email || '',
    phone: snap?.phone || header.phone || '',
    location: snap?.location || header.location || '',
    linkedin: snap?.linkedin || header.linkedin || '',
    github: snap?.github || header.github || '',
    website: snap?.website || header.website || '',
    photo_url: snap?.photo_url || undefined,
    summary: snap?.summary || snap?.professional_summary || '',
    experience: Array.isArray(snap?.experience) ? mapExperience(snap.experience) : [],
    education: Array.isArray(snap?.education) ? mapEducation(snap.education) : [],
    skills: flattenSkills(snap?.skills),
    certifications: Array.isArray(snap?.certifications) ? mapCertifications(snap.certifications) : []
  };
};

export default function ResumeStudioPage() {
  const [versions, setVersions] = useState<ResumeVersionItem[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<ResumeVersionItem | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('Europass Standard');
  const [targetRole, setTargetRole] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [mode, setMode] = useState<'editor' | 'versions'>('editor');
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Live CV Form State
  // Starts empty and is filled from the user's saved resume or profile. Sample data
  // only appears through the explicit "Preview with sample data" toggle.
  const [formData, setFormData] = useState<ResumeFormData>(EMPTY_FORM);
  const [sampleMode, setSampleMode] = useState(false);
  const realDataRef = useRef<ResumeFormData>(EMPTY_FORM);
  const [profileChecked, setProfileChecked] = useState(false);

  // Any real data arriving switches sample preview off.
  const applyRealData = (data: ResumeFormData) => {
    setSampleMode(false);
    realDataRef.current = data;
    setFormData(data);
  };

  const handleToggleSample = () => {
    if (sampleMode) {
      setSampleMode(false);
      setFormData(realDataRef.current);
    } else {
      realDataRef.current = formData;
      setSampleMode(true);
      setFormData(SAMPLE_FORM);
    }
  };

  // `initial`: fill the editor on page load. Refreshes after Save keep the live edits.
  const loadResumes = async (initial = false) => {
    setLoading(true);
    setResumeError(null);
    let loaded = false;
    try {
      const data = await apiFetch('/resumes/');
      if (Array.isArray(data) && data.length > 0) {
        setVersions(data);
        const withContent = data.find((r: any) => r.content_snapshot && !isFormEmpty(snapshotToForm(r.content_snapshot)));
        if (withContent) {
          setSelectedVersion(withContent);
          if (initial) {
            applyRealData(snapshotToForm(withContent.content_snapshot));
            loaded = true;
          }
        } else {
          setSelectedVersion(data[0]);
        }
      }
    } catch (err: any) {
      console.warn('Resume load notice:', err);
    } finally {
      setLoading(false);
    }
    // No saved version with content: fill from the user's real profile.
    if (initial && !loaded) {
      await handleImportFromProfile({ silent: true });
    }
  };

  useEffect(() => {
    loadResumes(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleImportFromProfile = async ({ silent = false }: { silent?: boolean } = {}) => {
    setIsImporting(true);
    // Never fall back to sample values for fields the profile doesn't have.
    const base = sampleMode ? realDataRef.current : formData;
    try {
      const profile = await apiFetch('/profiles/me');
      if (profile) {
        const profObj = profile.professional || {};
        const persObj = profile.personal || {};
        const expList = Array.isArray(profile.experience) && profile.experience.length > 0
          ? mapExperience(profile.experience)
          : base.experience;

        const eduList = Array.isArray(profile.education) && profile.education.length > 0
          ? mapEducation(profile.education)
          : base.education;

        let skillList = base.skills;
        const flattened = flattenSkills(profile.skills);
        if (flattened.length > 0) skillList = flattened;

        const certList = Array.isArray(profile.certifications)
          ? mapCertifications(profile.certifications)
          : base.certifications || [];

        const next: ResumeFormData = {
          title: profObj.headline || profObj.title || base.title,
          name: persObj.name || base.name,
          email: persObj.email || base.email,
          phone: persObj.phone || base.phone,
          location: persObj.location || base.location,
          linkedin: persObj.linkedin || persObj.linkedin_url || base.linkedin || '',
          github: persObj.github || persObj.github_url || base.github || '',
          website: persObj.website || persObj.portfolio_url || base.website || '',
          photo_url: base.photo_url,
          summary: profObj.summary || base.summary,
          experience: expList,
          education: eduList,
          skills: skillList,
          certifications: certList
        };
        applyRealData(next);
        if (!silent && !isFormEmpty(next)) {
          setSaveSuccess(true);
          setTimeout(() => setSaveSuccess(false), 2500);
        }
      }
    } catch (err: any) {
      console.warn('Profile import error:', err);
    } finally {
      setIsImporting(false);
      setProfileChecked(true);
    }
  };

  const handleSaveCustomResume = async () => {
    if (sampleMode) return; // sample data is preview-only
    setIsSaving(true);
    setSaveSuccess(false);
    try {
      const savedRes = await apiFetch('/resumes/', {
        method: 'POST',
        body: JSON.stringify({
          title: `${formData.title || 'Resume'} (${new Date().toLocaleDateString()})`,
          template: selectedTemplate,
          target_role: targetRole
        })
      });

      if (savedRes && savedRes.id) {
        await apiFetch(`/resumes/${savedRes.id}/generate`, {
          method: 'POST',
          body: JSON.stringify({
            target_role: targetRole,
            template: selectedTemplate,
            custom_content: formData
          })
        });
      }

      await loadResumes();
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      console.error('Save resume error:', err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6">
        
        {/* Sleek, Executive Header */}
        <div className="bg-surface border border-line rounded-2xl p-6 shadow-xs space-y-4 print:hidden">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-accent" />
                <span className="text-[11px] font-mono text-accent uppercase tracking-wider font-bold">
                  JobPilot Document Studio
                </span>
              </div>
              <h1 className="text-2xl font-semibold tracking-tight text-fg">
                Resume Studio
              </h1>
              <p className="text-xs text-muted mt-0.5">
                Design ATS-compliant and Europass resumes with real-time live preview and AI role tailoring.
              </p>
            </div>

            {/* Top Action Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={`/jobs?query=${encodeURIComponent(formData.title || targetRole)}&source=cv`}
                className="px-3.5 py-2 rounded-xl bg-accent-soft hover:bg-accent-soft text-accent border border-accent/30 text-xs font-bold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
              >
                <Sparkles className="w-3.5 h-3.5 text-accent" />
                <span>Find Matching Jobs</span>
              </a>

              <button
                type="button"
                role="switch"
                aria-checked={sampleMode}
                onClick={handleToggleSample}
                className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 border cursor-pointer ${
                  sampleMode
                    ? 'bg-accent-soft text-accent border-accent/40'
                    : 'bg-inset text-fg-2 border-line-strong hover:text-fg hover:border-accent/50'
                }`}
              >
                <span className={`relative inline-flex w-7 h-4 rounded-full transition-colors ${sampleMode ? 'bg-accent' : 'bg-surface-2 border border-line-strong'}`}>
                  <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${sampleMode ? 'left-3.5' : 'left-0.5'}`} />
                </span>
                <span>Preview with sample data</span>
              </button>

              <button
                onClick={() => handleImportFromProfile()}
                disabled={isImporting}
                className="px-3.5 py-2 rounded-xl bg-inset hover:bg-surface-2 text-fg border border-line text-xs font-bold transition-all flex items-center gap-1.5 shadow-2xs hover:border-accent/50 cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 text-accent ${isImporting ? 'animate-spin' : ''}`} />
                <span>{isImporting ? 'Syncing...' : 'Sync from Profile'}</span>
              </button>

              <button
                onClick={handleSaveCustomResume}
                disabled={isSaving || sampleMode}
                title={sampleMode ? 'Sample data is preview-only and cannot be saved' : undefined}
                className="px-4 py-2 rounded-xl bg-gradient-to-r from-accent to-accent hover:from-accent-hover hover:to-accent text-white text-xs font-bold transition-all flex items-center gap-1.5 shadow-md hover:shadow-lg disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
              >
                <Save className="w-3.5 h-3.5" />
                <span>{isSaving ? 'Saving...' : saveSuccess ? 'Saved to Cloud!' : 'Save Version'}</span>
              </button>
            </div>
          </div>

          {/* Interactive Action Banner on Save / Alignment */}
          {saveSuccess && (
            <div className="p-3.5 bg-gradient-to-r from-ok-soft to-accent-soft border border-ok/30 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-2xs animate-in fade-in duration-300">
              <div className="flex items-center gap-2.5 text-xs text-ok">
                <CheckCircle2 className="w-4 h-4 text-ok shrink-0" />
                <div>
                  <span className="font-bold">Resume Synchronized!</span>
                  <span className="text-fg-2 ml-1">Ready to search live jobs matching <strong className="text-fg">{formData.title || targetRole}</strong>?</span>
                </div>
              </div>
              <a
                href={`/jobs?query=${encodeURIComponent(formData.title || targetRole)}&source=cv`}
                className="px-3.5 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-xs font-bold transition-all flex items-center gap-1.5 shrink-0 shadow-xs"
              >
                <Briefcase className="w-3.5 h-3.5" />
                <span>Search Relevant Jobs</span>
              </a>
            </div>
          )}

          {/* Template Format Selector Strip */}
          <div className="pt-4 border-t border-line flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-muted font-bold">
              <LayoutTemplate className="w-3.5 h-3.5 text-accent" />
              <span>Select Design Template:</span>
            </div>

            <div className="flex flex-wrap items-center gap-1.5 bg-inset p-1 rounded-xl border border-line">
              {TEMPLATES.map((tmpl) => {
                const Icon = tmpl.icon;
                const active = selectedTemplate === tmpl.id;
                return (
                  <button
                    key={tmpl.id}
                    onClick={() => setSelectedTemplate(tmpl.id)}
                    aria-pressed={active}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 cursor-pointer border ${
                      active
                        ? 'bg-accent text-white border-accent shadow-xs'
                        : 'bg-surface-2 text-fg-2 border-line-strong hover:border-accent hover:text-fg'
                    }`}
                  >
                    <Icon className={`w-3.5 h-3.5 ${active ? 'text-white' : 'text-muted'}`} />
                    <span>{tmpl.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Two-Column Studio Layout */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start print:block print:w-full">
          
          {/* Left Panel: Form & AI Tailor */}
          <div className="xl:col-span-5 space-y-4 print:hidden">
            <div className="bg-surface border border-line rounded-2xl p-5 shadow-xs">
              <ResumeFormEditor
                data={formData}
                onChange={setFormData}
                onImportFromProfile={() => handleImportFromProfile()}
                isImporting={isImporting}
              />
            </div>
          </div>

          {/* Right Panel: Live Document Canvas */}
          <div className="xl:col-span-7 sticky top-20 space-y-4 print:static print:w-full print:m-0 print:p-0 print:space-y-0">
            {sampleMode && (
              <div className="px-4 py-2.5 rounded-xl border border-accent/40 bg-accent-soft text-xs flex items-center justify-between gap-3 print:hidden">
                <span className="flex items-center gap-2 font-bold text-accent">
                  <Sparkles className="w-3.5 h-3.5" /> Sample data — not saved
                </span>
                <button
                  type="button"
                  onClick={handleToggleSample}
                  className="text-fg-2 hover:text-fg font-semibold cursor-pointer"
                >
                  Turn off
                </button>
              </div>
            )}

            {!sampleMode && profileChecked && !isImporting && isFormEmpty(formData) && (
              <div className="p-5 rounded-2xl border border-line bg-surface flex flex-col sm:flex-row sm:items-center justify-between gap-4 print:hidden">
                <div className="flex items-start gap-3">
                  <div className="p-2 rounded-lg bg-surface-2 border border-line-strong text-accent shrink-0">
                    <FileText className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-fg">Your career profile has no CV details yet</div>
                    <p className="text-xs text-muted mt-0.5">
                      Add experience, education and skills on the <a href="/profile" className="text-accent hover:underline font-semibold">Profile page</a>, then sync — or fill in the editor on the left. Nothing is invented for you.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleImportFromProfile()}
                  disabled={isImporting}
                  className="px-3.5 py-2 rounded-xl bg-accent hover:bg-accent-hover text-white text-xs font-bold transition-all flex items-center gap-1.5 shrink-0 cursor-pointer disabled:opacity-60"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Sync from Profile</span>
                </button>
              </div>
            )}

            <ResumePreview
              resume={formData}
              templateName={selectedTemplate}
            />
          </div>

        </div>

      </div>
    </AppShell>
  );
}
