"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, Input, Query, Spinner, StatusBadge } from "@/components/ui";
import { api, fmtDateTime, unwrap } from "@/lib/api";
import { useClinic } from "@/lib/hooks";

export default function PatientsPage() {
  const tz = useClinic().data?.timezone ?? "Asia/Tashkent";
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["patients", search],
    queryFn: () => unwrap(api.GET("/patients", { params: { query: { limit: 50, ...(search ? { q: search } : {}) } } })),
  });
  const hist = useQuery({
    enabled: !!open,
    queryKey: ["patient-history", open],
    queryFn: () => unwrap(api.GET("/patients/{patient_id}/appointments", { params: { path: { patient_id: open! } } })),
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Patients</h1>
        <Input aria-label="Search patients" placeholder="Search name or phone" className="max-w-xs" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <Query q={q} empty={(d) => d.items.length === 0}>
        {(d) => (
          <div className="space-y-2">
            {d.items.map((p) => (
              <Card key={p.id}>
                <button className="flex w-full items-center justify-between text-left" onClick={() => setOpen(open === p.id ? null : p.id)} aria-expanded={open === p.id}>
                  <span><span className="font-medium">{p.full_name}</span><span className="block text-sm text-slate-500">{p.phone}</span></span>
                  <span className="text-xs text-slate-400">{open === p.id ? "Hide history" : "History"}</span>
                </button>
                {open === p.id && (
                  <div className="mt-3 space-y-1 border-t border-slate-100 pt-3 text-sm">
                    {hist.isLoading && <Spinner />}
                    {hist.data?.map((a) => (
                      <div key={a.id} className="flex items-center justify-between">
                        <span>{fmtDateTime(a.starts_at, tz)} — {a.service_name} ({a.doctor_name})</span>
                        <StatusBadge status={a.status} />
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
      </Query>
    </div>
  );
}
