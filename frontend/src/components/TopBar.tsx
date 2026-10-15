'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { Search, Bell, ChevronRight, Menu } from 'lucide-react';

interface TopBarProps {
  onOpenCommandPalette: () => void;
  onOpenNav?: () => void;
}

export function TopBar({ onOpenCommandPalette, onOpenNav }: TopBarProps) {
  const pathname = usePathname();

  const getBreadcrumbs = () => {
    if (pathname === '/') return ['JobPilot', 'Overview'];
    if (pathname === '/workspace') return ['JobPilot', 'Workspace'];
    if (pathname === '/profile') return ['Profile & CV', 'Career Profile'];
    if (pathname === '/confirm') return ['Profile & CV', 'Document Intelligence'];
    if (pathname === '/resume') return ['Profile & CV', 'Resume Studio'];
    if (pathname === '/resume-editor') return ['Resume Studio', 'Editor'];
    if (pathname.startsWith('/jobs')) return ['Jobs', 'Job Discovery'];
    if (pathname.startsWith('/applications')) return ['Outreach', 'Applications & Email'];
    if (pathname === '/agent-transparency') return ['Agents', 'Agent Transparency'];
    if (pathname === '/agent') return ['Agents', 'Career Counsellor'];
    return ['JobPilot', 'Overview'];
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <header className="sticky top-0 z-30 flex h-14 flex-shrink-0 items-center justify-between gap-3 border-b border-line bg-canvas/95 px-4 backdrop-blur sm:px-6">
      <div className="flex min-w-0 items-center gap-2 text-sm">
        {onOpenNav && (
          <button
            type="button"
            onClick={onOpenNav}
            className="-ml-1 mr-1 rounded-md p-2 text-fg-2 hover:bg-surface-2 hover:text-fg lg:hidden"
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
        <span className="hidden text-muted sm:inline">{breadcrumbs[0]}</span>
        <ChevronRight className="hidden h-3.5 w-3.5 text-faint sm:inline" />
        <span className="truncate font-semibold text-fg">{breadcrumbs[1]}</span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="flex h-9 items-center gap-2 whitespace-nowrap rounded-lg border border-line-strong bg-surface px-3 text-sm text-muted transition-colors hover:border-accent/60 hover:text-fg sm:w-80 sm:justify-between"
          aria-label="Search (Ctrl+K)"
        >
          <span className="flex items-center gap-2">
            <Search className="h-4 w-4" />
            <span className="hidden sm:inline">Search pages and actions…</span>
          </span>
          <kbd className="hidden rounded border border-line-strong bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-muted sm:inline">
            Ctrl K
          </kbd>
        </button>

        {/* Notifications: no notification source exists yet, so no unread indicator is shown */}
        <button
          type="button"
          className="rounded-lg p-2 text-fg-2 transition-colors hover:bg-surface-2 hover:text-fg"
          aria-label="Notifications (none)"
          title="No notifications"
        >
          <Bell className="h-[18px] w-[18px]" strokeWidth={1.7} />
        </button>
      </div>
    </header>
  );
}
