import React from 'react';
import { FileSearch, Search, Mail } from 'lucide-react';
import { cx } from './cn';

export type AgentKey = 'cv' | 'job' | 'email';

export const AGENT_META: Record<AgentKey, { name: string; icon: React.ElementType; tone: string; dot: string }> = {
  cv: { name: 'CV Agent', icon: FileSearch, tone: 'bg-agent-cv/15 text-agent-cv', dot: 'bg-agent-cv' },
  job: { name: 'Job Agent', icon: Search, tone: 'bg-agent-job/15 text-agent-job', dot: 'bg-agent-job' },
  email: { name: 'Email Agent', icon: Mail, tone: 'bg-agent-email/15 text-agent-email', dot: 'bg-agent-email' },
};

const sizes = { sm: 'h-6 w-6 [&>svg]:h-3 [&>svg]:w-3', md: 'h-8 w-8 [&>svg]:h-4 [&>svg]:w-4', lg: 'h-11 w-11 [&>svg]:h-5 [&>svg]:w-5' };

export function AgentBadge({ agent, size = 'md' }: { agent: AgentKey; size?: keyof typeof sizes }) {
  const meta = AGENT_META[agent];
  const Icon = meta.icon;
  return (
    <span className={cx('inline-grid shrink-0 place-items-center rounded-full', meta.tone, sizes[size])} aria-hidden>
      <Icon strokeWidth={1.8} />
    </span>
  );
}
