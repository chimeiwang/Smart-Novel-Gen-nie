import { notFound } from "next/navigation";

import { WorkflowEventsInspector } from "@/features/debug/workflow-events-inspector";
import { getAgentObservabilityConfig } from "@/shared/env";

export const dynamic = "force-dynamic";

export default function WorkflowEventsDebugPage() {
  if (!getAgentObservabilityConfig().workflowEventDebugEnabled) {
    notFound();
  }

  return <WorkflowEventsInspector />;
}
