/**
 * Sanity test for the generated OpenAPI types. Doesn't validate every type
 * exhaustively — just confirms the file is present, parseable as TypeScript,
 * and contains a known endpoint we expect from the AGSignal Console API.
 */

import { describe, it, expectTypeOf } from "vitest";
import type { paths } from "../src/types/generated";

describe("generated types", () => {
  it("includes the /ui/audit endpoint", () => {
    expectTypeOf<paths["/ui/audit"]>().toBeObject();
  });

  it("includes the /v1/notifications/{notification_id}/ack endpoint", () => {
    expectTypeOf<paths["/v1/notifications/{notification_id}/ack"]>().toBeObject();
  });
});
