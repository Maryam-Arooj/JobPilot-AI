'use client';

import React, { useState } from 'react';
import { apiFetch } from '@/lib/api';
import { 
  User, 
  Briefcase, 
  GraduationCap, 
  Code, 
  Plus, 
  Trash2, 
  Sparkles, 
  RefreshCw,
  FileText,
  Mail,
  Phone,
  MapPin,
  Globe,
  Sliders,
  CheckCircle2,
  X,
  Camera,
  Upload,
  Award,
  Link2
} from 'lucide-react';

const LinkedinIcon = ({ className = "w-3.5 h-3.5" }: { className?: string }) => (
  <svg className={className} fill="currentColor" viewBox="0 0 24 24">
    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
  </svg>
);

const GithubIcon = ({ className = "w-3.5 h-3.5" }: { className?: string }) => (
  <svg className={className} fill="currentColor" viewBox="0 0 24 24">
    <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
  </svg>
);

export interface ResumeFormData {
  title?: string;
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  linkedin?: string;
  github?: string;
  website?: string;
  photo_url?: string;
  summary?: string;
  experience?: Array<{
    role: string;
    company: string;
    location?: string;
    period: string;
    bullets: string[];
  }>;
  education?: Array<{
    degree: string;
    institution: string;
    location?: string;
    year: string;
  }>;
  skills?: string[];
  certifications?: string[];
}

type TailorProposal = {
  id: string;
  kind: 'title' | 'summary' | 'skills' | 'bullet';
  label: string;
  before: string;
  after: string;
  beforeList?: string[];
  afterList?: string[];
  expIndex?: number;
  bulletIndex?: number;
  status: 'pending' | 'accepted' | 'rejected' | 'outdated';
};

// Turn the /resumes/tailor response into reviewable before → after items.
function buildProposals(data: ResumeFormData, res: any): TailorProposal[] {
  const out: TailorProposal[] = [];
  if (typeof res?.title === 'string' && res.title.trim() && res.title !== (data.title || '')) {
    out.push({ id: 'title', kind: 'title', label: 'Professional headline', before: data.title || '', after: res.title, status: 'pending' });
  }
  if (typeof res?.summary === 'string' && res.summary.trim() && res.summary !== (data.summary || '')) {
    out.push({ id: 'summary', kind: 'summary', label: 'Professional summary', before: data.summary || '', after: res.summary, status: 'pending' });
  }
  const skills = data.skills || [];
  if (Array.isArray(res?.skills_order) && res.skills_order.join('\u0000') !== skills.join('\u0000')) {
    out.push({
      id: 'skills', kind: 'skills', label: 'Skills order (most relevant first)',
      before: skills.join(' · '), after: res.skills_order.join(' · '),
      beforeList: skills, afterList: res.skills_order, status: 'pending'
    });
  }
  (Array.isArray(res?.experience) ? res.experience : []).forEach((item: any) => {
    const exp = data.experience?.[item?.index];
    if (!exp || !Array.isArray(item.bullets)) return;
    // Empty bullets were not sent, so map response positions back to form positions.
    const formPositions = (exp.bullets || []).map((b, i) => (b.trim() ? i : -1)).filter(i => i >= 0);
    item.bullets.forEach((after: string, j: number) => {
      const pos = formPositions[j];
      if (pos === undefined || typeof after !== 'string' || after === exp.bullets[pos]) return;
      out.push({
        id: `exp-${item.index}-${pos}`, kind: 'bullet',
        label: `${[exp.role, exp.company].filter(Boolean).join(' @ ') || `Role #${item.index + 1}`} — bullet ${pos + 1}`,
        before: exp.bullets[pos], after, expIndex: item.index, bulletIndex: pos, status: 'pending'
      });
    });
  });
  return out;
}

// apiFetch throws "API <status>: <body>"; surface the backend's own detail message.
function apiErrorMessage(err: any): string {
  const msg = String(err?.message || '');
  const brace = msg.indexOf('{');
  if (brace >= 0) {
    try {
      const detail = JSON.parse(msg.slice(brace)).detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) return detail.map((d: any) => d?.msg).filter(Boolean).join('; ');
    } catch { /* not JSON */ }
  }
  return msg || 'Tailoring failed. Please try again.';
}

interface ResumeFormEditorProps {
  data: ResumeFormData;
  onChange: (newData: ResumeFormData) => void;
  onImportFromProfile?: () => void;
  isImporting?: boolean;
}

export function ResumeFormEditor({
  data,
  onChange,
  onImportFromProfile,
  isImporting = false
}: ResumeFormEditorProps) {
  const [activeTab, setActiveTab] = useState<'personal' | 'summary' | 'experience' | 'education' | 'skills' | 'certifications'>('personal');
  const [newSkill, setNewSkill] = useState('');
  const [newCertification, setNewCertification] = useState('');
  const [targetRoleInput, setTargetRoleInput] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [isTailoring, setIsTailoring] = useState(false);
  const [tailorError, setTailorError] = useState<string | null>(null);
  const [proposals, setProposals] = useState<TailorProposal[] | null>(null);
  const [tailorGaps, setTailorGaps] = useState<string[]>([]);
  const [tailorNotes, setTailorNotes] = useState<string[]>([]);

  const updateField = (field: keyof ResumeFormData, value: any) => {
    onChange({
      ...data,
      [field]: value
    });
  };

  // Experience handlers
  const handleAddExperience = () => {
    const updated = [
      ...(data.experience || []),
      { role: '', company: '', period: '', bullets: [] }
    ];
    updateField('experience', updated);
  };

  const handleUpdateExperience = (index: number, key: string, val: any) => {
    const updated = [...(data.experience || [])];
    updated[index] = { ...updated[index], [key]: val };
    updateField('experience', updated);
  };

  const handleRemoveExperience = (index: number) => {
    const updated = (data.experience || []).filter((_, i) => i !== index);
    updateField('experience', updated);
  };

  const handleAddBullet = (expIndex: number) => {
    const updated = [...(data.experience || [])];
    updated[expIndex].bullets = [...(updated[expIndex].bullets || []), ''];
    updateField('experience', updated);
  };

  const handleUpdateBullet = (expIndex: number, bulletIndex: number, text: string) => {
    const updated = [...(data.experience || [])];
    const bullets = [...(updated[expIndex].bullets || [])];
    bullets[bulletIndex] = text;
    updated[expIndex].bullets = bullets;
    updateField('experience', updated);
  };

  const handleRemoveBullet = (expIndex: number, bulletIndex: number) => {
    const updated = [...(data.experience || [])];
    updated[expIndex].bullets = (updated[expIndex].bullets || []).filter((_, i) => i !== bulletIndex);
    updateField('experience', updated);
  };

  // Education handlers
  const handleAddEducation = () => {
    const updated = [
      ...(data.education || []),
      { degree: '', institution: '', year: '' }
    ];
    updateField('education', updated);
  };

  const handleUpdateEducation = (index: number, key: string, val: string) => {
    const updated = [...(data.education || [])];
    updated[index] = { ...updated[index], [key]: val };
    updateField('education', updated);
  };

  const handleRemoveEducation = (index: number) => {
    const updated = (data.education || []).filter((_, i) => i !== index);
    updateField('education', updated);
  };

  // Skill handlers
  const handleAddSkill = () => {
    if (!newSkill.trim()) return;
    const current = data.skills || [];
    if (!current.includes(newSkill.trim())) {
      updateField('skills', [...current, newSkill.trim()]);
    }
    setNewSkill('');
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    const updated = (data.skills || []).filter(s => s !== skillToRemove);
    updateField('skills', updated);
  };

  // Certification handlers
  const handleAddCertification = () => {
    if (!newCertification.trim()) return;
    const current = data.certifications || [];
    if (!current.includes(newCertification.trim())) {
      updateField('certifications', [...current, newCertification.trim()]);
    }
    setNewCertification('');
  };

  const handleRemoveCertification = (certToRemove: string) => {
    const updated = (data.certifications || []).filter(c => c !== certToRemove);
    updateField('certifications', updated);
  };

  // AI tailoring: the backend returns grounded proposals; nothing changes until accepted.
  const handleAITailor = async () => {
    const role = targetRoleInput.trim();
    if (!role) {
      setTailorError('Enter a target job title first.');
      return;
    }
    setIsTailoring(true);
    setTailorError(null);
    setProposals(null);
    setTailorGaps([]);
    setTailorNotes([]);
    try {
      const res = await apiFetch('/resumes/tailor', {
        method: 'POST',
        body: JSON.stringify({
          target_role: role,
          job_description: jobDescription.trim() || undefined,
          cv: {
            title: data.title || '',
            summary: data.summary || '',
            experience: (data.experience || []).map(e => ({
              role: e.role || '', company: e.company || '', location: e.location || '',
              period: e.period || '', bullets: (e.bullets || []).filter(b => b.trim())
            })),
            skills: data.skills || [],
            education: data.education || [],
            certifications: data.certifications || []
          }
        })
      });
      setProposals(buildProposals(data, res));
      setTailorGaps(Array.isArray(res?.gaps) ? res.gaps : []);
      setTailorNotes(Array.isArray(res?.notes) ? res.notes : []);
    } catch (err: any) {
      setTailorError(apiErrorMessage(err));
    } finally {
      setIsTailoring(false);
    }
  };

  // Apply the given proposals to the current form in one update. A proposal whose
  // "before" no longer matches (the user edited it meanwhile) is skipped as outdated.
  const resolveProposals = (ids: string[], accept: boolean) => {
    if (!proposals) return;
    const experience = (data.experience || []).map(e => ({ ...e, bullets: [...(e.bullets || [])] }));
    const next: ResumeFormData = { ...data, experience };
    let changed = false;
    const updated = proposals.map(p => {
      if (!ids.includes(p.id) || p.status !== 'pending') return p;
      if (!accept) return { ...p, status: 'rejected' as const };
      if (p.kind === 'title' && (next.title || '') === p.before) next.title = p.after;
      else if (p.kind === 'summary' && (next.summary || '') === p.before) next.summary = p.after;
      else if (p.kind === 'skills' && (next.skills || []).join('\u0000') === (p.beforeList || []).join('\u0000')) next.skills = p.afterList;
      else if (p.kind === 'bullet' && experience[p.expIndex!]?.bullets[p.bulletIndex!] === p.before) {
        experience[p.expIndex!].bullets[p.bulletIndex!] = p.after;
      } else return { ...p, status: 'outdated' as const };
      changed = true;
      return { ...p, status: 'accepted' as const };
    });
    setProposals(updated);
    if (changed) onChange(next);
  };

  const closeTailorReview = () => {
    setProposals(null);
    setTailorGaps([]);
    setTailorNotes([]);
  };

  return (
    <div className="space-y-5">
      
      {/* Editor Section Navigation Tabs */}
      <div className="flex p-1 bg-surface-2 rounded-xl border border-line gap-1 overflow-x-auto text-xs font-semibold">
        {[
          { id: 'personal', label: 'Personal', icon: User },
          { id: 'summary', label: 'Summary', icon: FileText },
          { id: 'experience', label: 'Experience', icon: Briefcase },
          { id: 'education', label: 'Education', icon: GraduationCap },
          { id: 'skills', label: 'Skills', icon: Code },
          { id: 'certifications', label: 'Certifications', icon: Award },
        ].map((tab) => {
          const Icon = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              className={`flex-1 py-2 px-2.5 rounded-lg text-center transition-all flex items-center justify-center gap-1.5 shrink-0 cursor-pointer ${
                active
                  ? 'bg-surface text-accent shadow-[inset_0_-2px_0_0_var(--jp-accent)]'
                  : 'text-muted hover:text-fg'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab 1: Personal Information */}
      {activeTab === 'personal' && (
        <div className="space-y-3.5 text-xs">
          <div className="space-y-1">
            <label className="font-semibold text-fg-2 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-muted" /> Full Name
            </label>
            <input
              type="text"
              value={data.name || ''}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="e.g. Alex Chen"
              className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
            />
          </div>

          <div className="space-y-1">
            <label className="font-semibold text-fg-2 flex items-center gap-1.5">
              <Briefcase className="w-3.5 h-3.5 text-muted" /> Professional Headline
            </label>
            <input
              type="text"
              value={data.title || ''}
              onChange={(e) => updateField('title', e.target.value)}
              placeholder="e.g. Senior Software & AI Engineer"
              className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="font-semibold text-fg-2 flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-muted" /> Email Address
              </label>
              <input
                type="email"
                value={data.email || ''}
                onChange={(e) => updateField('email', e.target.value)}
                placeholder="alex.chen@example.com"
                className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
              />
            </div>

            <div className="space-y-1">
              <label className="font-semibold text-fg-2 flex items-center gap-1.5">
                <Phone className="w-3.5 h-3.5 text-muted" /> Phone Number
              </label>
              <input
                type="text"
                value={data.phone || ''}
                onChange={(e) => updateField('phone', e.target.value)}
                placeholder="+1 (555) 234-5678"
                className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label className="font-semibold text-fg-2 flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5 text-muted" /> Location / Country
            </label>
            <input
              type="text"
              value={data.location || ''}
              onChange={(e) => updateField('location', e.target.value)}
              placeholder="e.g. San Francisco, CA / Remote"
              className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
            />
          </div>

          {/* Optional Social & Professional Profile Links */}
          <div className="space-y-3 pt-3 border-t border-line">
            <div className="text-[11px] font-mono uppercase font-bold text-muted flex items-center gap-1.5">
              <Link2 className="w-3.5 h-3.5 text-accent" /> Professional Links & Social Profiles (Optional)
            </div>

            <div className="space-y-1">
              <label className="font-semibold text-fg-2 flex items-center gap-1.5">
                <LinkedinIcon className="w-3.5 h-3.5 text-accent" /> LinkedIn Profile
              </label>
              <input
                type="text"
                value={data.linkedin || ''}
                onChange={(e) => updateField('linkedin', e.target.value)}
                placeholder="e.g. linkedin.com/in/alexchen"
                className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="font-semibold text-fg-2 flex items-center gap-1.5">
                  <GithubIcon className="w-3.5 h-3.5 text-fg" /> GitHub Profile
                </label>
                <input
                  type="text"
                  value={data.github || ''}
                  onChange={(e) => updateField('github', e.target.value)}
                  placeholder="e.g. github.com/alexchen"
                  className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                />
              </div>

              <div className="space-y-1">
                <label className="font-semibold text-fg-2 flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-accent" /> Website / Portfolio
                </label>
                <input
                  type="text"
                  value={data.website || ''}
                  onChange={(e) => updateField('website', e.target.value)}
                  placeholder="e.g. alexchen.dev"
                  className="w-full p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                />
              </div>
            </div>
          </div>

          {/* Profile Picture Upload & Management */}
          <div className="space-y-2 pt-3 border-t border-line">
            <div className="flex items-center justify-between">
              <label className="font-bold text-fg-2 flex items-center gap-1.5">
                <Camera className="w-3.5 h-3.5 text-accent" /> Profile Photo
              </label>
              {data.photo_url && (
                <button
                  type="button"
                  onClick={() => updateField('photo_url', '')}
                  className="text-[11px] text-bad font-bold hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <Trash2 className="w-3 h-3" /> Remove Photo
                </button>
              )}
            </div>

            {data.photo_url ? (
              <div className="p-3 bg-inset border border-line rounded-2xl flex items-center gap-3">
                <img
                  src={data.photo_url}
                  alt="Profile Preview"
                  className="w-14 h-14 rounded-xl object-cover border-2 border-accent shadow-xs shrink-0"
                />
                <div className="flex-1 space-y-1">
                  <div className="text-xs font-bold text-fg">Photo Attached</div>
                  <p className="text-[10px] text-muted">Active on Europass and executive resume templates.</p>
                  <label className="inline-flex items-center gap-1 text-[11px] font-bold text-accent hover:underline cursor-pointer">
                    <Upload className="w-3 h-3" /> Change Photo
                    <input
                      type="file"
                      accept="image/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          if (file.size > 4 * 1024 * 1024) {
                            alert('Image must be under 4MB');
                            return;
                          }
                          const reader = new FileReader();
                          reader.onload = (ev) => {
                            updateField('photo_url', ev.target?.result as string);
                          };
                          reader.readAsDataURL(file);
                        }
                      }}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>
            ) : (
              <div>
                <label className="border-2 border-dashed border-line-strong hover:border-accent/60 bg-inset hover:bg-accent-soft/30 rounded-2xl p-4 flex flex-col items-center justify-center gap-1.5 text-center cursor-pointer transition-all group">
                  <div className="p-2 rounded-full bg-surface border border-line text-accent group-hover:scale-110 transition-transform shadow-2xs">
                    <Upload className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-xs font-bold text-fg block">Click to upload photo</span>
                    <span className="text-[10px] text-muted font-mono">PNG, JPG, WEBP up to 4MB</span>
                  </div>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) {
                        if (file.size > 4 * 1024 * 1024) {
                          alert('Image must be under 4MB');
                          return;
                        }
                        const reader = new FileReader();
                        reader.onload = (ev) => {
                          updateField('photo_url', ev.target?.result as string);
                        };
                        reader.readAsDataURL(file);
                      }
                    }}
                    className="hidden"
                  />
                </label>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 2: Executive Summary */}
      {activeTab === 'summary' && (
        <div className="space-y-3.5 text-xs">
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="font-semibold text-fg-2 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-muted" /> Professional Summary
              </label>
              <span className="text-[10px] font-mono text-subtle">
                {data.summary?.length || 0} chars
              </span>
            </div>
            <textarea
              rows={6}
              value={data.summary || ''}
              onChange={(e) => updateField('summary', e.target.value)}
              placeholder="Provide a compelling overview of your technical background, impact, and engineering specialties..."
              className="w-full p-3 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent leading-relaxed transition-all"
            />
          </div>
        </div>
      )}

      {/* Tab 3: Work Experience */}
      {activeTab === 'experience' && (
        <div className="space-y-4 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-fg">{data.experience?.length || 0} Work Roles</span>
            <button
              type="button"
              onClick={handleAddExperience}
              className="px-2.5 py-1 rounded-lg bg-accent hover:bg-accent-hover text-white text-[11px] font-semibold transition-colors flex items-center gap-1 shadow-2xs"
            >
              <Plus className="w-3 h-3" /> Add Position
            </button>
          </div>

          <div className="space-y-3">
            {(data.experience || []).map((exp, idx) => (
              <div key={idx} className="p-3.5 rounded-xl border border-line bg-surface-2 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-fg text-xs">Role #{idx + 1}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveExperience(idx)}
                    className="p-1 text-subtle hover:text-bad transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  <input
                    type="text"
                    value={exp.role}
                    onChange={(e) => handleUpdateExperience(idx, 'role', e.target.value)}
                    placeholder="Job title (e.g. Software Engineer)"
                    className="p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                  />
                  <input
                    type="text"
                    value={exp.company}
                    onChange={(e) => handleUpdateExperience(idx, 'company', e.target.value)}
                    placeholder="Company (e.g. Acme Corp)"
                    className="p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                  />
                </div>

                <input
                  type="text"
                  value={exp.period}
                  onChange={(e) => handleUpdateExperience(idx, 'period', e.target.value)}
                  placeholder="Period (e.g. 2023 — Present)"
                  className="w-full p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                />

                {/* Bullets */}
                <div className="space-y-1.5 pt-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-fg-2">Impact & Achievements</span>
                    <button
                      type="button"
                      onClick={() => handleAddBullet(idx)}
                      className="text-[10px] text-fg font-semibold hover:underline flex items-center gap-0.5"
                    >
                      <Plus className="w-3 h-3" /> Add Bullet
                    </button>
                  </div>
                  {exp.bullets.map((b, bIdx) => (
                    <div key={bIdx} className="flex items-center gap-1.5">
                      <input
                        type="text"
                        value={b}
                        onChange={(e) => handleUpdateBullet(idx, bIdx, e.target.value)}
                        placeholder="Achievement (e.g. Built and shipped the billing API)"
                        className="flex-1 p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                      />
                      <button
                        type="button"
                        onClick={() => handleRemoveBullet(idx, bIdx)}
                        className="p-1.5 text-subtle hover:text-bad"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 4: Education */}
      {activeTab === 'education' && (
        <div className="space-y-4 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-fg">{data.education?.length || 0} Academic Entries</span>
            <button
              type="button"
              onClick={handleAddEducation}
              className="px-2.5 py-1 rounded-lg bg-accent hover:bg-accent-hover text-white text-[11px] font-semibold transition-colors flex items-center gap-1 shadow-2xs"
            >
              <Plus className="w-3 h-3" /> Add Degree
            </button>
          </div>

          <div className="space-y-3">
            {(data.education || []).map((edu, idx) => (
              <div key={idx} className="p-3.5 rounded-xl border border-line bg-surface-2 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-fg text-xs">Degree #{idx + 1}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveEducation(idx)}
                    className="p-1 text-subtle hover:text-bad transition-colors"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <input
                  type="text"
                  value={edu.degree}
                  onChange={(e) => handleUpdateEducation(idx, 'degree', e.target.value)}
                  placeholder="Degree & Major (e.g. B.S. Computer Science)"
                  className="w-full p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                />

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={edu.institution}
                    onChange={(e) => handleUpdateEducation(idx, 'institution', e.target.value)}
                    placeholder="Institution / University"
                    className="p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                  />
                  <input
                    type="text"
                    value={edu.year}
                    onChange={(e) => handleUpdateEducation(idx, 'year', e.target.value)}
                    placeholder="Year (e.g. 2021)"
                    className="p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 5: Skills */}
      {activeTab === 'skills' && (
        <div className="space-y-4 text-xs">
          <div className="space-y-1.5">
            <label className="font-semibold text-fg-2">Add Technical Skill</label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={newSkill}
                onChange={(e) => setNewSkill(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddSkill()}
                placeholder="e.g. PyTorch, Next.js, Kubernetes"
                className="flex-1 p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent"
              />
              <button
                type="button"
                onClick={handleAddSkill}
                className="px-4 py-2.5 bg-accent hover:bg-accent-hover text-white font-semibold rounded-xl text-xs shadow-2xs"
              >
                Add
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <span className="font-semibold text-fg-2 text-[11px]">Active Skills ({data.skills?.length || 0}):</span>
            <div className="flex flex-wrap gap-1.5">
              {(data.skills || []).map((sk, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-inset border border-line text-xs font-mono text-fg"
                >
                  <span>{sk}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveSkill(sk)}
                    className="text-subtle hover:text-bad"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab 6: Certifications */}
      {activeTab === 'certifications' && (
        <div className="space-y-4 text-xs">
          <div className="space-y-1.5">
            <label className="font-semibold text-fg-2">Add Certification or License (Optional)</label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={newCertification}
                onChange={(e) => setNewCertification(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddCertification()}
                placeholder="e.g. Google Analytics Certified, AWS Solutions Architect"
                className="flex-1 p-2.5 bg-inset border border-line-strong rounded-xl text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent"
              />
              <button
                type="button"
                onClick={handleAddCertification}
                className="px-4 py-2.5 bg-accent hover:bg-accent-hover text-white font-semibold rounded-xl text-xs shadow-2xs cursor-pointer"
              >
                Add
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <span className="font-semibold text-fg-2 text-[11px]">Active Certifications ({data.certifications?.length || 0}):</span>
            {(data.certifications && data.certifications.length > 0) ? (
              <div className="space-y-2">
                {data.certifications.map((cert, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-2.5 bg-inset border border-line rounded-xl text-xs text-fg"
                  >
                    <div className="flex items-center gap-2 font-medium">
                      <Award className="w-3.5 h-3.5 text-accent" />
                      <span>{cert}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemoveCertification(cert)}
                      className="text-subtle hover:text-bad p-1 cursor-pointer"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted italic">No certifications added yet. (Optional)</p>
            )}
          </div>
        </div>
      )}

      {/* AI Role Tailor Banner */}
      <div className="p-3.5 bg-inset rounded-xl border border-line space-y-2">
        <div className="text-xs">
          <span className="font-semibold text-fg flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-accent" /> AI Role Tailoring & Job Discovery
          </span>
          <p className="text-[11px] text-muted mt-0.5">
            Rewrites only from your CV and verified profile facts. You review every change before it is applied.
          </p>
        </div>
        <div className="space-y-1">
          <label htmlFor="tailor-target" className="font-semibold text-fg-2 text-xs">Target job title</label>
          <div className="flex items-center gap-2">
            <input
              id="tailor-target"
              type="text"
              value={targetRoleInput}
              onChange={(e) => setTargetRoleInput(e.target.value)}
              placeholder="e.g. AI Engineer"
              className="flex-1 p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all"
            />
            <button
              type="button"
              onClick={handleAITailor}
              disabled={isTailoring}
              aria-busy={isTailoring}
              className="px-3 py-2 bg-accent hover:bg-accent-hover text-white rounded-lg text-xs font-semibold shrink-0 disabled:opacity-60 disabled:cursor-wait transition-colors shadow-xs flex items-center gap-1.5 cursor-pointer"
            >
              {isTailoring && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              {isTailoring ? 'Tailoring…' : 'Tailor Resume'}
            </button>
          </div>
        </div>
        <div className="space-y-1">
          <label htmlFor="tailor-jd" className="font-semibold text-fg-2 text-xs">
            Paste job description <span className="font-normal text-muted">(optional)</span>
          </label>
          <textarea
            id="tailor-jd"
            rows={3}
            value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)}
            placeholder="Paste the job posting to find what your CV is missing for this role"
            className="w-full p-2 bg-inset border border-line-strong rounded-lg text-xs text-fg placeholder:text-subtle focus:outline-none focus:border-accent transition-all leading-relaxed"
          />
        </div>

        <div aria-live="polite" className="space-y-2">
          {isTailoring && (
            <p className="text-[11px] text-muted flex items-center gap-1.5">
              <RefreshCw className="w-3 h-3 animate-spin text-accent" />
              Asking the AI to rewrite from your CV only. This can take up to a minute.
            </p>
          )}

          {tailorError && (
            <div role="alert" className="p-2.5 rounded-lg border border-bad/30 bg-bad-soft text-[11px] text-bad flex items-start justify-between gap-2">
              <span>{tailorError}</span>
              <button type="button" onClick={() => setTailorError(null)} className="shrink-0 text-bad hover:text-fg cursor-pointer" aria-label="Dismiss error">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {proposals && (
            <div className="space-y-2.5 pt-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-fg">
                  {proposals.length ? `Proposed changes (${proposals.length})` : 'No changes suggested'}
                </span>
                <div className="flex items-center gap-1.5">
                  {proposals.some(p => p.status === 'pending') && (
                    <button
                      type="button"
                      onClick={() => resolveProposals(proposals.filter(p => p.status === 'pending').map(p => p.id), true)}
                      className="px-2.5 py-1 rounded-lg bg-accent hover:bg-accent-hover text-white text-[11px] font-semibold cursor-pointer"
                    >
                      Accept all
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={closeTailorReview}
                    className="px-2.5 py-1 rounded-lg border border-line-strong text-fg-2 hover:text-fg text-[11px] font-semibold cursor-pointer"
                  >
                    Close
                  </button>
                </div>
              </div>

              {proposals.map((p) => (
                <div key={p.id} data-proposal={p.id} className="p-2.5 rounded-lg border border-line bg-surface-2 space-y-1.5 text-[11px]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-fg-2">{p.label}</span>
                    {p.status === 'pending' ? (
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => resolveProposals([p.id], true)}
                          className="px-2 py-0.5 rounded-md bg-accent hover:bg-accent-hover text-white font-semibold cursor-pointer"
                        >
                          Accept
                        </button>
                        <button
                          type="button"
                          onClick={() => resolveProposals([p.id], false)}
                          className="px-2 py-0.5 rounded-md border border-line-strong text-fg-2 hover:text-fg font-semibold cursor-pointer"
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <span className={`font-semibold shrink-0 ${p.status === 'accepted' ? 'text-ok' : p.status === 'outdated' ? 'text-bad' : 'text-muted'}`}>
                        {p.status === 'accepted' ? 'Applied' : p.status === 'outdated' ? 'Not applied: you edited this field' : 'Rejected'}
                      </span>
                    )}
                  </div>
                  <div className="text-muted leading-relaxed"><span className="font-semibold text-subtle">Before: </span>{p.before || <em>(empty)</em>}</div>
                  <div className="text-fg leading-relaxed"><span className="font-semibold text-accent">After: </span>{p.after}</div>
                </div>
              ))}

              {tailorGaps.length > 0 && (
                <div className="p-2.5 rounded-lg border border-line bg-surface-2 space-y-1.5">
                  <div className="text-xs font-semibold text-fg">Missing for this role</div>
                  <p className="text-[11px] text-muted">Asked for by the job description but not shown in your CV. Not added to your CV.</p>
                  <div className="flex flex-wrap gap-1.5">
                    {tailorGaps.map((g) => (
                      <span key={g} className="px-2 py-0.5 rounded-md border border-line-strong bg-inset text-[11px] text-fg-2 font-mono">{g}</span>
                    ))}
                  </div>
                </div>
              )}

              {tailorNotes.length > 0 && (
                <ul className="list-disc pl-4 space-y-0.5 text-[11px] text-muted">
                  {tailorNotes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              )}
            </div>
          )}
        </div>
        {data.title && (
          <div className="pt-1 flex items-center justify-between text-[11px]">
            <span className="text-muted">Active CV Title: <strong className="text-fg">{data.title}</strong></span>
            <a
              href={`/jobs?query=${encodeURIComponent(data.title)}&source=cv`}
              className="text-accent hover:underline font-semibold flex items-center gap-1"
            >
              <span>Search Jobs for this Role →</span>
            </a>
          </div>
        )}
      </div>

    </div>
  );
}
