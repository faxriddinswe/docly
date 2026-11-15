import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-4xl font-bold tracking-tight">Docly</h1>
      <p className="text-lg text-slate-600">
        Online appointments for private clinics. Patients book in a minute, doctors see their day, reminders go out
        via Telegram.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link className="rounded-lg bg-teal-700 px-5 py-2.5 font-medium text-white hover:bg-teal-800" href="/signup">
          Register your clinic
        </Link>
        <Link className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 font-medium hover:bg-slate-50" href="/login">
          Staff sign in
        </Link>
      </div>
      <p className="text-sm text-slate-500">
        Patients: open your clinic&apos;s booking page, e.g. <Link className="underline" href="/smile-dental">/smile-dental</Link>.
      </p>
    </main>
  );
}
