'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ShieldCheck, ArrowRight, UserPlus, LogIn, AlertCircle, Send } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const endpoint = mode === 'signup' ? `${API_URL}/auth/register` : `${API_URL}/auth/login`;
      const bodyPayload = mode === 'signup'
        ? { email, password, name: name.trim() || undefined }
        : { email, password };

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyPayload),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Authentication failed. Please check your credentials.');
      }

      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
        if (data.email) localStorage.setItem('user_email', data.email);
        router.push('/');
      } else {
        // If registered successfully without auto token, log in immediately
        const loginRes = await fetch(`${API_URL}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password }),
        });
        const loginData = await loginRes.json();
        if (loginRes.ok && loginData.access_token) {
          localStorage.setItem('access_token', loginData.access_token);
          if (loginData.email) localStorage.setItem('user_email', loginData.email);
          router.push('/');
        } else {
          setMode('login');
          setError('Account created! Please sign in with your password.');
        }
      }
    } catch (err: any) {
      setError(err.message || 'An error occurred during authentication.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-canvas via-surface to-canvas flex items-center justify-center p-6 text-fg font-sans antialiased relative overflow-hidden">
      {/* Background Glow Spheres */}
      <div className="absolute -top-32 -left-32 w-96 h-96 bg-accent/20 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-32 -right-32 w-96 h-96 bg-accent/20 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md p-8 bg-surface/95 backdrop-blur-md border border-line rounded-3xl space-y-6 shadow-2xl relative z-10">
        
        {/* Brand Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2.5 text-2xl font-bold tracking-tight text-fg">
            <span className="grid h-10 w-10 -rotate-6 place-items-center rounded-lg bg-accent text-white">
              <Send className="h-5 w-5" strokeWidth={2} />
            </span>
            <span>
              JobPilot <span className="text-accent">AI</span>
            </span>
          </div>
          <p className="text-xs text-muted font-medium">Enterprise AI Career Operating System</p>
        </div>

        {/* Auth Mode Toggle Tabs */}
        <div className="flex p-1 bg-surface-2 rounded-xl border border-line text-xs font-bold">
          <button
            type="button"
            onClick={() => { setMode('login'); setError(null); }}
            className={`flex-1 py-2 rounded-lg text-center transition-all flex items-center justify-center gap-1.5 ${
              mode === 'login' ? 'bg-surface text-fg shadow-xs' : 'text-muted hover:text-fg'
            }`}
          >
            <LogIn className={`w-3.5 h-3.5 ${mode === 'login' ? 'text-accent' : ''}`} />
            <span>Sign In</span>
          </button>
          <button
            type="button"
            onClick={() => { setMode('signup'); setError(null); }}
            className={`flex-1 py-2 rounded-lg text-center transition-all flex items-center justify-center gap-1.5 ${
              mode === 'signup' ? 'bg-surface text-fg shadow-xs' : 'text-muted hover:text-fg'
            }`}
          >
            <UserPlus className={`w-3.5 h-3.5 ${mode === 'signup' ? 'text-accent' : ''}`} />
            <span>Create Account</span>
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-3 bg-bad-soft border border-bad/30 rounded-xl text-xs text-bad flex items-center gap-2 font-medium">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'signup' && (
            <div className="space-y-1">
              <label className="text-xs font-semibold text-fg">Full Name</label>
              <input
                type="text"
                required={mode === 'signup'}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Alex Chen"
                className="w-full bg-inset border border-line rounded-xl p-3 text-xs text-fg focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all"
              />
            </div>
          )}

          <div className="space-y-1">
            <label className="text-xs font-semibold text-fg">Email Address</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="alex.chen@example.com"
              className="w-full bg-inset border border-line rounded-xl p-3 text-xs text-fg focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-semibold text-fg">Password</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="w-full bg-inset border border-line rounded-xl p-3 text-xs text-fg focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-gradient-to-r from-accent to-accent hover:from-accent-hover hover:to-accent text-white font-semibold text-xs py-3 rounded-xl transition-all shadow-md hover:shadow-lg flex items-center justify-center gap-1.5 disabled:opacity-60 cursor-pointer"
          >
            <span>{loading ? 'Authenticating...' : mode === 'signup' ? 'Create Career Workspace' : 'Sign In to Workspace'}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </form>

        {/* Quick Demo Credentials Pill */}
        <div className="p-3 bg-accent-soft rounded-xl border border-accent/20 space-y-1.5 text-xs">
          <div className="flex items-center justify-between">
            <span className="font-bold text-accent text-[11px]">Demo account (works only if it exists on your server):</span>
            <button
              type="button"
              onClick={() => {
                setMode('login');
                setEmail('demo@jobpilot.com');
                setPassword('jobpilot123');
              }}
              className="text-[11px] font-bold text-accent hover:underline cursor-pointer bg-surface px-2 py-0.5 rounded border border-accent/30 shadow-2xs"
            >
              Fill Demo Login
            </button>
          </div>
          <div className="text-[11px] font-mono text-fg-2 space-y-0.5">
            <div>Email: <strong className="text-fg">demo@jobpilot.com</strong></div>
            <div>Password: <strong className="text-fg">jobpilot123</strong></div>
          </div>
        </div>

        <div className="pt-2 border-t border-line text-center text-[11px] text-muted font-mono flex items-center justify-center gap-1">
          <ShieldCheck className="w-3.5 h-3.5 text-accent" />
          <span>JWT Secure Authentication Active</span>
        </div>

      </div>
    </div>
  );
}
