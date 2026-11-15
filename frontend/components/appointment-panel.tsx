"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDateTime, unwrap, type S } from "@/lib/api";
import { Button, Card, ErrorBox, StatusBadge } from "@/components/ui";

const NEXT: Record<string, [string, S["StatusIn"]["status"], "primary" | "secondary" | "danger"][]> = {
  booked: [["Confirm", "confirmed", "primary"], ["Completed", "completed", "secondary"], ["No-show", "no_show", "secondary"], ["Cancel", "cancelled", "danger"]],
  confirmed: [["Completed", "completed", "primary"], ["No-show", "no_show", "secondary"], ["Cancel", "cancelled", "danger"]],
};

export function AppointmentPanel({ a, tz, onClose }: { a: S["AppointmentOut"]; tz: string; onClose: () => void }) {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: (status: S["StatusIn"]["status"]) =>
      unwrap(api.PATCH("/appointments/{appointment_id}/status", { params: { path: { appointment_id: a.id } }, body: { status } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["appointments"] }); onClose(); },
  });
  return (
    <Card className="space-y-3" role="dialog" aria-label="Appointment details">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold">{a.patient_name}</p>
          <p className="text-sm text-slate-500">{a.patient_phone}</p>
        </div>
        <StatusBadge status={a.status} />
      </div>
      <p className="text-sm">{a.service_name} with {a.doctor_name}<br />{fmtDateTime(a.starts_at, tz)}</p>
      {m.error && <ErrorBox error={m.error} />}
      <div className="flex flex-wrap gap-2">
        {(NEXT[a.status] ?? []).map(([label, status, variant]) => (
          <Button key={status} variant={variant} disabled={m.isPending} onClick={() => m.mutate(status)}>{label}</Button>
        ))}
        <Button variant="ghost" onClick={onClose}>Close</Button>
      </div>
    </Card>
  );
}
