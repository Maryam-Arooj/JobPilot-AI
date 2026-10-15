'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AppShell } from '@/components/AppShell';
import { getAuthToken } from '@/lib/api';
import { AICommandComposer } from '@/components/AICommandComposer';
import { CareerSnapshot } from '@/components/CareerSnapshot';
import { AIInsightPanel } from '@/components/AIInsightPanel';
import {
  FileText,
  Upload,
  CheckCircle2,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Bot
} from 'lucide-react';

export default function WorkspacePage() {
  const router = useRouter();
  // JWT lives in localStorage, so the auth check has to run client-side.
  useEffect(() => {
    if (!getAuthToken()) router.replace('/login');
  }, [router]);

  const [profileInput, setProfileInput] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractedFactsMsg, setExtractedFactsMsg] = useState<string | null>(null);

  const handleExtractProfile = async () => {
    if (!profileInput.trim()) return;
    setIsExtracting(true);
    setExtractedFactsMsg(null);
    try {
      const res = await fetch('/api/profiles/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_text: profileInput })
      });
      if (res.ok) {
        setExtractedFactsMsg('Facts extracted successfully! Please review in Fact Confirmation.');
      } else {
        setExtractedFactsMsg(`Extraction failed (HTTP ${res.status}). Nothing was extracted. Use Document Intelligence to upload your CV instead.`);
      }
    } catch (err) {
      setExtractedFactsMsg('Could not reach the extraction service. Nothing was extracted.');
    } finally {
      setIsExtracting(false);
    }
  };

  return (
    <AppShell>
      <div className="space-y-8">
        
        {/* Workspace Title Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-line pb-6">
          <div>
            <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full border border-line bg-surface text-xs font-mono text-muted mb-2">
              <ShieldCheck className="w-3.5 h-3.5 text-ok" />
              <span>Canonical Career Profile Intelligence</span>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight text-fg">
              Career Workspace
            </h1>
            <p className="text-xs md:text-sm text-muted mt-1">
              Extract verified profile facts, manage ATS resumes, discover opportunities, and prepare applications.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/confirm"
              className="px-3.5 py-2 rounded-lg border border-line bg-surface hover:bg-inset text-fg font-medium text-xs transition-colors flex items-center gap-1.5"
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-ok" />
              <span>Fact Confirmation</span>
            </Link>
          </div>
        </div>

        {/* AI Command Composer */}
        <AICommandComposer />

        {/* Career Snapshot */}
        <CareerSnapshot />

        {/* Two-Column Interactive Workspace Tools */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
          {/* Tool 1: Conversational Profile Fact Extraction */}
          <div className="card-base p-6 bg-surface border border-line rounded-xl space-y-4">
            <div className="flex items-center justify-between border-b border-line pb-3">
              <div>
                <h3 className="text-sm font-semibold text-fg flex items-center gap-2">
                  <Bot className="w-4 h-4 text-fg" /> Conversational Profile Extractor
                </h3>
                <p className="text-xs text-muted mt-0.5">Paste project history or experience notes to extract canonical facts.</p>
              </div>
            </div>

            <textarea
              rows={4}
              value={profileInput}
              onChange={(e) => setProfileInput(e.target.value)}
              placeholder="e.g. 'I am a BS Data Science student with 3 years Python and FastAPI experience. Built RAG search pipelines with Docker and pgvector...'"
              className="w-full bg-inset border border-line rounded-lg p-3 text-xs text-fg placeholder-faint focus:outline-none focus:border-accent font-sans leading-relaxed"
            />

            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-subtle font-mono">
                AI never invents facts.
              </span>
              <button
                onClick={handleExtractProfile}
                disabled={isExtracting || !profileInput.trim()}
                className={`px-4 py-2 rounded-lg font-medium text-xs transition-colors flex items-center gap-1.5 ${
                  profileInput.trim()
                    ? 'bg-accent text-white hover:bg-accent-hover'
                    : 'bg-line-strong text-subtle cursor-not-allowed'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>{isExtracting ? 'Extracting...' : 'Extract Facts'}</span>
              </button>
            </div>

            {extractedFactsMsg && (
              <div className="p-3 bg-ok-soft border border-ok/30 text-ok rounded-lg text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                <span>{extractedFactsMsg}</span>
              </div>
            )}
          </div>

          {/* Tool 2: Document Intelligence Dropzone */}
          <div className="card-base p-6 bg-surface border border-line rounded-xl space-y-4 flex flex-col justify-between">
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-line pb-3">
                <h3 className="text-sm font-semibold text-fg flex items-center gap-2">
                  <FileText className="w-4 h-4 text-fg" /> Document Upload & Parsing
                </h3>
                <span className="text-[10px] font-mono text-muted bg-surface-2 px-2 py-0.5 rounded border border-line">
                  PDF · DOCX · TXT
                </span>
              </div>

              {/* Drag and Drop Zone */}
              <Link
                href="/confirm"
                className="border-2 border-dashed border-line hover:border-accent/60 bg-inset rounded-xl p-8 text-center flex flex-col items-center justify-center space-y-2 transition-all group cursor-pointer block"
              >
                <div className="w-10 h-10 rounded-full bg-surface border border-line flex items-center justify-center text-fg group-hover:scale-105 transition-transform shadow-xs">
                  <Upload className="w-5 h-5 text-muted group-hover:text-fg" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-fg block">
                    Drop your resume or document here
                  </span>
                  <span className="text-[11px] text-muted block mt-0.5">
                    Parser extracts structured facts with source provenance
                  </span>
                </div>
              </Link>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-line text-xs">
              <span className="text-muted">Explicit confirmation required for all extracted facts.</span>
              <Link
                href="/confirm"
                className="text-fg font-semibold hover:underline flex items-center gap-1"
              >
                <span>Upload File</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>

        </div>

        {/* AI Insight Panel */}
        <AIInsightPanel />

      </div>
    </AppShell>
  );
}
