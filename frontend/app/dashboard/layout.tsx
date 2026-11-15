"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { logout, tokens } from "@/lib/api";
import { useClinic, useMe } from "@/lib/hooks";
import { ErrorBox, Spinner } from "@/components/ui";

const NAV = [
  ["/dashboard", "Calendar"],
  ["/dashboard/appointments", "Appointments"],
  ["/dashboard/doctors", "Doctors"],
  ["/dashboard/services", "Services"],
  ["/dashboard/patients", "Patients"],
  ["/dashboard/stats", "Stats"],
] as const;

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (!tokens.get()) router.replace("/login");
  }, [router]);
  const me = useMe();
  const clinic = useClinic();
  useEffect(() => {
    if (me.isError) { tokens.clear(); router.replace("/login"); }
  }, [me.isError, router]);

  if (me.isLoading || !me.data) return <Spinner />;
  if (me.data && !me.data.clinic_id) { router.replace("/admin"); return <Spinner />; }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-slate-200 bg-white md:w-56 md:border-r md:border-b-0">
        <div className="flex items-center justify-between px-4 py-3 md:block">
          <div>
            <p className="font-bold text-teal-800">Docly</p>
            <p className="truncate text-xs text-slate-500">{clinic.data?.name}</p>
          </div>
          <button className="text-xs text-slate-500 underline md:mt-3" onClick={async () => { await logout(); router.push("/login"); }}>
            Sign out
          </button>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0" aria-label="Main">
          {NAV.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              aria-current={path === href ? "page" : undefined}
              className={`shrink-0 rounded-lg px-3 py-2 text-sm font-medium ${path === href ? "bg-teal-50 text-teal-800" : "text-slate-600 hover:bg-slate-100"}`}
            >
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">
        {clinic.error && <ErrorBox error={clinic.error} />}
        {children}
      </main>
    </div>
  );
}
