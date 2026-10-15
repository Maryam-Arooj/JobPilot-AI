'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AppShell } from '@/components/AppShell';
import { apiFetch, getAuthToken } from '@/lib/api';
import {
  User,
  CheckCircle2,
  AlertTriangle,
  Edit2,
  FileText,
  ShieldCheck,
  Plus,
  Save,
  RefreshCw,
  X,
  Upload,
  Briefcase,
  GraduationCap,
  Award,
  FolderOpen
} from 'lucide-react';

interface ProfileData {
  id?: number;
  completeness_pct?: number;
  personal?: {
    name?: string;
    email?: string;
    phone?: string;
    location?: string;
  };
  professional?: {
    target_role?: string;
    years_of_experience?: number;
    skills?: string[];
    summary?: string;
    linkedin?: string;
    github?: string;
  };
  education?: Array<{
    institution?: string;
    degree?: string;
    field?: string;
    year?: string | number;
  }>;
  experience?: Array<{
    company?: string;
    role?: string;
    duration?: string;
    description?: string;
  }>;
  skills?: Record<string, string[]> | { list?: string[] };
  projects?: Array<{
    name?: string;
    description?: string;
    technologies?: string[];
  }>;
  certifications?: Array<{
    name?: string;
    issuer?: string;
    year?: string | number;
  }>;
  facts?: Array<{
    id: number;
    fact_key: string;
    fact_value: string;
    source: string;
    verified: boolean;
  }>;
}

export default function CareerProfilePage() {
  const router = useRouter();
  // JWT lives in localStorage, so the auth check has to run client-side.
  useEffect(() => {
    if (!getAuthToken()) router.replace('/login');
  }, [router]);

  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Form State — starts completely empty, no mocked defaults
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [location, setLocation] = useState('');
  const [targetRole, setTargetRole] = useState('');
  const [yearsExp, setYearsExp] = useState<string>('');
  const [skillsStr, setSkillsStr] = useState('');
  const [certificationsStr, setCertificationsStr] = useState('');
  const [summary, setSummary] = useState('');
  const [linkedin, setLinkedin] = useState('');
  const [github, setGithub] = useState('');

  // Upload state
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  const loadProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch('/profiles/me');
      setProfile(data);
      // Populate form from real data only
      setName(data.personal?.name || '');
      setEmail(data.personal?.email || '');
      setPhone(data.personal?.phone || '');
      setLocation(data.personal?.location || '');
      setTargetRole(data.professional?.target_role || '');
      setYearsExp(String(data.professional?.years_of_experience || ''));
      setLinkedin(data.professional?.linkedin || '');
      setGithub(data.professional?.github || '');

      // Extract skills — handle both array and object formats
      const profSkills = data.professional?.skills;
      if (Array.isArray(profSkills)) {
        setSkillsStr(profSkills.join(', '));
      } else if (data.skills && typeof data.skills === 'object') {
        const allSkills: string[] = [];
        Object.values(data.skills as Record<string, string[]>).forEach(v => {
          if (Array.isArray(v)) allSkills.push(...v);
        });
        setSkillsStr(allSkills.join(', '));
      } else {
        setSkillsStr('');
      }

      // Extract certifications
      if (Array.isArray(data.certifications)) {
        const certNames = data.certifications.map((c: any) =>
          typeof c === 'string' ? c : [c.name || c.title, c.issuer, c.year].filter(Boolean).join(' · ')
        );
        setCertificationsStr(certNames.join(', '));
      } else {
        setCertificationsStr('');
      }

      setSummary(data.professional?.summary || '');
    } catch (err: any) {
      setError(`Failed to load profile: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProfile();
  }, []);

  const handleSaveProfile = async () => {
    setSaving(true);
    setSaveSuccess(false);
    setError(null);
    try {
      const skillsArray = skillsStr
        .split(',')
        .map(s => s.trim())
        .filter(Boolean);

      const certsArray = certificationsStr
        .split(',')
        .map(c => c.trim())
        .filter(Boolean);

      const updated = await apiFetch('/profiles/me', {
        method: 'PUT',
        body: JSON.stringify({
          personal: {
            name: name || undefined,
            email: email || undefined,
            phone: phone || undefined,
            location: location || undefined,
          },
          professional: {
            target_role: targetRole || undefined,
            years_of_experience: yearsExp ? Number(yearsExp) : undefined,
            skills: skillsArray.length > 0 ? skillsArray : undefined,
            summary: summary || undefined,
            linkedin: linkedin || undefined,
            github: github || undefined,
          },
          certifications: certsArray.length > 0 ? certsArray : undefined,
        }),
      });
      setProfile(updated);
      setIsEditing(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: any) {
      setError(`Save failed: ${err.message || err}`);
    } finally {
      setSaving(false);
    }
  };

  const handleUploadDocument = async () => {
    if (!uploadFile) return;
    setIsUploading(true);
    setUploadMsg(null);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      const result = await apiFetch('/documents/upload', {
        method: 'POST',
        body: formData,
      });
      setUploadMsg(`Document parsed successfully! Extracted ${result.facts?.length || 0} facts. Refresh to see updates.`);
      setUploadFile(null);
      await loadProfile();
    } catch (err: any) {
      setUploadMsg(`Upload failed: ${err.message || err}`);
    } finally {
      setIsUploading(false);
    }
  };

  const getSkillsDisplay = (): string[] => {
    if (!profile) return [];
    const profSkills = profile.professional?.skills;
    if (Array.isArray(profSkills) && profSkills.length > 0) return profSkills;
    if (profile.skills && typeof profile.skills === 'object') {
      const all: string[] = [];
      Object.values(profile.skills as Record<string, string[]>).forEach(v => {
        if (Array.isArray(v)) all.push(...v);
      });
      return all;
    }
    return [];
  };

  const skills = getSkillsDisplay();
  const isProfileEmpty = !profile?.personal?.name && !profile?.professional?.target_role;

  return (
    <AppShell>
      <div className="space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-line pb-6">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full border border-line bg-surface text-xs font-mono text-muted mb-2">
              <ShieldCheck className="w-3.5 h-3.5 text-ok" />
              <span>Real PostgreSQL Backend — Your Actual Data</span>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-fg">
              Career Profile
            </h1>
            <p className="text-xs md:text-sm text-muted mt-1">
              Your verified career information. All data you enter is saved to the database and persists on refresh.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsEditing(!isEditing)}
              className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white font-medium text-xs transition-colors flex items-center gap-1.5 shadow-xs"
            >
              <Edit2 className="w-3.5 h-3.5" />
              <span>{isEditing ? 'Cancel' : 'Edit Profile'}</span>
            </button>
            <button
              onClick={loadProfile}
              className="p-2 rounded-lg bg-surface border border-line text-muted hover:text-fg"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="p-4 bg-bad-soft border border-bad/30 rounded-xl text-xs text-bad">
            ⚠️ {error}
          </div>
        )}

        {/* Success Banner */}
        {saveSuccess && (
          <div className="p-4 bg-ok-soft border border-ok/30 rounded-xl text-xs text-ok flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            Profile saved to database successfully!
          </div>
        )}

        {/* Profile Completeness */}
        <div className="card-base p-4 bg-surface border border-line rounded-xl space-y-2">
          <div className="flex items-center justify-between text-xs font-mono">
            <span className="font-semibold text-fg">Profile Completeness</span>
            <span className="text-ok font-bold">{profile?.completeness_pct || 0}%</span>
          </div>
          <div className="w-full bg-surface-2 rounded-full h-2 overflow-hidden border border-line">
            <div
              className="bg-accent h-full rounded-full transition-all duration-500"
              style={{ width: `${profile?.completeness_pct || 0}%` }}
            />
          </div>
          {isProfileEmpty && (
            <p className="text-[11px] text-pending font-mono mt-1">
              ↑ Click "Edit Profile" to fill in your information.
            </p>
          )}
        </div>

        {/* Edit Form */}
        {isEditing ? (
          <div className="card-base p-6 bg-surface border border-line rounded-xl space-y-5">
            <h3 className="text-sm font-bold text-fg border-b border-line pb-2">
              Edit Your Profile Information
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              {[
                { label: 'Full Name', value: name, set: setName, placeholder: 'e.g. Ali Hassan' },
                { label: 'Email Address', value: email, set: setEmail, placeholder: 'ali@example.com' },
                { label: 'Phone Number', value: phone, set: setPhone, placeholder: '+92 300 0000000' },
                { label: 'Location', value: location, set: setLocation, placeholder: 'Lahore, Pakistan' },
                { label: 'Target Role', value: targetRole, set: setTargetRole, placeholder: 'Senior AI Engineer' },
                { label: 'Years of Experience', value: yearsExp, set: setYearsExp, placeholder: '3' },
                { label: 'LinkedIn URL', value: linkedin, set: setLinkedin, placeholder: 'linkedin.com/in/yourname' },
                { label: 'GitHub URL', value: github, set: setGithub, placeholder: 'github.com/yourname' },
              ].map(({ label, value, set, placeholder }) => (
                <div key={label} className="space-y-1">
                  <label className="font-semibold text-fg">{label}</label>
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => set(e.target.value)}
                    placeholder={placeholder}
                    className="w-full bg-inset border border-line rounded-lg p-2.5 text-xs text-fg focus:outline-none focus:border-accent"
                  />
                </div>
              ))}

              <div className="md:col-span-2 space-y-1">
                <label className="font-semibold text-fg">
                  Technical Skills <span className="font-normal text-subtle">(comma-separated)</span>
                </label>
                <input
                  type="text"
                  value={skillsStr}
                  onChange={(e) => setSkillsStr(e.target.value)}
                  placeholder="Python, FastAPI, React, PostgreSQL, Docker, AWS"
                  className="w-full bg-inset border border-line rounded-lg p-2.5 text-xs text-fg focus:outline-none focus:border-accent"
                />
              </div>

              <div className="md:col-span-2 space-y-1">
                <label className="font-semibold text-fg">
                  Certifications & Licenses <span className="font-normal text-subtle">(comma-separated)</span>
                </label>
                <input
                  type="text"
                  value={certificationsStr}
                  onChange={(e) => setCertificationsStr(e.target.value)}
                  placeholder="AWS Certified Solutions Architect, Google Analytics Certified, CKA"
                  className="w-full bg-inset border border-line rounded-lg p-2.5 text-xs text-fg focus:outline-none focus:border-accent"
                />
              </div>

              <div className="md:col-span-2 space-y-1">
                <label className="font-semibold text-fg">Professional Summary</label>
                <textarea
                  rows={4}
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  placeholder="Describe your professional background, expertise, and career goals..."
                  className="w-full bg-inset border border-line rounded-lg p-2.5 text-xs text-fg focus:outline-none focus:border-accent"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-line">
              <button
                onClick={() => setIsEditing(false)}
                className="bg-surface hover:bg-surface-2 border border-line text-fg text-xs font-semibold px-4 py-2 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveProfile}
                disabled={saving}
                className="bg-accent hover:bg-accent-hover text-white text-xs font-semibold px-5 py-2 rounded-lg transition-colors flex items-center gap-1.5 shadow-xs disabled:opacity-60"
              >
                <Save className="w-3.5 h-3.5" />
                {saving ? 'Saving...' : 'Save to Database'}
              </button>
            </div>
          </div>
        ) : (
          /* Profile View */
          <div className="space-y-6">
            {/* Identity Card */}
            <div className="card-base p-6 bg-surface border border-line rounded-xl">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
                <div className="space-y-1">
                  <span className="text-[10px] font-mono text-subtle uppercase tracking-wider block">Identity</span>
                  <h2 className="text-xl font-bold text-fg">
                    {name || <span className="text-subtle font-normal italic">No name set — click Edit Profile</span>}
                  </h2>
                  <p className="text-muted font-mono">{email || '—'}</p>
                  <p className="text-muted">{location || '—'}</p>
                  {phone && <p className="text-muted">{phone}</p>}
                </div>

                <div className="space-y-2">
                  <span className="text-[10px] font-mono text-subtle uppercase tracking-wider block">Target Position</span>
                  <div className="text-sm font-bold text-fg">
                    {targetRole || <span className="text-subtle font-normal italic">Not specified</span>}
                  </div>
                  {yearsExp && (
                    <div className="text-xs text-muted">{yearsExp} years experience</div>
                  )}
                  <div className="text-xs text-muted leading-relaxed">
                    {summary || <span className="italic text-subtle">No summary set</span>}
                  </div>
                  <div className="flex gap-3 text-[11px] text-muted font-mono pt-1">
                    {linkedin && <a href={linkedin} target="_blank" rel="noopener noreferrer" className="hover:text-fg underline">LinkedIn</a>}
                    {github && <a href={github} target="_blank" rel="noopener noreferrer" className="hover:text-fg underline">GitHub</a>}
                  </div>
                </div>
              </div>
            </div>

            {/* Skills */}
            <div className="card-base p-5 bg-surface border border-line rounded-xl space-y-3">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-subtle">Technical Skills</h3>
              <div className="flex flex-wrap gap-1.5">
                {skills.length > 0 ? (
                  skills.map((skill, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded text-xs font-mono bg-inset text-fg border border-line"
                    >
                      {skill}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-subtle italic">
                    No skills added yet. Click "Edit Profile" to add your technical skills.
                  </span>
                )}
              </div>
            </div>

            {/* Experience */}
            {(profile?.experience?.length ?? 0) > 0 && (
              <div className="card-base p-5 bg-surface border border-line rounded-xl space-y-3">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-subtle flex items-center gap-1.5">
                  <Briefcase className="w-3.5 h-3.5" /> Work Experience
                </h3>
                <div className="space-y-3">
                  {profile?.experience?.map((exp, idx) => (
                    <div key={idx} className="border-l-2 border-line pl-3 space-y-0.5">
                      <div className="text-xs font-bold text-fg">{exp.role}</div>
                      <div className="text-[11px] text-muted">{exp.company} {exp.duration && `· ${exp.duration}`}</div>
                      {exp.description && <p className="text-[11px] text-muted">{exp.description}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Education */}
            {(profile?.education?.length ?? 0) > 0 && (
              <div className="card-base p-5 bg-surface border border-line rounded-xl space-y-3">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-subtle flex items-center gap-1.5">
                  <GraduationCap className="w-3.5 h-3.5" /> Education
                </h3>
                <div className="space-y-2">
                  {profile?.education?.map((edu, idx) => (
                    <div key={idx} className="border-l-2 border-line pl-3">
                      <div className="text-xs font-bold text-fg">{edu.degree} {edu.field && `in ${edu.field}`}</div>
                      <div className="text-[11px] text-muted">{edu.institution} {edu.year && `· ${edu.year}`}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Certifications */}
            {(profile?.certifications?.length ?? 0) > 0 && (
              <div className="card-base p-5 bg-surface border border-line rounded-xl space-y-3">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-subtle flex items-center gap-1.5">
                  <Award className="w-3.5 h-3.5" /> Certifications
                </h3>
                <div className="flex flex-wrap gap-2">
                  {profile?.certifications?.map((cert: any, idx) => {
                    const certDisplay = typeof cert === 'string'
                      ? cert
                      : [cert.name || cert.title, cert.issuer, cert.year].filter(Boolean).join(' · ');
                    return (
                      <span key={idx} className="px-2.5 py-1 bg-inset border border-line rounded text-xs text-fg font-medium flex items-center gap-1.5">
                        <Award className="w-3 h-3 text-accent" />
                        {certDisplay}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Projects */}
            {(profile?.projects?.length ?? 0) > 0 && (
              <div className="card-base p-5 bg-surface border border-line rounded-xl space-y-3">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-subtle flex items-center gap-1.5">
                  <FolderOpen className="w-3.5 h-3.5" /> Projects
                </h3>
                <div className="space-y-3">
                  {profile?.projects?.map((proj, idx) => (
                    <div key={idx} className="border-l-2 border-line pl-3 space-y-1">
                      <div className="text-xs font-bold text-fg">{proj.name}</div>
                      {proj.description && <p className="text-[11px] text-muted">{proj.description}</p>}
                      {(proj.technologies?.length ?? 0) > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {proj.technologies?.map((t, i) => (
                            <span key={i} className="text-[10px] font-mono bg-surface-2 px-1.5 py-0.5 rounded border border-line text-fg">{t}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Document Upload Section */}
        <div className="card-base p-5 bg-surface border border-line rounded-xl space-y-4">
          <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-subtle flex items-center gap-1.5">
            <Upload className="w-3.5 h-3.5" /> Upload CV / Resume / Certificate
          </h3>
          <p className="text-xs text-muted">
            Upload a PDF or DOCX file to automatically extract profile information. Parsed facts will be added to your profile.
          </p>
          <div className="flex items-center gap-3">
            <input
              type="file"
              accept=".pdf,.docx,.doc,.txt"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
              className="text-xs text-fg file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border file:border-line file:text-xs file:font-medium file:bg-inset file:text-fg hover:file:bg-line-strong file:cursor-pointer"
            />
            <button
              onClick={handleUploadDocument}
              disabled={!uploadFile || isUploading}
              className="px-4 py-2 bg-accent text-white text-xs font-medium rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              <Upload className="w-3.5 h-3.5" />
              {isUploading ? 'Parsing...' : 'Upload & Parse'}
            </button>
          </div>
          {uploadMsg && (
            <div className={`p-3 rounded-lg text-xs ${uploadMsg.includes('failed') ? 'bg-bad-soft border border-bad/30 text-bad' : 'bg-ok-soft border border-ok/30 text-ok'}`}>
              {uploadMsg}
            </div>
          )}
        </div>

        {/* Extracted Facts */}
        {(profile?.facts?.length ?? 0) > 0 && (
          <div className="space-y-3">
            <h3 className="text-xs font-mono uppercase tracking-wider text-subtle font-semibold">
              Extracted Facts ({profile?.facts?.length})
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {profile?.facts?.map((fact) => (
                <div
                  key={fact.id}
                  className="card-base p-4 bg-surface border border-line rounded-xl flex items-start justify-between gap-3"
                >
                  <div className="space-y-0.5 flex-1 min-w-0">
                    <div className="text-[10px] font-mono text-subtle uppercase tracking-wider">{fact.fact_key}</div>
                    <div className="text-xs font-bold text-fg truncate">{fact.fact_value}</div>
                    <div className="text-[10px] font-mono text-subtle">Source: {fact.source}</div>
                  </div>
                  {fact.verified ? (
                    <span className="text-[10px] font-mono text-ok bg-ok-soft px-2 py-0.5 rounded border border-ok/30 flex items-center gap-1 shrink-0">
                      <CheckCircle2 className="w-3 h-3" /> Verified
                    </span>
                  ) : (
                    <span className="text-[10px] font-mono text-pending bg-pending-soft px-2 py-0.5 rounded border border-pending/30 flex items-center gap-1 shrink-0">
                      <AlertTriangle className="w-3 h-3" /> Pending
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </AppShell>
  );
}
