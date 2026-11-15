"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, Query } from "@/components/ui";
import { api, unwrap } from "@/lib/api";

export default function StatsPage() {
  const q = useQuery({ queryKey: ["stats"], queryFn: () => unwrap(api.GET("/stats")) });
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Statistics <span className="text-sm font-normal text-slate-500">(last 30 days, cancelled excluded)</span></h1>
      <Query q={q}>
        {(d) => {
          const max = Math.max(1, ...d.per_day.map((x) => x.count));
          return (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Card><p className="text-sm text-slate-500">Appointments</p><p className="text-3xl font-bold">{d.total}</p></Card>
                <Card>
                  <p className="text-sm text-slate-500">No-show rate</p>
                  <p className="text-3xl font-bold">{d.no_show_rate === null ? "—" : `${Math.round(d.no_show_rate * 100)}%`}</p>
                  {d.no_show_rate === null && <p className="text-xs text-slate-500">No finished appointments yet</p>}
                </Card>
              </div>
              <Card>
                <h2 className="mb-3 font-medium">Appointments per day</h2>
                {d.per_day.length === 0 ? <p className="text-sm text-slate-500">No data in this period.</p> : (
                  <div className="flex h-40 items-end gap-1" role="img" aria-label="Bar chart of appointments per day">
                    {d.per_day.map((x) => (
                      <div key={x.date} className="flex flex-1 flex-col items-center justify-end" title={`${x.date}: ${x.count}`}>
                        <span className="text-xs text-slate-500">{x.count}</span>
                        <div className="w-full rounded-t bg-teal-600" style={{ height: `${(x.count / max) * 100}%` }} />
                        <span className="mt-1 text-[10px] text-slate-400">{x.date.slice(8)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
              <Card>
                <h2 className="mb-3 font-medium">Busiest doctors</h2>
                {d.busiest_doctors.length === 0 ? <p className="text-sm text-slate-500">No data yet.</p> : (
                  <ul className="space-y-2">
                    {d.busiest_doctors.map((x) => (
                      <li key={x.doctor_id} className="flex items-center justify-between text-sm"><span>{x.doctor_name}</span><b>{x.appointments}</b></li>
                    ))}
                  </ul>
                )}
              </Card>
            </>
          );
        }}
      </Query>
    </div>
  );
}
