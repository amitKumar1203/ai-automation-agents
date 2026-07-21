import { auth } from "@/auth";
import IntakeInbox from "@/components/intake/IntakeInbox";
import type { OperatorRole } from "@/lib/types";

export default async function IntakeAgentPage() {
  const session = await auth();
  const role: OperatorRole = session?.user?.role ?? "operator";
  return <IntakeInbox role={role} />;
}
