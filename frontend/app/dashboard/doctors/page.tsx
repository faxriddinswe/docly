"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, Empty, ErrorBox, Field, Input, Query, Spinner } from "@/components/ui";
import { api, fmtDateTime, unwrap, zonedToIso, type S } from "@/lib/api";
import { useClinic, useDoctors, useServices } from "@/lib/hooks";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export default function DoctorsPage() {
  const qc = useQueryClient();
  const q = useDoctors();
  const [name, setName] = useState("");
  const [specialty, setSpecialty] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/doctors", { body: { full_name: name, specialty, user_id: null } })),
    onSuccess: (d) => { setName(""); setSpecialty(""); setSelected(d.id); qc.invalidateQueries({ queryKey: ["doctors"] }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/doctors/{doctor_id}", { params: { path: { doctor_id: id } } })),
    onSuccess: () => { setSelected(null); qc.invalidateQueries({ queryKey: ["doctors"] }); },
  });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Doctors</h1>
      <Card>
        <form className="grid gap-3 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Full name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label="Specialty"><Input value={specialty} onChange={(e) => setSpecialty(e.target.value)} /></Field>
          <div className="flex items-end"><Button type="submit" className="w-full" disabled={create.isPending}>New doctor</Button></div>
        </form>
        {create.error && <div className="mt-3"><ErrorBox error={create.error} /></div>}
      </Card>
      <Query q={q} empty={(d) => d.items.length === 0}>
        {(d) => (
          <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
            <div className="space-y-2">
              {d.items.map((doc) => (
                <button key={doc.id} onClick={() => setSelected(doc.id)} aria-pressed={selected === doc.id}
                  className={`w-full rounded-xl border p-3 text-left ${selected === doc.id ? "border-teal-700 bg-teal-50" : "border-slate-200 bg-white"} ${doc.is_active ? "" : "opacity-50"}`}>
                  <span className="block font-medium">{doc.full_name}</span>
                  <span className="text-sm text-slate-500">{doc.specialty || "—"}{doc.is_active ? "" : " · inactive"}</span>
                </button>
              ))}
            </div>
            {selected ? (
              <DoctorEditor key={selected} doctor={d.items.find((x) => x.id === selected)!} onDeactivate={() => remove.mutate(selected)} />
            ) : (
              <Empty title="Select a doctor" hint="Set their services, working hours and time off." />
            )}
          </div>
        )}
      </Query>
    </div>
  );
}

function DoctorEditor({ doctor, onDeactivate }: { doctor: S["DoctorOut"]; onDeactivate: () => void }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">{doctor.full_name}</h2>
        {doctor.is_active && <Button variant="danger" onClick={onDeactivate}>Deactivate</Button>}
      </div>
      <ServicesEditor doctor={doctor} />
      <HoursEditor doctorId={doctor.id} />
      <TimeOffEditor doctorId={doctor.id} />
    </div>
  );
}

function ServicesEditor({ doctor }: { doctor: S["DoctorOut"] }) {
  const qc = useQueryClient();
  const services = useServices();
  const [ids, setIds] = useState<string[]>(doctor.service_ids);
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/doctors/{doctor_id}/services", { params: { path: { doctor_id: doctor.id } }, body: { service_ids: ids } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["doctors"] }),
  });
  return (
    <Card>
      <h3 className="mb-2 font-medium">Services this doctor provides</h3>
      <Query q={services} empty={(d) => d.items.length === 0}>
        {(d) => (
          <div className="space-y-1">
            {d.items.filter((s) => s.is_active).map((s) => (
              <label key={s.id} className="flex min-h-10 items-center gap-2 text-sm">
                <input type="checkbox" checked={ids.includes(s.id)} onChange={(e) => setIds(e.target.checked ? [...ids, s.id] : ids.filter((x) => x !== s.id))} />
                {s.name} ({s.duration_minutes} min)
              </label>
            ))}
          </div>
        )}
      </Query>
      {save.error && <ErrorBox error={save.error} />}
      <Button className="mt-3" onClick={() => save.mutate()} disabled={save.isPending}>{save.isSuccess ? "Saved ✓" : "Save services"}</Button>
    </Card>
  );
}

type Interval = { weekday: number; start_time: string; end_time: string };

function HoursEditor({ doctorId }: { doctorId: string }) {
  const q = useQuery({ queryKey: ["hours", doctorId], queryFn: () => unwrap(api.GET("/doctors/{doctor_id}/working-hours", { params: { path: { doctor_id: doctorId } } })) });
  return (
    <Card>
      <h3 className="mb-2 font-medium">Working hours</h3>
      {q.isLoading && <Spinner />}
      {q.error && <ErrorBox error={q.error} />}
      {q.data && <HoursForm doctorId={doctorId} initial={q.data.map((r) => ({ ...r, start_time: r.start_time.slice(0, 5), end_time: r.end_time.slice(0, 5) }))} />}
    </Card>
  );
}

function HoursForm({ doctorId, initial }: { doctorId: string; initial: Interval[] }) {
  const [rows, setRows] = useState<Interval[]>(initial);
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/doctors/{doctor_id}/working-hours", { params: { path: { doctor_id: doctorId } }, body: { intervals: rows } })),
  });
  const upd = (i: number, patch: Partial<Interval>) => setRows(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  return (
    <>
      <div className="space-y-2">
        {DAYS.map((day, wd) => (
          <div key={day} className="flex flex-wrap items-center gap-2 text-sm">
            <span className="w-24 font-medium">{day}</span>
            {rows.map((r, i) => r.weekday !== wd ? null : (
              <span key={i} className="flex items-center gap-1">
                <input aria-label={`${day} from`} type="time" value={r.start_time} onChange={(e) => upd(i, { start_time: e.target.value })} className="min-h-9 rounded border border-slate-300 px-1" />–
                <input aria-label={`${day} to`} type="time" value={r.end_time} onChange={(e) => upd(i, { end_time: e.target.value })} className="min-h-9 rounded border border-slate-300 px-1" />
                <button aria-label="Remove interval" className="px-1 text-slate-400 hover:text-red-600" onClick={() => setRows(rows.filter((_, idx) => idx !== i))}>✕</button>
              </span>
            ))}
            {!rows.some((r) => r.weekday === wd) && <span className="text-slate-400">day off</span>}
            <button className="text-teal-700 underline" onClick={() => setRows([...rows, { weekday: wd, start_time: "09:00", end_time: "13:00" }])}>+ interval</button>
          </div>
        ))}
        <p className="text-xs text-slate-500">Add two intervals for a lunch break, e.g. 09:00–13:00 and 14:00–18:00.</p>
      </div>
      {save.error && <div className="mt-2"><ErrorBox error={save.error} /></div>}
      <Button className="mt-3" onClick={() => save.mutate()} disabled={save.isPending}>{save.isSuccess ? "Saved ✓" : "Save hours"}</Button>
    </>
  );
}

function TimeOffEditor({ doctorId }: { doctorId: string }) {
  const qc = useQueryClient();
  const tz = useClinic().data?.timezone ?? "Asia/Tashkent";
  const key = ["time-off", doctorId];
  const q = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/doctors/{doctor_id}/time-off", { params: { path: { doctor_id: doctorId } } })) });
  const [f, setF] = useState({ from: "", to: "", reason: "" });
  const add = useMutation({
    mutationFn: () => unwrap(api.POST("/doctors/{doctor_id}/time-off", { params: { path: { doctor_id: doctorId } }, body: { starts_at: zonedToIso(f.from, tz), ends_at: zonedToIso(f.to, tz), reason: f.reason } })),
    onSuccess: () => { setF({ from: "", to: "", reason: "" }); qc.invalidateQueries({ queryKey: key }); },
  });
  const del = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/time-off/{time_off_id}", { params: { path: { time_off_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  return (
    <Card>
      <h3 className="mb-2 font-medium">Time off</h3>
      <form className="grid gap-2 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="From"><Input type="datetime-local" required value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} /></Field>
        <Field label="To"><Input type="datetime-local" required value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} /></Field>
        <Field label="Reason"><Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
        <div className="flex items-end"><Button type="submit" className="w-full" disabled={add.isPending}>Add</Button></div>
      </form>
      {add.error && <div className="mt-2"><ErrorBox error={add.error} /></div>}
      {q.isLoading && <Spinner />}
      {q.data?.length === 0 && <p className="mt-3 text-sm text-slate-500">No time off scheduled.</p>}
      <ul className="mt-3 space-y-1 text-sm">
        {q.data?.map((t) => (
          <li key={t.id} className="flex items-center justify-between rounded bg-slate-50 px-2 py-1">
            <span>{fmtDateTime(t.starts_at, tz)} → {fmtDateTime(t.ends_at, tz)} {t.reason && `· ${t.reason}`}</span>
            <button aria-label="Delete time off" className="text-slate-400 hover:text-red-600" onClick={() => del.mutate(t.id)}>✕</button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
