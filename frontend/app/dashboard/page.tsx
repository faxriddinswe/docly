"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AppointmentPanel } from "@/components/appointment-panel";
import { TimeGrid, type Column } from "@/components/time-grid";
import { Button, ErrorBox, Select, Spinner } from "@/components/ui";
import { addDays, api, unwrap, ymd, zonedToIso, type S } from "@/lib/api";
import { useClinic, useDoctors } from "@/lib/hooks";

export default function CalendarPage() {
  const clinic = useClinic();
  const doctors = useDoctors();
  const tz = clinic.data?.timezone ?? "Asia/Tashkent";
  const [view, setView] = useState<"day" | "week">("day");
  const [day, setDay] = useState(() => ymd(new Date(), tz));
  const [doctorId, setDoctorId] = useState("");
  const [selected, setSelected] = useState<S["AppointmentOut"] | null>(null);

  const monday = addDays(day, -((new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7));
  const from = view === "day" ? day : monday;
  const days = view === "day" ? [day] : Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const activeDoctors = (doctors.data?.items ?? []).filter((d) => d.is_active);
  const weekDoctor = doctorId || activeDoctors[0]?.id || "";

  const q = useQuery({
    enabled: !!clinic.data,
    queryKey: ["appointments", "calendar", from, view, view === "week" ? weekDoctor : ""],
    queryFn: () =>
      unwrap(
        api.GET("/appointments", {
          params: {
            query: {
              date_from: zonedToIso(`${from}T00:00`, tz),
              date_to: zonedToIso(`${addDays(from, view === "day" ? 1 : 7)}T00:00`, tz),
              limit: 200,
              ...(view === "week" && weekDoctor ? { doctor_id: weekDoctor } : {}),
            },
          },
        }),
      ),
  });

  const items = (q.data?.items ?? []).filter((a) => a.status !== "cancelled");
  const columns: Column[] =
    view === "day"
      ? activeDoctors.map((d) => ({ key: d.id, label: d.full_name, dayStartIso: day, items: items.filter((a) => a.doctor_id === d.id) }))
      : days.map((d) => ({
          key: d,
          label: new Date(`${d}T12:00:00`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }),
          dayStartIso: d,
          items: items.filter((a) => ymd(new Date(a.starts_at), tz) === d),
        }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Calendar</h1>
        <Button variant="secondary" onClick={() => setDay(addDays(day, view === "day" ? -1 : -7))} aria-label="Previous">‹</Button>
        <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className="min-h-10 rounded-lg border border-slate-300 px-2 text-sm" />
        <Button variant="secondary" onClick={() => setDay(addDays(day, view === "day" ? 1 : 7))} aria-label="Next">›</Button>
        <Button variant="ghost" onClick={() => setDay(ymd(new Date(), tz))}>Today</Button>
        <div className="flex overflow-hidden rounded-lg border border-slate-300">
          {(["day", "week"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} aria-pressed={view === v} className={`px-3 py-2 text-sm ${view === v ? "bg-teal-700 text-white" : "bg-white"}`}>{v}</button>
          ))}
        </div>
        {view === "week" && (
          <Select aria-label="Doctor" className="w-48" value={weekDoctor} onChange={(e) => setDoctorId(e.target.value)}>
            {activeDoctors.map((d) => <option key={d.id} value={d.id}>{d.full_name}</option>)}
          </Select>
        )}
      </div>
      {(q.isLoading || doctors.isLoading) && <Spinner label="Loading calendar…" />}
      {q.error && <ErrorBox error={q.error} retry={() => q.refetch()} />}
      {!doctors.isLoading && activeDoctors.length === 0 && (
        <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">Add a doctor first (Doctors → New doctor) to see the calendar.</p>
      )}
      {q.data && activeDoctors.length > 0 && <TimeGrid columns={columns} tz={tz} onSelect={setSelected} />}
      {q.data && items.length === 0 && activeDoctors.length > 0 && <p className="text-sm text-slate-500">No appointments in this period.</p>}
      {selected && <AppointmentPanel a={selected} tz={tz} onClose={() => setSelected(null)} />}
    </div>
  );
}
