"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Organization, User } from "@/lib/types";

export function useCurrentUser() {
  return useQuery<User>({
    queryKey: ["auth", "me"],
    queryFn: () => apiFetch<User>("/api/v1/auth/me"),
    retry: false,
  });
}

export function useCurrentOrganization() {
  return useQuery<Organization>({
    queryKey: ["organizations", "current"],
    queryFn: () => apiFetch<Organization>("/api/v1/organizations/current"),
    retry: false,
  });
}
