"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Button, Card, ErrorBox, Query, Spinner } from "@/components/ui";
import { api, logout, tokens, unwrap } from "@/lib/api";
import { useMe } from "@/lib/hooks";

export default function AdminPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  useEffect(() => {
    if (!tokens.get() || me.isError) router.replace("/login");
    if (me.data && !me.data.is_superadmin) router.replace("/dashboard");
  }, [me.isError, me.data, router]);
  const q = useQuery({ enabled: !!me.data?.is_superadmin, queryKey: ["admin-clinics"], queryFn: () => unwrap(api.GET("/admin/clinics", { params: { query: { limit: 200 } } })) });
  const toggle = useMutation({
    mutationFn: (c: { id: string; is_active: boolean }) =>
      c.is_active
        ? unwrap(api.POST("/admin/clinics/{clinic_id}/suspend", { params: { path: { clinic_id: c.id } } }))
        : unwrap(api.POST("/admin/clinics/{clinic_id}/activate", { params: { path: { clinic_id: c.id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-clinics"] }),
  });
  if (me.isLoading) return <Spinner />;
  return (
    <main className="mx-auto w-full max-w-3xl flex-1 space-y-4 px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Platform clinics</h1>
        <button className="text-sm underline" onClick={async () => { await logout(); router.push("/login"); }}>Sign out</button>
      </div>
      {toggle.error && <ErrorBox error={toggle.error} />}
      <Query q={q} empty={(d) => d.items.length === 0}>
        {(d) => (
          <div className="space-y-2">
            {d.items.map((c) => (
              <Card key={c.id} className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{c.name} {!c.is_active && <span className="ml-2 rounded bg-red-100 px-2 py-0.5 text-xs text-red-800">suspended</span>}</p>
                  <p className="text-sm text-slate-500">/{c.slug} · {c.timezone}</p>
                </div>
                <Button variant={c.is_active ? "danger" : "primary"} disabled={toggle.isPending} onClick={() => toggle.mutate(c)}>
                  {c.is_active ? "Suspend" : "Activate"}
                </Button>
              </Card>
            ))}
          </div>
        )}
      </Query>
    </main>
  );
}
