/**
 * Generates apps/ui/src/types/generated.ts from the UNS Console OpenAPI
 * spec. Spec is exported offline by importing the FastAPI app directly,
 * avoiding any dependency on a running Console process.
 *
 * Run with: npm run generate-types
 */

import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = join(ROOT, "..", "..");
const OUT_FILE = join(ROOT, "src", "types", "generated.ts");

async function main(): Promise<void> {
  console.log("Exporting OpenAPI spec from uns.app via uv run python...");
  const specJson = execSync(
    `uv run python -c "import os, json; os.environ['UNS_ENABLE_DOCS']='true'; from uns import Runtime; from uns.app import create_app; print(json.dumps(create_app(runtime=Runtime('sqlite://', create_tables=True), skip_persistence_config=True).openapi()))"`,
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "inherit"], maxBuffer: 32 * 1024 * 1024 },
  ).toString();

  const spec = JSON.parse(specJson);
  spec.components ??= {};
  spec.components.schemas ??= {};

  if (!spec.components.schemas.RuntimeEvent) {
    spec.components.schemas.RuntimeEvent = {
      title: "RuntimeEvent",
      description: "Single runtime obligation lifecycle event.",
      type: "object",
      required: ["id", "notification_id", "kind", "at", "payload"],
      properties: {
        id: { type: "string", title: "Id" },
        notification_id: { type: "string", format: "uuid", title: "Notification Id" },
        kind: { type: "string", title: "Kind" },
        at: { type: "number", title: "At" },
        payload: { type: "object", additionalProperties: true, title: "Payload" },
        callback_pending: { type: "boolean", title: "Callback Pending" },
        callback_attempts: { type: "integer", title: "Callback Attempts" },
        callback_error: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Callback Error",
        },
      },
    };
  }

  if (!spec.components.schemas.RuntimeDeliveryState) {
    spec.components.schemas.RuntimeDeliveryState = {
      title: "RuntimeDeliveryState",
      description: "Durable runtime delivery and obligation lineage state.",
      type: "object",
      required: ["delivery_status", "ack_status", "dead_letter"],
      properties: {
        delivery_status: { type: "string", title: "Delivery Status" },
        ack_status: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Ack Status",
        },
        deadline: {
          anyOf: [{ type: "number" }, { type: "null" }],
          title: "Deadline",
        },
        dead_letter: { type: "boolean", title: "Dead Letter" },
        replay_blocked_by: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Replay Blocked By",
        },
        replay_block_reason: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Replay Block Reason",
        },
        policy_config_hash: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Policy Config Hash",
        },
        policy_evaluation_id: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Policy Evaluation Id",
        },
        require_ack: { type: "boolean", title: "Require Ack" },
        obligation_owner_id: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Obligation Owner Id",
        },
        effective_status: { type: "string", title: "Effective Status" },
        effective_ack_status: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Effective Ack Status",
        },
        ack_inherited: { type: "boolean", title: "Ack Inherited" },
        obligation_resolution_status: {
          type: "string",
          title: "Obligation Resolution Status",
        },
        obligation_resolution_error: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Obligation Resolution Error",
        },
        actor: {
          anyOf: [{ type: "string" }, { type: "null" }],
          title: "Actor",
        },
        responded_at: {
          anyOf: [{ type: "number" }, { type: "null" }],
          title: "Responded At",
        },
        response_metadata: {
          anyOf: [
            { type: "object", additionalProperties: true },
            { type: "null" },
          ],
          title: "Response Metadata",
        },
        events: {
          type: "array",
          items: { $ref: "#/components/schemas/RuntimeEvent" },
          title: "Events",
        },
        events_total_count: { type: "integer", title: "Events Total Count" },
        events_truncated: { type: "boolean", title: "Events Truncated" },
      },
    };
  }

  if (spec.components.schemas.DeliveryTimelineResponse?.properties?.runtime_state) {
    spec.components.schemas.DeliveryTimelineResponse.properties.runtime_state = {
      anyOf: [
        { $ref: "#/components/schemas/RuntimeDeliveryState" },
        { type: "null" },
      ],
      title: "Runtime State",
    };
  }

  console.log(`Spec OK: title="${spec.info.title}" paths=${Object.keys(spec.paths ?? {}).length}`);

  const ast = await openapiTS(spec);
  const contents = astToString(ast);

  mkdirSync(dirname(OUT_FILE), { recursive: true });
  const banner =
    "/* AUTO-GENERATED by scripts/generate-types.ts. Do not edit by hand.\n" +
    " * Refresh on demand via: npm run generate-types\n" +
    " */\n\n";
  const aliases =
    "\nexport type ConsoleSessionResponse = components[\"schemas\"][\"ConsoleSessionResponse\"];\n" +
    "export type ActivePolicySummary = components[\"schemas\"][\"ActivePolicySummary\"];\n" +
    "export type ActivePolicyListResponse = components[\"schemas\"][\"ActivePolicyListResponse\"];\n" +
    "export type RuntimeEvent = components[\"schemas\"][\"RuntimeEvent\"];\n" +
    "export type RuntimeDeliveryState = components[\"schemas\"][\"RuntimeDeliveryState\"];\n";
  writeFileSync(OUT_FILE, banner + contents + aliases);
  console.log(`Wrote ${OUT_FILE}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
