'use client';

import React from 'react';
import { Download, FileText, Printer, CheckCircle2, Sparkles, Building2, GraduationCap, Code, Mail, Phone, MapPin, Globe, Award } from 'lucide-react';

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

// html2canvas (bundled in html2pdf.js) can't parse the lab()/oklch() colours that
// Tailwind v4 computes, so Download PDF used to fail and fall back to window.print().
// On html2canvas's cloned document, resolve every colour to rgba() before it renders.
// The live page and the template styles are untouched.
const MODERN_COLOR = /(?:ok)?(?:lab|lch)\([^)]*\)|color\([^)]*\)/g;

function resolveModernColors(clonedDoc: Document) {
  // html2pdf renders its own copy of #printable-cv inside an overlay container,
  // so the clone holds more than one; resolve every copy and its ancestors.
  const roots = Array.from(clonedDoc.querySelectorAll<HTMLElement>('#printable-cv'));
  const view = clonedDoc.defaultView;
  if (!roots.length || !view) return;
  const canvas = clonedDoc.createElement('canvas');
  canvas.width = canvas.height = 1;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return;
  const cache = new Map<string, string>();
  const toRgba = (token: string) => {
    const hit = cache.get(token);
    if (hit) return hit;
    ctx.clearRect(0, 0, 1, 1);
    ctx.fillStyle = '#000';
    ctx.fillStyle = token;
    ctx.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
    const rgba = `rgba(${r}, ${g}, ${b}, ${+(a / 255).toFixed(3)})`;
    cache.set(token, rgba);
    return rgba;
  };
  const targets = new Set<Element>();
  roots.forEach((root) => {
    for (let el: Element | null = root; el; el = el.parentElement) targets.add(el);
    root.querySelectorAll('*').forEach((el) => targets.add(el));
  });
  // Every computed property, not a fixed list: html2canvas also parses ones such as
  // -webkit-text-stroke-color, which on SVG icons can stay lab() after `color` is set.
  targets.forEach((el) => {
    const cs = view.getComputedStyle(el);
    const updates: Array<[string, string]> = [];
    for (let i = 0; i < cs.length; i++) {
      const prop = cs[i];
      if (prop.startsWith('--')) continue;
      const value = cs.getPropertyValue(prop);
      if (value && MODERN_COLOR.test(value)) updates.push([prop, value.replace(MODERN_COLOR, toRgba)]);
      MODERN_COLOR.lastIndex = 0;
    }
    updates.forEach(([prop, value]) => (el as HTMLElement).style.setProperty(prop, value));
  });
}

interface ResumeData {
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
  certifications?: Array<string | { name?: string; title?: string; issuer?: string; year?: string | number; date?: string }>;
}

interface ResumePreviewProps {
  resume?: ResumeData;
  templateName?: string;
}

export function ResumePreview({
  resume,
  templateName = 'Europass Standard'
}: ResumePreviewProps) {
  const name = resume?.name || 'Your Name';
  const email = resume?.email || '';
  const phone = resume?.phone || '';
  const location = resume?.location || '';
  const linkedin = resume?.linkedin;
  const github = resume?.github;
  const website = resume?.website;
  const photoUrl = resume?.photo_url;
  const summary = resume?.summary || '';
  const skills = resume?.skills || [];
  const certifications = resume?.certifications || [];

  const formatCertification = (cert: any): string => {
    if (!cert) return '';
    if (typeof cert === 'string') return cert;
    const name = cert.name || cert.title || '';
    const issuer = cert.issuer || cert.authority || '';
    const date = cert.year || cert.date || '';
    const parts = [name, issuer, date ? `(${date})` : ''].filter(Boolean);
    return parts.join(' · ') || String(cert);
  };

  const [isExporting, setIsExporting] = React.useState(false);

  const handleDownloadPDF = async () => {
    if (typeof window === 'undefined') return;
    const cvElem = document.getElementById('printable-cv');
    if (!cvElem) return;

    setIsExporting(true);
    try {
      // Dynamic import to prevent SSR issues
      const html2pdfModule = await import('html2pdf.js');
      const html2pdf = html2pdfModule.default || html2pdfModule;
      
      const safeName = (name || 'Curriculum_Vitae').trim().replace(/[^a-zA-Z0-9_-]/g, '_');
      const safeTemplate = (templateName || 'CV').trim().replace(/[^a-zA-Z0-9_-]/g, '_');
      const filename = `${safeName}_${safeTemplate}.pdf`;

      const opt = {
        margin: [8, 8, 8, 8] as [number, number, number, number],
        filename: filename,
        image: { type: 'jpeg' as const, quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true, logging: false, onclone: resolveModernColors },
        jsPDF: { unit: 'mm' as const, format: 'a4', orientation: 'portrait' as const }
      };

      await html2pdf().set(opt).from(cvElem).save();
    } catch (err) {
      console.warn('Direct PDF export error, falling back to print dialog:', err);
      window.print();
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      
      {/* Document Control Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-white border border-[#E2E8F0] rounded-xl text-xs shadow-xs print:hidden">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-[#003366]" />
          <span className="font-bold text-[#0F172A]">{resume?.title || 'Untitled CV'}</span>
        </div>

        <div className="flex items-center gap-2">
          <a
            href={`/jobs?query=${encodeURIComponent(resume?.title || '')}&source=cv`}
            className="px-3 py-1.5 rounded-lg border border-[#BAE6FD] bg-[#F0F9FF] hover:bg-[#E0F2FE] text-[#003366] font-bold text-xs transition-colors flex items-center gap-1.5 shadow-2xs cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5 text-[#0284C7]" />
            <span>Find Jobs for CV</span>
          </a>
          <button
            onClick={() => window.print()}
            className="px-3 py-1.5 rounded-lg border border-[#E2E8F0] bg-[#F8FAFC] hover:bg-[#F1F5F9] text-[#0F172A] font-semibold text-xs transition-colors flex items-center gap-1.5 shadow-2xs cursor-pointer"
          >
            <Printer className="w-3.5 h-3.5 text-[#64748B]" />
            <span>Print / Dialog</span>
          </button>
          <button
            onClick={handleDownloadPDF}
            disabled={isExporting}
            className="px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-[#003366] to-[#1E3A8A] hover:from-[#002244] hover:to-[#003366] text-white font-bold text-xs transition-all flex items-center gap-1.5 shadow-sm hover:shadow-md disabled:opacity-75 cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>{isExporting ? 'Generating PDF...' : 'Download PDF File'}</span>
          </button>
        </div>
      </div>

      <div>
      {/* ISOLATED PRINTABLE CV WRAPPER */}
      <div id="printable-cv" className="w-full cv-paper">
        {/* RENDER TEMPLATE STYLE 0: EUROPASS OFFICIAL STANDARD */}
        {templateName === 'Europass Standard' && (
          <div className="bg-white border border-[#E2E8F0] rounded-2xl p-8 md:p-10 shadow-xs space-y-6 text-[#0F172A] font-sans max-w-4xl mx-auto border-t-6 border-t-[#003366]">
            {/* Europass Clean Header */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b-2 border-[#003366]/15 pb-6 gap-6">
              <div className="flex items-center gap-4 sm:gap-5">
                {photoUrl ? (
                  <div className="relative shrink-0">
                    <img
                      src={photoUrl}
                      alt={name}
                      className="w-20 h-20 sm:w-24 sm:h-24 rounded-2xl object-cover border-2 border-[#003366] shadow-xs bg-white"
                    />
                  </div>
                ) : (
                  <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-2xl bg-[#F0F9FF] border-2 border-dashed border-[#003366]/30 flex items-center justify-center text-[#003366] font-bold text-lg shrink-0">
                    {name.split(' ').map(n => n[0]).join('')}
                  </div>
                )}
                <div className="space-y-1">
                  <span className="inline-block px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-[#003366] text-white font-mono shadow-2xs">
                    EUROPASS CURRICULUM VITAE
                  </span>
                  <h1 className="text-2xl sm:text-3xl font-extrabold text-[#003366] tracking-tight">{name}</h1>
                  <p className="text-xs sm:text-sm font-semibold text-[#475569]">{resume?.title || ''}</p>
                </div>
              </div>

              <div className="text-xs space-y-1.5 text-[#334155] bg-[#F8FAFC] p-3.5 sm:p-4 rounded-xl border border-[#E2E8F0] self-stretch sm:self-auto min-w-[220px]">
                {email && (
                  <div className="flex items-center gap-2 font-bold text-[#003366]">
                    <Mail className="w-3.5 h-3.5 text-[#003366] shrink-0" />
                    <span className="truncate">{email}</span>
                  </div>
                )}
                {phone && (
                  <div className="flex items-center gap-2 text-[#475569]">
                    <Phone className="w-3.5 h-3.5 text-[#64748B] shrink-0" />
                    <span>{phone}</span>
                  </div>
                )}
                {location && (
                  <div className="flex items-center gap-2 text-[#475569]">
                    <MapPin className="w-3.5 h-3.5 text-[#64748B] shrink-0" />
                    <span>{location}</span>
                  </div>
                )}
                {linkedin && (
                  <div className="flex items-center gap-2 text-[#475569]">
                    <LinkedinIcon className="w-3.5 h-3.5 text-[#003366] shrink-0" />
                    <span className="truncate">{linkedin}</span>
                  </div>
                )}
                {github && (
                  <div className="flex items-center gap-2 text-[#475569]">
                    <GithubIcon className="w-3.5 h-3.5 text-[#181816] shrink-0" />
                    <span className="truncate">{github}</span>
                  </div>
                )}
                {website && (
                  <div className="flex items-center gap-2 text-[#475569]">
                    <Globe className="w-3.5 h-3.5 text-[#003366] shrink-0" />
                    <span className="truncate">{website}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Section: Personal Statement */}
            <div className="grid grid-cols-12 gap-6 items-start">
              <div className="col-span-12 sm:col-span-3 font-bold text-xs uppercase tracking-wider text-[#003366] sm:border-r-2 sm:border-[#003366]/20 sm:pr-4 pt-0.5">
                Personal Statement
              </div>
              <div className="col-span-12 sm:col-span-9 text-xs leading-relaxed text-[#0F172A] font-normal">
                {summary}
              </div>
            </div>

            {/* Section: Work Experience */}
            <div className="grid grid-cols-12 gap-6 items-start border-t border-[#E2E8F0] pt-6">
              <div className="col-span-12 sm:col-span-3 font-bold text-xs uppercase tracking-wider text-[#003366] sm:border-r-2 sm:border-[#003366]/20 sm:pr-4 pt-0.5">
                Work Experience
              </div>
              <div className="col-span-12 sm:col-span-9 space-y-5 text-xs">
                {resume?.experience?.map((exp, idx) => (
                  <div key={idx} className="space-y-1.5">
                    <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center font-bold">
                      <span className="text-[#003366] text-xs font-bold">{exp.role}</span>
                      <span className="font-mono text-[11px] text-[#64748B]">{exp.period}</span>
                    </div>
                    <div className="text-xs font-semibold text-[#475569]">{exp.company}{exp.location ? `, ${exp.location}` : ''}</div>
                    <ul className="list-disc pl-4 text-xs space-y-1 text-[#0F172A] leading-relaxed pt-1">
                      {(exp.bullets || []).map((b, bIdx) => (
                        <li key={bIdx}>{b}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>

            {/* Section: Education */}
            <div className="grid grid-cols-12 gap-6 items-start border-t border-[#E2E8F0] pt-6">
              <div className="col-span-12 sm:col-span-3 font-bold text-xs uppercase tracking-wider text-[#003366] sm:border-r-2 sm:border-[#003366]/20 sm:pr-4 pt-0.5">
                Education & Training
              </div>
              <div className="col-span-12 sm:col-span-9 space-y-3 text-xs">
                {resume?.education?.map((edu, idx) => (
                  <div key={idx} className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-1">
                    <div>
                      <div className="font-bold text-[#0F172A]">{edu.degree}</div>
                      <div className="text-[#64748B]">{edu.institution}{edu.location ? `, ${edu.location}` : ''}</div>
                    </div>
                    <span className="font-mono text-[#64748B] text-[11px] font-semibold">{edu.year}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Section: Skills & Competencies */}
            <div className="grid grid-cols-12 gap-6 items-start border-t border-[#E2E8F0] pt-6">
              <div className="col-span-12 sm:col-span-3 font-bold text-xs uppercase tracking-wider text-[#003366] sm:border-r-2 sm:border-[#003366]/20 sm:pr-4 pt-0.5">
                Personal Skills
              </div>
              <div className="col-span-12 sm:col-span-9 flex flex-wrap gap-2 text-xs">
                {skills.map((s, idx) => (
                  <span key={idx} className="px-3 py-1 bg-[#F0F9FF] text-[#003366] font-semibold border border-[#BAE6FD] rounded-lg text-xs font-mono shadow-2xs">
                    {s}
                  </span>
                ))}
              </div>
            </div>

            {/* Section: Certifications & Accreditations */}
            {certifications && certifications.length > 0 && (
              <div className="grid grid-cols-12 gap-6 items-start border-t border-[#E2E8F0] pt-6">
                <div className="col-span-12 sm:col-span-3 font-bold text-xs uppercase tracking-wider text-[#003366] sm:border-r-2 sm:border-[#003366]/20 sm:pr-4 pt-0.5">
                  Certifications
                </div>
                <div className="col-span-12 sm:col-span-9 space-y-2 text-xs">
                  {certifications.map((cert, idx) => (
                    <div key={idx} className="flex items-center gap-2 font-semibold text-[#003366]">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[#003366] shrink-0" />
                      <span>{formatCertification(cert)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

      {/* RENDER TEMPLATE STYLE 1: ATS CLEAN (Authentic High-Impact Standard) */}
      {(templateName.includes('ATS') || templateName === 'ATS Clean (Standard)' || templateName === 'ATS Clean') && (
        <div className="bg-white border border-[#D1D5DB] rounded-xl p-8 sm:p-12 md:p-14 shadow-md space-y-5 text-black font-sans max-w-4xl mx-auto leading-normal">
          {/* Header Section */}
          <div className="text-center space-y-1.5 pb-2">
            {photoUrl && (
              <div className="flex justify-center mb-3">
                <img
                  src={photoUrl}
                  alt={name}
                  className="w-20 h-20 rounded-full object-cover border border-black shadow-xs bg-white"
                />
              </div>
            )}
            <h1 className="text-2xl sm:text-3xl font-extrabold uppercase tracking-tight text-black">
              {name}
            </h1>
            
            {resume?.title && (
              <p className="text-xs sm:text-sm font-bold text-black tracking-wide">
                {resume.title}
              </p>
            )}

            {/* Pipe-separated Contact and Social Line */}
            <div className="text-xs text-neutral-800 font-medium flex flex-wrap items-center justify-center gap-x-2 gap-y-1 pt-0.5">
              {location && <span>{location}</span>}
              {location && email && <span className="text-neutral-400">|</span>}
              {email && <span>{email}</span>}
              {(email || location) && phone && <span className="text-neutral-400">|</span>}
              {phone && <span>{phone}</span>}
              {linkedin && (
                <>
                  <span className="text-neutral-400">|</span>
                  <span className="text-neutral-900">{linkedin.replace(/^https?:\/\/(www\.)?/, '')}</span>
                </>
              )}
              {github && (
                <>
                  <span className="text-neutral-400">|</span>
                  <span className="text-neutral-900">{github.replace(/^https?:\/\/(www\.)?/, '')}</span>
                </>
              )}
              {website && (
                <>
                  <span className="text-neutral-400">|</span>
                  <span className="text-neutral-900">{website.replace(/^https?:\/\/(www\.)?/, '')}</span>
                </>
              )}
            </div>
          </div>

          {/* Professional Summary */}
          {summary && (
            <div className="space-y-1.5">
              <h2 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-black border-b border-black pb-0.5">
                Professional Summary
              </h2>
              <p className="text-xs sm:text-[13px] text-neutral-900 leading-relaxed text-justify">
                {summary}
              </p>
            </div>
          )}

          {/* Work Experience */}
          {resume?.experience && resume.experience.length > 0 && (
            <div className="space-y-3.5">
              <h2 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-black border-b border-black pb-0.5">
                Work Experience
              </h2>
              <div className="space-y-4">
                {resume.experience.map((exp, idx) => (
                  <div key={idx} className="space-y-1">
                    <div className="flex flex-col sm:flex-row sm:justify-between sm:items-baseline gap-0.5">
                      <span className="font-bold text-black text-xs sm:text-[13px]">{exp.role}</span>
                      <span className="font-bold text-neutral-800 text-xs sm:text-[12px]">{exp.period}</span>
                    </div>
                    <div className="text-xs sm:text-[12px] font-semibold text-neutral-700">
                      {exp.company}{exp.location ? `, ${exp.location}` : ''}
                    </div>
                    {exp.bullets && exp.bullets.length > 0 && (
                      <ul className="list-disc pl-5 text-xs sm:text-[12.5px] space-y-1 text-neutral-900 leading-relaxed mt-1">
                        {exp.bullets.map((b, bIdx) => (
                          <li key={bIdx}>{b}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Education */}
          {resume?.education && resume.education.length > 0 && (
            <div className="space-y-2.5">
              <h2 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-black border-b border-black pb-0.5">
                Education
              </h2>
              <div className="space-y-3">
                {resume.education.map((edu, idx) => (
                  <div key={idx} className="space-y-0.5">
                    <div className="flex flex-col sm:flex-row sm:justify-between sm:items-baseline gap-0.5">
                      <span className="font-bold text-black text-xs sm:text-[13px]">{edu.degree}</span>
                      <span className="font-bold text-neutral-800 text-xs sm:text-[12px]">
                        {edu.year.toLowerCase().includes('grad') ? edu.year : `Graduated: ${edu.year}`}
                      </span>
                    </div>
                    <div className="text-xs sm:text-[12px] text-neutral-700 font-semibold">
                      {edu.institution}{edu.location ? `, ${edu.location}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Skills */}
          {skills && skills.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-black border-b border-black pb-0.5">
                Skills
              </h2>
              <ul className="list-disc pl-5 text-xs sm:text-[12.5px] space-y-1 text-neutral-900 leading-relaxed">
                {skills.map((skill, idx) => (
                  <li key={idx}>{skill}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Certifications (Optional) */}
          {certifications && certifications.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-black border-b border-black pb-0.5">
                Certifications
              </h2>
              <ul className="list-disc pl-5 text-xs sm:text-[12.5px] space-y-1 text-neutral-900 leading-relaxed">
                {certifications.map((cert, idx) => (
                  <li key={idx}>{formatCertification(cert)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* RENDER TEMPLATE STYLE 2: MODERN PROFESSIONAL (Executive Sidebar Layout) */}
      {(templateName.includes('Executive') || templateName === 'Modern Executive' || templateName === 'Modern Professional') && (
        <div className="bg-white border border-[#E4E4DF] rounded-xl shadow-md grid grid-cols-12 overflow-hidden max-w-4xl mx-auto">
          {/* Left Sidebar */}
          <div className="col-span-12 md:col-span-4 bg-[#F8FAFC] p-6 sm:p-7 border-r border-[#E2E8F0] space-y-6 text-xs text-[#0F172A]">
            <div>
              {photoUrl && (
                <img
                  src={photoUrl}
                  alt={name}
                  className="w-20 h-20 rounded-full object-cover border-2 border-[#003366] mb-3 shadow-xs"
                />
              )}
              <h1 className="text-xl font-bold text-[#0F172A]">{name}</h1>
              {resume?.title && <p className="text-xs font-semibold text-[#003366] mt-0.5">{resume.title}</p>}
              {location && <p className="text-[11px] font-mono text-[#64748B] mt-1">{location}</p>}
            </div>

            <div className="space-y-2 font-mono text-[11px] text-[#475569] border-t border-[#E2E8F0] pt-4">
              <div className="font-bold uppercase text-[#003366] text-[10px] tracking-wider">Contact & Social</div>
              {email && <div className="truncate flex items-center gap-1.5"><Mail className="w-3 h-3 text-[#003366]" /> {email}</div>}
              {phone && <div className="flex items-center gap-1.5"><Phone className="w-3 h-3 text-[#003366]" /> {phone}</div>}
              {linkedin && (
                <div className="truncate flex items-center gap-1.5">
                  <LinkedinIcon className="w-3 h-3 text-[#0077B5]" /> {linkedin.replace(/^https?:\/\/(www\.)?/, '')}
                </div>
              )}
              {github && (
                <div className="truncate flex items-center gap-1.5">
                  <GithubIcon className="w-3 h-3 text-[#0F172A]" /> {github.replace(/^https?:\/\/(www\.)?/, '')}
                </div>
              )}
              {website && (
                <div className="truncate flex items-center gap-1.5">
                  <Globe className="w-3 h-3 text-[#003366]" /> {website.replace(/^https?:\/\/(www\.)?/, '')}
                </div>
              )}
            </div>

            <div className="space-y-2 border-t border-[#E2E8F0] pt-4">
              <div className="font-bold uppercase text-[#003366] text-[10px] tracking-wider font-mono">Competencies</div>
              <div className="flex flex-wrap gap-1.5">
                {skills.map((s, idx) => (
                  <span key={idx} className="px-2 py-0.5 rounded text-[10px] font-semibold bg-white text-[#003366] border border-[#CBD5E1] shadow-2xs">
                    {s}
                  </span>
                ))}
              </div>
            </div>

            <div className="space-y-2 border-t border-[#E2E8F0] pt-4">
              <div className="font-bold uppercase text-[#003366] text-[10px] tracking-wider font-mono">Education</div>
              {resume?.education?.map((edu, idx) => (
                <div key={idx} className="space-y-0.5">
                  <div className="font-bold text-[#0F172A] text-[11px]">{edu.degree}</div>
                  <div className="text-[#64748B] text-[10px]">{edu.institution} ({edu.year})</div>
                </div>
              ))}
            </div>

            {certifications && certifications.length > 0 && (
              <div className="space-y-2 border-t border-[#E2E8F0] pt-4">
                <div className="font-bold uppercase text-[#003366] text-[10px] tracking-wider font-mono">Certifications</div>
                <div className="space-y-1.5">
                  {certifications.map((cert, idx) => (
                    <div key={idx} className="flex items-start gap-1.5 text-[11px] text-[#0F172A] font-medium">
                      <Award className="w-3.5 h-3.5 text-[#003366] shrink-0 mt-0.5" />
                      <span>{formatCertification(cert)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Main Column */}
          <div className="col-span-12 md:col-span-8 p-6 sm:p-8 space-y-6 text-xs text-[#0F172A]">
            <div className="space-y-1.5 border-b border-[#E2E8F0] pb-4">
              <h2 className="font-bold text-xs uppercase text-[#003366] tracking-wider">Executive Overview</h2>
              <p className="text-xs leading-relaxed text-[#334155]">{summary}</p>
            </div>

            <div className="space-y-4">
              <h2 className="font-bold text-xs uppercase text-[#003366] tracking-wider border-b border-[#E2E8F0] pb-1">Professional Experience</h2>
              {resume?.experience?.map((exp, idx) => (
                <div key={idx} className="space-y-1.5">
                  <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center font-bold">
                    <span className="text-[#0F172A] text-xs sm:text-[13px]">{exp.role}</span>
                    <span className="font-mono text-[11px] text-[#64748B]">{exp.period}</span>
                  </div>
                  <div className="text-xs font-semibold text-[#003366]">{exp.company}{exp.location ? `, ${exp.location}` : ''}</div>
                  <ul className="list-disc pl-4 space-y-1 text-xs text-[#334155] leading-relaxed">
                    {(exp.bullets || []).map((b, bIdx) => (
                      <li key={bIdx}>{b}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* RENDER TEMPLATE STYLE 3: TECHNICAL SPECIALIST (High-Density Engineering Layout) */}
      {(templateName.includes('Technical') || templateName === 'Technical Specialist') && (
        <div className="bg-white border border-[#E4E4DF] rounded-xl p-8 md:p-10 shadow-md space-y-6 text-[#181816] font-sans max-w-4xl mx-auto">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b-2 border-[#181816] pb-4 gap-4">
            <div className="flex items-center gap-4">
              {photoUrl && (
                <img
                  src={photoUrl}
                  alt={name}
                  className="w-16 h-16 rounded-xl object-cover border-2 border-[#181816] shrink-0 shadow-xs bg-white"
                />
              )}
              <div>
                <h1 className="text-2xl font-mono font-bold text-[#181816]">{name}</h1>
                {(location || email || phone) && (
                  <div className="text-xs font-mono text-[#6F6F68] mt-1 flex flex-wrap items-center gap-2">
                    {[location, email, phone].filter(Boolean).map((item, idx) => (
                      <React.Fragment key={idx}>
                        {idx > 0 && <span>•</span>}
                        <span>{item}</span>
                      </React.Fragment>
                    ))}
                  </div>
                )}
                {(linkedin || github || website) && (
                  <div className="text-xs font-mono text-[#003366] mt-1 flex flex-wrap items-center gap-2 font-medium">
                    {linkedin && <span>in: {linkedin.replace(/^https?:\/\/(www\.)?/, '')}</span>}
                    {github && <span>git: {github.replace(/^https?:\/\/(www\.)?/, '')}</span>}
                    {website && <span>web: {website.replace(/^https?:\/\/(www\.)?/, '')}</span>}
                  </div>
                )}
              </div>
            </div>
            <div className="px-3 py-1 rounded bg-[#181816] text-white text-[10px] font-mono uppercase font-bold self-start sm:self-auto">
              Engineering Dossier
            </div>
          </div>

          <div className="p-3 bg-[#F7F7F5] rounded-lg border border-[#E4E4DF] text-xs font-mono leading-relaxed">
            <span className="text-[#999990] font-bold block mb-0.5">// TECHNICAL PROFILE & SUMMARY</span>
            {summary}
          </div>

          <div className="space-y-2">
            <h2 className="text-xs font-mono font-bold uppercase text-[#181816] border-b border-[#E4E4DF] pb-1 flex items-center gap-1.5">
              <Code className="w-3.5 h-3.5" /> Technical Competencies & Stack
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-1">
              {skills.map((s, idx) => (
                <div key={idx} className="p-2 bg-[#F7F7F5] rounded border border-[#E4E4DF] text-center text-xs font-mono font-bold text-[#181816]">
                  {s}
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4">
            <h2 className="text-xs font-mono font-bold uppercase text-[#181816] border-b border-[#E4E4DF] pb-1 flex items-center gap-1.5">
              <Building2 className="w-3.5 h-3.5" /> Systems Engineering Experience
            </h2>
            {resume?.experience?.map((exp, idx) => (
              <div key={idx} className="space-y-1.5 p-3 rounded-lg bg-white border border-[#E4E4DF]">
                <div className="flex justify-between items-center text-xs font-mono">
                  <span className="font-bold text-[#181816]">{exp.role} @ {exp.company}</span>
                  <span className="text-[#6F6F68]">{exp.period}</span>
                </div>
                <ul className="list-disc pl-4 text-xs space-y-1 text-[#181816]">
                  {(exp.bullets || []).map((b, bIdx) => (
                    <li key={bIdx}>{b}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {certifications && certifications.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-xs font-mono font-bold uppercase text-[#181816] border-b border-[#E4E4DF] pb-1 flex items-center gap-1.5">
                <Award className="w-3.5 h-3.5" /> Certifications & Accreditations
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {certifications.map((cert, idx) => (
                  <div key={idx} className="p-2 bg-[#F7F7F5] rounded border border-[#E4E4DF] text-xs font-mono font-semibold text-[#181816] flex items-center gap-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                    <span>{formatCertification(cert)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      </div>
      </div>
    </div>
  );
}
