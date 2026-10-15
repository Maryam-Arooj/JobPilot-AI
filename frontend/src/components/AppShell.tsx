'use client';

import React, { useState, useEffect } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { CommandPalette } from './CommandPalette';

interface AppShellProps {
  children: React.ReactNode;
  /**
   * Full-bleed pages (e.g. Agent Transparency) manage their own internal
   * scrolling and padding instead of the default centred content column.
   */
  fullBleed?: boolean;
}

export function AppShell({ children, fullBleed = false }: AppShellProps) {
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isNavOpen, setIsNavOpen] = useState(false);

  // Global Ctrl+K / Cmd+K keyboard shortcut listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsCommandPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="flex h-screen bg-canvas text-fg font-sans antialiased overflow-hidden print:h-auto print:overflow-visible print:bg-white print:block">
      {/* Sidebar: permanent on large screens, drawer on small screens */}
      <div className="hidden lg:block h-full print:hidden">
        <Sidebar />
      </div>
      {isNavOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden print:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="h-full shadow-2xl">
            <Sidebar onNavigate={() => setIsNavOpen(false)} />
          </div>
          <button
            type="button"
            className="flex-1 bg-black/60"
            aria-label="Close navigation"
            onClick={() => setIsNavOpen(false)}
          />
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden print:h-auto print:overflow-visible print:block">
        <div className="print:hidden">
          <TopBar
            onOpenCommandPalette={() => setIsCommandPaletteOpen(true)}
            onOpenNav={() => setIsNavOpen(true)}
          />
        </div>

        {fullBleed ? (
          <main className="flex-1 min-h-0 overflow-hidden">{children}</main>
        ) : (
          <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 print:p-0 print:overflow-visible print:block">
            <div className="max-w-7xl mx-auto print:max-w-none print:m-0 print:p-0">{children}</div>
          </main>
        )}
      </div>

      <CommandPalette isOpen={isCommandPaletteOpen} onClose={() => setIsCommandPaletteOpen(false)} />
    </div>
  );
}
