import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const state = url.searchParams.get('state');
  const error = url.searchParams.get('error');

  const appUrl = new URL('/applications', request.url);

  if (error) {
    appUrl.searchParams.set('error', 'oauth_denied');
    return NextResponse.redirect(appUrl);
  }

  if (!code || !state) {
    appUrl.searchParams.set('error', 'missing_oauth_params');
    return NextResponse.redirect(appUrl);
  }

  // Forward code and state to the existing backend callback endpoint
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  const backendUrl = `${apiUrl}/gmail/oauth/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`;
  
  try {
    const res = await fetch(backendUrl);
    
    if (!res.ok) {
      console.error('Backend OAuth error status:', res.status);
      appUrl.searchParams.set('error', 'backend_oauth_failed');
      return NextResponse.redirect(appUrl);
    }
    
    appUrl.searchParams.set('success', 'gmail_connected');
    return NextResponse.redirect(appUrl);
  } catch (err) {
    console.error('Failed to contact backend for OAuth callback', err);
    appUrl.searchParams.set('error', 'backend_network_error');
    return NextResponse.redirect(appUrl);
  }
}
