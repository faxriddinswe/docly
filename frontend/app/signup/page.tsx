"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, tokens, unwrap } from "@/lib/api";
import { Button, Card, ErrorBox, Field, Input } from "@/components/ui";

export default function SignupPage() {
  const router = useRouter();
  const [f, setF] = useState({ clinic_name: "", slug: "", full_name: "", email: "", password: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const out = await unwrap(api.POST("/auth/signup", { body: f }));
      tokens.set({ access: out.access_token, refresh: out.refresh_token });
      router.push("/dashboard/doctors");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-md flex-1 px-4 py-12">
      <Card>
        <h1 className="mb-1 text-xl font-semibold">Register your clinic</h1>
        <p className="mb-4 text-sm text-slate-500">Free to try. You become the clinic owner.</p>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Clinic name">
            <Input required minLength={2} value={f.clinic_name} onChange={set("clinic_name")} />
          </Field>
          <Field label="Booking address (docly.example/your-address)">
            <Input required pattern="[a-z0-9][a-z0-9\-]{2,60}" title="lowercase letters, digits and dashes, 3+ chars" value={f.slug} onChange={set("slug")} />
          </Field>
          <Field label="Your name">
            <Input required minLength={2} value={f.full_name} onChange={set("full_name")} />
          </Field>
          <Field label="Email">
            <Input type="email" required value={f.email} onChange={set("email")} />
          </Field>
          <Field label="Password (10+ characters)">
            <Input type="password" required minLength={10} value={f.password} onChange={set("password")} />
          </Field>
          {error != null && <ErrorBox error={error} />}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Creating…" : "Create clinic"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
