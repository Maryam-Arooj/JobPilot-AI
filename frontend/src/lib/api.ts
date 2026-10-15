const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function getAuthToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("access_token");
  }
  return null;
}

export function setAuthToken(token: string, email?: string): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("access_token", token);
    if (email) localStorage.setItem("user_email", email);
  }
}

export function removeAuthToken(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    localStorage.removeItem("user_email");
  }
}

export async function apiFetch(path: string, options?: RequestInit) {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> || {}),
  };
  
  if (options?.body instanceof FormData) {
    // Browser sets multipart boundary automatically
  } else if (!headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
    });
  } catch (err: any) {
    console.error(`Network error when fetching ${API_URL}${path}:`, err);
    throw new Error(
      `Network Error: Unable to reach backend server at ${API_URL}. Please ensure the Python FastAPI server is running.`
    );
  }

  if (res.status === 401) {
    // If token expired or invalid, clear and redirect to login
    removeAuthToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API ${res.status}: ${errorText}`);
  }

  return res.json();
}
