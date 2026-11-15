"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { API_URL, ApiError, api, fmtDateTime, money, unwrap, type S } from "@/lib/api";
import { Button, Card, Empty, ErrorBox, Field, Input, Spinner } from "@/components/ui";
import { SlotPicker } from "@/components/slot-picker";

type Step = "service" | "doctor" | "slot" | "details" | "otp" | "done";

export function BookingWizard({ slug }: { slug: string }) {
  const clinic = useQuery({
    queryKey: ["public", slug],
    queryFn: () => unwrap(api.GET("/public/{slug}", { params: { path: { slug } } })),
    retry: false,
  });
  const [step, setStep] = useState<Step>("service");
  const [service, setService] = useState<S["ServiceOut"] | null>(null);
  const [doctor, setDoctor] = useState<S["DoctorOut"] | null>(null);
  const [slot, setSlot] = useState<string | null>(null);
  const [phone, setPhone] = useState("+998");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<S["PublicBookingOut"] | null>(null);
  const [slotsVersion, setSlotsVersion] = useState(0);

  const requestOtp = useMutation({
    mutationFn: () => unwrap(api.POST("/public/{slug}/otp", { params: { path: { slug } }, body: { phone } })),
    onSuccess: () => setStep("otp"),
  });
  const book = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/public/{slug}/bookings", {
          params: { path: { slug } },
          body: { doctor_id: doctor!.id, service_id: service!.id, starts_at: slot!, phone, full_name: name, otp_code: code },
        }),
      ),
    onSuccess: (r) => {
      setResult(r);
      setStep("done");
    },
    onError: (e) => {
      if (e instanceof ApiError && (e.code === "SLOT_TAKEN" || e.code === "SLOT_UNAVAILABLE")) {
        // Friendly handling: someone else got there first. Go back to the slot picker with fresh data.
        setNotice("Sorry — that time was just taken by someone else. Please choose another time.");
        setSlot(null);
        setCode("");
        setSlotsVersion((v) => v + 1);
        setStep("slot");
      }
    },
  });

  if (clinic.isLoading) return <Shell><Spinner label="Loading clinic…" /></Shell>;
  if (clinic.error) {
    const notFound = clinic.error instanceof ApiError && clinic.error.status === 404;
    return (
      <Shell>
        {notFound ? (
          <Empty title="Clinic not found" hint="Check the address you were given." />
        ) : (
          <ErrorBox error={clinic.error} retry={() => clinic.refetch()} />
        )}
      </Shell>
    );
  }
  const c = clinic.data!;
  const tz = c.timezone;
  const doctors = service ? c.doctors.filter((d) => d.service_ids.includes(service.id)) : [];

  return (
    <Shell title={c.name}>
      <Progress step={step} />
      {notice && (
        <div role="alert" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {notice}
        </div>
      )}

      {step === "service" && (
        <section aria-label="Choose a service" className="space-y-3">
          <h2 className="text-lg font-semibold">What do you need?</h2>
          {c.services.length === 0 && <Empty title="No services available yet" />}
          {c.services.map((s) => (
            <button
              key={s.id}
              onClick={() => { setService(s); setDoctor(null); setSlot(null); setNotice(null); setStep("doctor"); }}
              className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-teal-600"
            >
              <span>
                <span className="block font-medium">{s.name}</span>
                <span className="text-sm text-slate-500">{s.duration_minutes} min</span>
              </span>
              <span className="text-sm font-medium">{money(s.price_minor, s.currency)}</span>
            </button>
          ))}
        </section>
      )}

      {step === "doctor" && service && (
        <section aria-label="Choose a doctor" className="space-y-3">
          <Back onClick={() => setStep("service")} />
          <h2 className="text-lg font-semibold">Choose a doctor</h2>
          {doctors.length === 0 && <Empty title="No doctor offers this service yet" />}
          {doctors.map((d) => (
            <button
              key={d.id}
              onClick={() => { setDoctor(d); setSlot(null); setNotice(null); setStep("slot"); }}
              className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-teal-600"
            >
              <span className="block font-medium">{d.full_name}</span>
              <span className="text-sm text-slate-500">{d.specialty}</span>
            </button>
          ))}
        </section>
      )}

      {step === "slot" && service && doctor && (
        <SlotPicker
          key={slotsVersion}
          slug={slug}
          tz={tz}
          doctorId={doctor.id}
          serviceId={service.id}
          selected={slot}
          onBack={() => setStep("doctor")}
          onPick={(s) => { setSlot(s); setNotice(null); setStep("details"); }}
        />
      )}

      {step === "details" && service && doctor && slot && (
        <section aria-label="Your details" className="space-y-4">
          <Back onClick={() => setStep("slot")} />
          <Card className="text-sm">
            <b>{service.name}</b> with {doctor.full_name}
            <br />
            {fmtDateTime(slot, tz)}
          </Card>
          <form
            className="space-y-4"
            onSubmit={(e) => { e.preventDefault(); requestOtp.mutate(); }}
          >
            <Field label="Your name">
              <Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
            </Field>
            <Field label="Phone number">
              <Input required inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="tel" />
            </Field>
            {requestOtp.error && <ErrorBox error={requestOtp.error} />}
            <Button type="submit" className="w-full" disabled={requestOtp.isPending}>
              {requestOtp.isPending ? "Sending code…" : "Send me a code"}
            </Button>
          </form>
        </section>
      )}

      {step === "otp" && (
        <section aria-label="Confirm phone" className="space-y-4">
          <Back onClick={() => setStep("details")} />
          <h2 className="text-lg font-semibold">Enter the code</h2>
          <p className="text-sm text-slate-600">We sent a 6-digit code to {phone}.</p>
          <DevOtpHint phone={phone} />
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); book.mutate(); }}>
            <Input required inputMode="numeric" autoComplete="one-time-code" maxLength={8} placeholder="123456" value={code} onChange={(e) => setCode(e.target.value)} />
            {book.error && !(book.error instanceof ApiError && book.error.code.startsWith("SLOT")) && <ErrorBox error={book.error} />}
            <Button type="submit" className="w-full" disabled={book.isPending}>
              {book.isPending ? "Booking…" : "Confirm booking"}
            </Button>
          </form>
        </section>
      )}

      {step === "done" && result && (
        <section aria-label="Booked" className="space-y-4">
          <Card className="border-emerald-300 bg-emerald-50">
            <h2 className="text-lg font-semibold text-emerald-900">You&apos;re booked ✓</h2>
            <p className="mt-1 text-sm text-emerald-900">
              {result.appointment.service_name} with {result.appointment.doctor_name}
              <br />
              {fmtDateTime(result.appointment.starts_at, tz)}
            </p>
          </Card>
          {result.telegram_link && (
            <a className="block rounded-lg bg-sky-600 px-4 py-3 text-center font-medium text-white" href={result.telegram_link}>
              Get reminders in Telegram
            </a>
          )}
          <Link className="block text-center text-sm text-teal-700 underline" href={`/manage/${result.manage_token}`}>
            Change or cancel this appointment
          </Link>
        </section>
      )}
    </Shell>
  );
}

/** Shown only when the backend runs with the fake OTP sender (dev/demo); the endpoint does not exist in prod. */
function DevOtpHint({ phone }: { phone: string }) {
  const q = useQuery({
    queryKey: ["dev-otp", phone],
    queryFn: async () => {
      const r = await fetch(`${API_URL}/public/dev/otp/${encodeURIComponent(phone)}`);
      return r.ok ? ((await r.json()) as { code: string | null }) : null;
    },
    retry: false,
  });
  if (!q.data?.code) return null;
  return <p className="rounded bg-slate-100 p-2 text-xs text-slate-600">Demo mode — your code is <b>{q.data.code}</b></p>;
}

function Progress({ step }: { step: Step }) {
  const order: Step[] = ["service", "doctor", "slot", "details", "otp", "done"];
  const i = order.indexOf(step);
  return (
    <div className="mb-5 flex gap-1" aria-hidden>
      {order.map((s, idx) => (
        <span key={s} className={`h-1.5 flex-1 rounded-full ${idx <= i ? "bg-teal-700" : "bg-slate-200"}`} />
      ))}
    </div>
  );
}

function Back({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-sm text-slate-500 hover:underline">
      ← Back
    </button>
  );
}

function Shell({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto w-full max-w-lg flex-1 px-4 py-6">
      {title && <h1 className="mb-4 text-2xl font-bold">{title}</h1>}
      {children}
    </main>
  );
}
