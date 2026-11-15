"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, fmtTime, unwrap, ymd } from "@/lib/api";
import { Empty, ErrorBox, Spinner } from "@/components/ui";

export function SlotPicker({
  slug, tz, doctorId, serviceId, selected, onBack, onPick,
}: {
  slug: string; tz: string; doctorId: string; serviceId: string; selected: string | null;
  onBack?: () => void; onPick: (iso: string) => void;
}) {
  const [day, setDay] = useState(() => ymd(new Date(), tz));
  const [days] = useState(() => Array.from({ length: 14 }, (_, i) => ymd(new Date(Date.now() + i * 86_400_000), tz)));
  const q = useQuery({
    queryKey: ["slots", slug, doctorId, serviceId, day],
    queryFn: () =>
      unwrap(api.GET("/public/{slug}/availability", { params: { path: { slug }, query: { doctor_id: doctorId, service_id: serviceId, date: day } } })),
  });
  return (
    <section aria-label="Choose a time" className="space-y-4">
      {onBack && (
        <button onClick={onBack} className="text-sm text-slate-500 hover:underline">
          ← Back
        </button>
      )}
      <h2 className="text-lg font-semibold">Pick a day and time</h2>
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {days.map((d) => {
          const dt = new Date(`${d}T12:00:00`);
          return (
            <button
              key={d}
              onClick={() => setDay(d)}
              aria-pressed={d === day}
              className={`min-w-16 shrink-0 rounded-xl border px-3 py-2 text-center text-sm ${d === day ? "border-teal-700 bg-teal-700 text-white" : "border-slate-200 bg-white"}`}
            >
              <span className="block text-xs opacity-80">{dt.toLocaleDateString("en-GB", { weekday: "short" })}</span>
              <span className="font-semibold">{dt.getDate()}</span>
            </button>
          );
        })}
      </div>
      {q.isLoading && <Spinner label="Checking availability…" />}
      {q.error && <ErrorBox error={q.error} retry={() => q.refetch()} />}
      {q.data && q.data.slots.length === 0 && <Empty title="No free times on this day" hint="Try another day." />}
      {q.data && q.data.slots.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {q.data.slots.map((s) => (
            <button
              key={s}
              onClick={() => onPick(s)}
              className={`min-h-11 rounded-lg border text-sm font-medium ${s === selected ? "border-teal-700 bg-teal-700 text-white" : "border-slate-300 bg-white hover:border-teal-600"}`}
            >
              {fmtTime(s, tz)}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

