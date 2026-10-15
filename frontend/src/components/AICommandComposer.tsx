'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, ArrowRight } from 'lucide-react';

interface AICommandComposerProps {
  placeholder?: string;
  className?: string;
}

/** Quick job search: sends the typed query to Job Discovery (/jobs?query=…). */
export function AICommandComposer({
  placeholder = "Search for jobs, e.g. 'Remote AI Engineer roles in Europe'",
  className = ''
}: AICommandComposerProps) {
  const [prompt, setPrompt] = useState('');
  const router = useRouter();

  const suggestions = [
    { label: "Find remote AI Engineer roles", action: () => router.push('/jobs?query=Remote+AI+Engineer') },
    { label: "Audit resume for ATS", action: () => router.push('/resume') },
    { label: "Prepare job application", action: () => router.push('/applications') },
    { label: "Review career profile", action: () => router.push('/profile') },
  ];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    // Route to jobs or agent with query
    router.push(`/jobs?query=${encodeURIComponent(prompt.trim())}`);
  };

  return (
    <div className={`rounded-lg border border-line bg-surface p-4 sm:p-5 space-y-3 ${className}`}>
      <div className="flex items-center gap-2 text-sm font-semibold text-fg">
        <Search className="h-4 w-4 text-accent" /> Quick job search
      </div>

      <form onSubmit={handleSubmit} className="relative">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
          rows={2}
          placeholder={placeholder}
          aria-label="Job search query"
          className="w-full resize-none rounded-lg border border-line-strong bg-inset px-3.5 py-3 pr-28 text-sm text-fg placeholder:text-faint focus:border-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={!prompt.trim()}
          className="absolute bottom-3 right-3 inline-flex h-8 items-center gap-1.5 rounded-lg bg-accent px-3.5 text-xs font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-faint"
        >
          <span>Search</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </form>

      {/* Suggestion Chips */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-subtle">Shortcuts:</span>
        {suggestions.map((item, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => {
              setPrompt(item.label);
              item.action();
            }}
            className="rounded-md border border-line-strong bg-surface-2 px-2.5 py-1 text-xs text-fg-2 transition-colors hover:border-accent/60 hover:text-fg"
          >
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
}
