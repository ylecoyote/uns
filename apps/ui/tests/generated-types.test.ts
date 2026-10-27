/**
 * Sanity test for the generated OpenAPI types. Doesn't validate every type
 * exhaustively — just confirms the file is present, parseable as TypeScript,
 * and contains expected endpoints and schemas from the AGSignal Console API.
 */

import { describe, it, expectTypeOf } from "vitest";
import type {
  ActivePolicyListResponse,
  ActivePolicySummary,
  ConsoleSessionResponse,
  RuntimeDeliveryState,
  components,
  paths,
} from "../src/types/generated";

describe("generated types", () => {
  it("includes the /ui/audit endpoint", () => {
    expectTypeOf<paths["/ui/audit"]>().toBeObject();
  });

  it("includes the /api/v1/notifications/{notification_id}/ack endpoint", () => {
    expectTypeOf<paths["/api/v1/notifications/{notification_id}/ack"]>().toBeObject();
  });

  it("includes the /ui/session endpoint and ConsoleSessionResponse schema", () => {
    expectTypeOf<paths["/ui/session"]>().toBeObject();
    expectTypeOf<ConsoleSessionResponse>().toEqualTypeOf<
      components["schemas"]["ConsoleSessionResponse"]
    >();
    expectTypeOf<ConsoleSessionResponse["subject"]>().toBeString();
    expectTypeOf<ConsoleSessionResponse["scopes"]>().toEqualTypeOf<
      string[] | undefined
    >();
  });

  it("includes the /ui/policies/active endpoint and ActivePolicyListResponse / ActivePolicySummary schemas", () => {
    expectTypeOf<paths["/ui/policies/active"]>().toBeObject();
    expectTypeOf<ActivePolicyListResponse>().toEqualTypeOf<
      components["schemas"]["ActivePolicyListResponse"]
    >();
    expectTypeOf<ActivePolicySummary>().toEqualTypeOf<
      components["schemas"]["ActivePolicySummary"]
    >();
    expectTypeOf<ActivePolicySummary["notification_type"]>().toBeString();
    expectTypeOf<ActivePolicySummary["dedup_window_seconds"]>().toBeNumber();
    expectTypeOf<ActivePolicyListResponse["total_count"]>().toBeNumber();
  });

  it("includes the /ui/policies/revisions endpoint and PolicyRevisionListResponse / PolicyRevisionSummary schemas", () => {
    expectTypeOf<paths["/ui/policies/revisions"]>().toBeObject();
    expectTypeOf<
      components["schemas"]["PolicyRevisionSummary"]["notification_type"]
    >().toBeString();
    expectTypeOf<
      components["schemas"]["PolicyRevisionSummary"]["version"]
    >().toBeString();
    expectTypeOf<
      components["schemas"]["PolicyRevisionSummary"]["status"]
    >().toBeString();
    expectTypeOf<
      components["schemas"]["PolicyRevisionListResponse"]["total_count"]
    >().toBeNumber();
  });

  it("includes updated RuntimeDeliveryState lineage and bounded event fields", () => {
    expectTypeOf<RuntimeDeliveryState>().toEqualTypeOf<
      components["schemas"]["RuntimeDeliveryState"]
    >();
    expectTypeOf<RuntimeDeliveryState["delivery_status"]>().toBeString();
    expectTypeOf<RuntimeDeliveryState["dead_letter"]>().toBeBoolean();
    expectTypeOf<RuntimeDeliveryState["obligation_owner_id"]>().toEqualTypeOf<
      string | null | undefined
    >();
    expectTypeOf<RuntimeDeliveryState["effective_ack_status"]>().toEqualTypeOf<
      string | null | undefined
    >();
    expectTypeOf<RuntimeDeliveryState["ack_inherited"]>().toEqualTypeOf<
      boolean | undefined
    >();
    expectTypeOf<RuntimeDeliveryState["events_total_count"]>().toEqualTypeOf<
      number | undefined
    >();
    expectTypeOf<RuntimeDeliveryState["events_truncated"]>().toEqualTypeOf<
      boolean | undefined
    >();
  });
});
