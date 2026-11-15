"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, login } from "@/lib/api";
import { Button, Card, ErrorBox, Field, Input } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [slug, setSlug] = useState("");
  const [needSlug, setNeedSlug] = useState<string[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await login(email, password, slug || undefined);
      router.push(out.clinic_id ? "/dashboard" : "/admin");
    } catch (err) {
      if (err instanceof ApiError && err.code === "CLINIC_REQUIRED") setNeedSlug(err.details as string[]);
      else setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-sm flex-1 px-4 py-16">
      <Card>
        <h1 className="mb-4 text-xl font-semibold">Sign in</h1>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email">
            <Input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password">
            <Input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          {needSlug && (
            <Field label="Which clinic?">
              <select className="min-h-10 w-full rounded-lg border border-slate-300 px-3" required value={slug} onChange={(e) => setSlug(e.target.value)}>
                <option value="">Select…</option>
                {needSlug.map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </Field>
          )}
          {error != null && <ErrorBox error={error} />}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
