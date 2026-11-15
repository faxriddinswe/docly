import { ManageAppointment } from "./manage";

export default async function ManagePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <ManageAppointment token={token} />;
}
