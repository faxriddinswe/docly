"use client";

import type { S } from "@/lib/api";
import { fmtTime } from "@/lib/api";

const START = 8;
const END = 20;
const HOUR_PX = 56;

const color: Record<string, string> = {
  booked: "border-amber-400 bg-amber-50",
  confirmed: "border-blue-400 bg-blue-50",
  completed: "border-emerald-400 bg-emerald-50",
  no_show: "border-red-400 bg-red-50",
  cancelled: "border-slate-300 bg-slate-100 opacity-60",
};

export type Column = { key: string; label: string; dayStartIso: string; items: S["AppointmentOut"][] };

/** Time-grid: one column per doctor (day view) or per day (week view). Cards positioned by clinic-local time. */
export function TimeGrid({ columns, tz, onSelect }: { columns: Column[]; tz: string; onSelect: (a: S["AppointmentOut"]) => void }) {
  const hours = Array.from({ length: END - START }, (_, i) => START + i);
  const minutesOfDay = (iso: string) => {
    const [h, m] = fmtTime(iso, tz).split(":").map(Number);
    return h * 60 + m;
  };
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <div className="grid min-w-[640px]" style={{ gridTemplateColumns: `3rem repeat(${columns.length}, minmax(8rem, 1fr))` }}>
        <div />
        {columns.map((c) => (
          <div key={c.key} className="border-l border-slate-200 p-2 text-center text-sm font-medium">{c.label}</div>
        ))}
        <div className="relative" style={{ height: hours.length * HOUR_PX }}>
          {hours.map((h, i) => (
            <span key={h} className="absolute right-1 -translate-y-1/2 text-xs text-slate-400" style={{ top: i * HOUR_PX }}>{`${h}:00`}</span>
          ))}
        </div>
        {columns.map((c) => (
          <div key={c.key} className="relative border-l border-slate-200" style={{ height: hours.length * HOUR_PX }}>
            {hours.map((h, i) => (
              <div key={h} className="absolute inset-x-0 border-t border-slate-100" style={{ top: i * HOUR_PX }} />
            ))}
            {c.items.map((a) => {
              const top = ((minutesOfDay(a.starts_at) - START * 60) / 60) * HOUR_PX;
              const height = Math.max(((minutesOfDay(a.ends_at) - minutesOfDay(a.starts_at)) / 60) * HOUR_PX, 22);
              return (
                <button
                  key={a.id}
                  onClick={() => onSelect(a)}
                  className={`absolute inset-x-1 overflow-hidden rounded-md border-l-4 px-1.5 py-0.5 text-left text-xs shadow-sm ${color[a.status]}`}
                  style={{ top, height }}
                  title={`${a.patient_name} — ${a.service_name}`}
                >
                  <b>{fmtTime(a.starts_at, tz)}</b> {a.patient_name}
                  <span className="block truncate text-slate-500">{a.service_name}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
