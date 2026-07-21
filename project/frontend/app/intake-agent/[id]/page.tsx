import { auth } from "@/auth";
import IntakeDetail from "@/components/intake/IntakeDetail";
import type { OperatorRole } from "@/lib/types";

export default async function IntakeSubmissionPage({
  params,
}: {
  params: { id: string };
}) {
  const session = await auth();
  const role: OperatorRole = session?.user?.role ?? "operator";
  return <IntakeDetail submissionId={params.id} role={role} />;
}
