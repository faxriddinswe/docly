"use client";

import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "./api";

export const useClinic = () =>
  useQuery({ queryKey: ["clinic"], queryFn: () => unwrap(api.GET("/clinic")), staleTime: 60_000 });
export const useMe = () => useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/auth/me")), retry: false });
export const useDoctors = () =>
  useQuery({ queryKey: ["doctors"], queryFn: () => unwrap(api.GET("/doctors", { params: { query: { limit: 200 } } })) });
export const useServices = () =>
  useQuery({ queryKey: ["services"], queryFn: () => unwrap(api.GET("/services", { params: { query: { limit: 200 } } })) });
