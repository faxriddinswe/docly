"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { SlotPicker } from "@/components/slot-picker";
import { Button, Card, ErrorBox, Spinner, StatusBadge } from "@/components/ui";
import { api, fmtDateTime, unwrap } from "@/lib/api";

export function ManageAppointment({ token }: { token: string }) {
  const qc = useQueryClient();
  const path = { params: { path: { token } } };
  const q = useQuery({
    queryKey: ["manage", token],
    queryFn: () => unwrap(api.GET("/public/manage/{token}", path)),
    retry: false,
  });
  const [moving, setMoving] = useState(false);
  const cancel = useMutation({
    mutationFn: () => unwrap(api.POST("/public/manage/{token}/cancel", path)),
    onSuccess: (d) => qc.setQueryData(["manage", token], d),
  });
  const move = useMutation({
    mutationFn: (iso: string) => unwrap(api.POST("/public/manage/{token}/reschedule", { ...path, body: { starts_at: iso } })),
    onSuccess: (d) => {
      qc.setQueryData(["manage", token], d);
      setMoving(false);
    },
  });

  const body = () => {
    if (q.isLoading) return <Spinner />;
    if (q.error) return <ErrorBox error={q.error} />;
    const a = q.data!;
    const active = a.status === "booked" || a.status === "confirmed";
    return (
      <>
        <Card className="space-y-1">
          <StatusBadge status={a.status} />
          <p className="font-medium">{a.service_name} — {a.doctor_name}</p>
          <p className="text-sm text-slate-500">{a.clinic_name}</p>
          <p className="text-slate-600">{fmtDateTime(a.starts_at, a.timezone)}</p>
        </Card>
        {(cancel.error || move.error) && <ErrorBox error={cancel.error ?? move.error} />}
        {moving ? (
          <div className="space-y-2">
            <SlotPicker slug={a.clinic_slug} tz={a.timezone} doctorId={a.doctor_id} serviceId={a.service_id} selected={null} onPick={(iso) => move.mutate(iso)} />
            <Button variant="ghost" onClick={() => setMoving(false)}>Keep current time</Button>
          </div>
        ) : active ? (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setMoving(true)}>Change time</Button>
            <Button variant="danger" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
              {cancel.isPending ? "Cancelling…" : "Cancel appointment"}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-slate-500">This appointment can no longer be changed.</p>
        )}
      </>
    );
  };

  return (
    <main className="mx-auto w-full max-w-lg flex-1 space-y-4 px-4 py-8">
      <h1 className="text-2xl font-bold">Your appointment</h1>
      {body()}
    </main>
  );
}
