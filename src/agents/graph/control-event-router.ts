import type { AgentControlEvent } from "./state";

type RouteControlEvent = Extract<
  AgentControlEvent,
  { type: "route_to_agent" | "request_revision" }
>;

type SideEffectControlEvent = Exclude<AgentControlEvent, RouteControlEvent>;

function isRouteEvent(event: AgentControlEvent): event is RouteControlEvent {
  return event.type === "route_to_agent" ||
    event.type === "request_revision";
}

export function splitControlEvents(events: AgentControlEvent[]): {
  sideEffectEvents: SideEffectControlEvent[];
  routeEvent: RouteControlEvent | null;
  ignoredRouteEvents: RouteControlEvent[];
} {
  const sideEffectEvents: SideEffectControlEvent[] = [];
  const ignoredRouteEvents: RouteControlEvent[] = [];
  let routeEvent: RouteControlEvent | null = null;

  for (const event of events) {
    if (!isRouteEvent(event)) {
      sideEffectEvents.push(event);
      continue;
    }

    if (!routeEvent) {
      routeEvent = event;
    } else {
      ignoredRouteEvents.push(event);
    }
  }

  return { sideEffectEvents, routeEvent, ignoredRouteEvents };
}
