"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, ErrorBox, Field, Input, Query } from "@/components/ui";
import { api, money, unwrap } from "@/lib/api";
import { useServices } from "@/lib/hooks";

export default function ServicesPage() {
  const qc = useQueryClient();
  const q = useServices();
  const [f, setF] = useState({ name: "", duration_minutes: "30", price: "" });
  const create = useMutation({
    mutationFn: () =>
      unwrap(api.POST("/services", { body: { name: f.name, duration_minutes: Number(f.duration_minutes), price_minor: Math.round(Number(f.price || 0) * 100), currency: "UZS" } })),
    onSuccess: () => { setF({ name: "", duration_minutes: "30", price: "" }); qc.invalidateQueries({ queryKey: ["services"] }); },
  });
  const toggle = useMutation({
    mutationFn: (s: { id: string; is_active: boolean }) =>
      unwrap(api.PATCH("/services/{service_id}", { params: { path: { service_id: s.id } }, body: { is_active: !s.is_active } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["services"] }),
  });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Services</h1>
      <Card>
        <form className="grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Name"><Input required minLength={2} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Duration (min)"><Input type="number" required min={5} max={480} step={5} value={f.duration_minutes} onChange={(e) => setF({ ...f, duration_minutes: e.target.value })} /></Field>
          <Field label="Price (UZS)"><Input type="number" min={0} value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} /></Field>
          <div className="flex items-end"><Button type="submit" disabled={create.isPending} className="w-full">Add service</Button></div>
        </form>
        {create.error && <div className="mt-3"><ErrorBox error={create.error} /></div>}
      </Card>
      <Query q={q} empty={(d) => d.items.length === 0}>
        {(d) => (
          <div className="space-y-2">
            {d.items.map((s) => (
              <Card key={s.id} className="flex items-center justify-between">
                <div className={s.is_active ? "" : "opacity-50"}>
                  <p className="font-medium">{s.name}</p>
                  <p className="text-sm text-slate-500">{s.duration_minutes} min · {money(s.price_minor, s.currency)}</p>
                </div>
                <Button variant="secondary" onClick={() => toggle.mutate(s)}>{s.is_active ? "Deactivate" : "Activate"}</Button>
              </Card>
            ))}
          </div>
        )}
      </Query>
    </div>
  );
}
