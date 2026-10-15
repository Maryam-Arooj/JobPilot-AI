import { apiFetch } from "./api";

export async function getMyProfile() {
  return apiFetch("/profiles/me");
}

export async function updateProfile(data: any) {
  return apiFetch("/profiles/me", { method: "PUT", body: JSON.stringify(data) });
}

export async function extractProfile(text: string) {
  return apiFetch("/profiles/me/extract", { method: "POST", body: JSON.stringify({ text }) });
}
