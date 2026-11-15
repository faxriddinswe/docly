import { BookingWizard } from "./wizard";

export default async function ClinicBookingPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <BookingWizard slug={slug} />;
}
