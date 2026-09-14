import { apiRequest, clearTokens, setTokens } from "./client";
import type { Me, Role } from "../types/api";

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  role: Role;
  organization_id: string;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const data = await apiRequest<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
  });
  setTokens(data.access_token, data.refresh_token);
  return data;
}

export function logout(): void {
  clearTokens();
}

export function fetchMe(): Promise<Me> {
  return apiRequest<Me>("/api/v1/auth/me");
}
