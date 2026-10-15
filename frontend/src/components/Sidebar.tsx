'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  User,
  FileText,
  Briefcase,
  Send,
  ShieldCheck,
  Bot,
  Activity,
  Settings,
  LogOut,
} from 'lucide-react';
import { apiFetch, removeAuthToken } from '@/lib/api';

interface NavItem {
  name: string;
  href: string;
  icon: React.ElementType;
  badge?: string;
}

/**
 * Navigation follows the product workflow:
 * Profile & CV (CV Agent) → Jobs (Job Agent) → Outreach (Email Agent) → Agents.
 * Each system keeps its own section so responsibilities stay separate.
 */
const NAV_SECTIONS: { label?: string; items: NavItem[] }[] = [
  { items: [{ name: 'Overview', href: '/', icon: LayoutDashboard }] },
  {
    label: 'Profile & CV',
    items: [
      { name: 'Career Profile', href: '/profile', icon: User },
      { name: 'Document Intelligence', href: '/confirm', icon: ShieldCheck },
      { name: 'Resume Studio', href: '/resume', icon: FileText },
    ],
  },
  { label: 'Jobs', items: [{ name: 'Job Discovery', href: '/jobs', icon: Briefcase }] },
  { label: 'Outreach', items: [{ name: 'Applications & Email', href: '/applications', icon: Send }] },
  {
    label: 'Agents',
    items: [
      { name: 'Agent Transparency', href: '/agent-transparency', icon: Activity, badge: 'New' },
      { name: 'Career Counsellor', href: '/agent', icon: Bot },
    ],
  },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const [userName, setUserName] = useState('Career Explorer');
  const [userEmail, setUserEmail] = useState('');
  const [userHeadline, setUserHeadline] = useState('');

  useEffect(() => {
    const fetchUserProfile = async () => {
      try {
        const prof = await apiFetch('/profiles/me');
        if (prof?.personal?.name) {
          setUserName(prof.personal.name);
        }
        if (prof?.personal?.email) {
          setUserEmail(prof.personal.email);
        }
        if (prof?.professional?.headline) {
          setUserHeadline(prof.professional.headline);
        }
      } catch (e) {
        if (typeof window !== 'undefined') {
          const storedEmail = localStorage.getItem('user_email');
          if (storedEmail) {
            setUserEmail(storedEmail);
            setUserName(storedEmail.split('@')[0]);
          }
        }
      }
    };
    fetchUserProfile();
  }, []);

  const handleLogout = () => {
    removeAuthToken();
    router.push('/login');
  };

  const isActive = (path: string) => {
    if (path === '/' && pathname === '/') return true;
    if (path !== '/' && (pathname === path || pathname.startsWith(path + '/'))) return true;
    return false;
  };

  const renderItem = (item: NavItem) => {
    const Icon = item.icon;
    const active = isActive(item.href);
    return (
      <Link
        key={item.name}
        href={item.href}
        onClick={onNavigate}
        aria-current={active ? 'page' : undefined}
        className={`relative flex items-center gap-3 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors ${
          active ? 'bg-accent-soft text-fg font-semibold' : 'text-fg-2 hover:bg-surface hover:text-fg'
        }`}
      >
        {active && <span className="absolute -left-3 top-2 bottom-2 w-[3px] rounded-r bg-accent" aria-hidden />}
        <Icon className={`h-[18px] w-[18px] shrink-0 ${active ? 'text-accent' : ''}`} strokeWidth={1.7} />
        <span className="truncate">{item.name}</span>
        {item.badge && (
          <span className="ml-auto rounded bg-accent px-1.5 py-0.5 text-[10.5px] font-semibold text-white">{item.badge}</span>
        )}
      </Link>
    );
  };

  return (
    <aside className="flex h-full w-[264px] flex-shrink-0 select-none flex-col border-r border-line bg-panel">
      {/* Brand */}
      <Link
        href="/"
        onClick={onNavigate}
        className="mx-3 mb-3 mt-4 flex items-center gap-2.5 border-b border-line px-2 pb-4 text-[21px] font-bold tracking-tight text-fg"
      >
        <span className="grid h-8 w-8 -rotate-6 place-items-center rounded-md bg-accent text-white">
          <Send className="h-[18px] w-[18px]" strokeWidth={2} />
        </span>
        <span>
          JobPilot <span className="text-accent">AI</span>
        </span>
      </Link>

      {/* Navigation */}
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 pb-4" aria-label="Main">
        {NAV_SECTIONS.map((section, i) => (
          <div key={section.label ?? i} className="space-y-0.5">
            {section.label && (
              <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">{section.label}</p>
            )}
            {section.items.map(renderItem)}
          </div>
        ))}
      </nav>

      {/* Footer: settings + signed-in user */}
      <div className="space-y-2 border-t border-line p-3">
        <Link
          href="/profile"
          onClick={onNavigate}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-fg-2 transition-colors hover:bg-surface hover:text-fg"
        >
          <Settings className="h-[18px] w-[18px]" strokeWidth={1.7} />
          <span>Settings</span>
        </Link>

        <div className="flex items-center justify-between gap-2 rounded-lg border border-line bg-surface p-2.5">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-line-strong bg-accent-soft text-sm font-bold text-accent">
              {userName.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <span className="block truncate text-sm font-semibold leading-tight text-fg">{userName}</span>
              <span className="block truncate text-[11px] text-muted">{userHeadline || userEmail || 'Signed in'}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            title="Sign out"
            aria-label="Sign out"
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-bad"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
