"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AppointmentPanel } from "@/components/appointment-panel";
import { Button, Card, Query, Select, StatusBadge } from "@/components/ui";
import { api, fmtDateTime, unwrap, type S } from "@/lib/api";
import { useClinic } from "@/lib/hooks";

const PAGE = 20;
const STATUSES = ["booked", "confirmed", "completed", "cancelled", "no_show"] as const;

export default function AppointmentsPage() {
  const tz = useClinic().data?.timezone ?? "Asia/Tashkent";
  const [status, setStatus] = useState<S["StatusIn"]["status"] | "">("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<S["AppointmentOut"] | null>(null);
  const q = useQuery({
    queryKey: ["appointments", "list", status, offset],
    queryFn: () => unwrap(api.GET("/appointments", { params: { query: { limit: PAGE, offset, ...(status ? { status } : {}) } } })),
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Appointments</h1>
        <Select aria-label="Status filter" className="w-44" value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setOffset(0); }}>
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </Select>
      </div>
      <Query q={q} empty={(d) => d.items.length === 0}>
        {(d) => (
          <>
            <Card className="overflow-x-auto p-0">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr><th className="p-3">When</th><th className="p-3">Patient</th><th className="p-3">Doctor</th><th className="p-3">Service</th><th className="p-3">Status</th></tr>
                </thead>
                <tbody>
                  {d.items.map((a) => (
                    <tr key={a.id} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => setSelected(a)}>
                      <td className="p-3 whitespace-nowrap">{fmtDateTime(a.starts_at, tz)}</td>
                      <td className="p-3">{a.patient_name}<span className="block text-xs text-slate-500">{a.patient_phone}</span></td>
                      <td className="p-3">{a.doctor_name}</td>
                      <td className="p-3">{a.service_name}</td>
                      <td className="p-3"><StatusBadge status={a.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <div className="flex items-center justify-between text-sm text-slate-600">
              <span>{offset + 1}–{Math.min(offset + PAGE, d.total)} of {d.total}</span>
              <span className="flex gap-2">
                <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
                <Button variant="secondary" disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
              </span>
            </div>
          </>
        )}
      </Query>
      {selected && <AppointmentPanel a={selected} tz={tz} onClose={() => setSelected(null)} />}
    </div>
  );
}
