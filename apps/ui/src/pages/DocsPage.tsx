/**
 * DocsPage — In-Portal Documentation & Runbooks Workspace (/docs)
 *
 * Implements a Modernist two-column split layout (260px sticky left section index
 * + main documentation reader) with URL deep-linking (?section=) and instant
 * cross-section keyword filtering across all 5 documentation domains:
 * 1. Overview & Visual Grammar (capability pills, BroadcastChannel session sync, badge grammar)
 * 2. Console Surfaces & Workflows (/deliveries, /policy, /operations, /invariants, /audit)
 * 3. Architecture & State Machines (delivery lifecycle, ACK lifecycle, idempotency vs. dedup)
 * 4. Producer, MIP & Agent MCP (uns.Runtime, mip-uns, WebSocket subprotocols, uns-mcp, smoke)
 * 5. Incident Runbooks (TSG-01 through TSG-06)
 */

import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ROUTES } from '../types/routes';

export type DocsSectionId =
  | 'overview'
  | 'workflows'
  | 'state-machines'
  | 'integration'
  | 'runbooks'
  | 'all';

interface DocsSectionMeta {
  readonly id: Exclude<DocsSectionId, 'all'>;
  readonly navLabel: string;
  readonly navSubtitle: string;
  readonly heading: string;
  readonly summary: string;
}

interface DocsCardEntry {
  readonly id: string;
  readonly sectionId: Exclude<DocsSectionId, 'all'>;
  readonly title: string;
  readonly tag: string;
  readonly keywords: string;
  readonly render: () => ReactNode;
}

const SECTION_META: readonly DocsSectionMeta[] = [
  {
    id: 'overview',
    navLabel: '1. Overview & Visual Grammar',
    navSubtitle: 'Auth scopes, multi-tab sync & badge grammar',
    heading: '1. Overview & Visual Grammar',
    summary:
      'Server-verified session capability introspection, tab-memory credential security, and the Modernist filled vs. outlined badge visual grammar.',
  },
  {
    id: 'workflows',
    navLabel: '2. Console Surfaces & Workflows',
    navSubtitle: 'Deliveries, Policy, Operations, Audit & Invariants',
    heading: '2. Console Surfaces & Workflows',
    summary:
      'Operational workflows across all console workspaces, including responder ACK/Dismiss, policy simulation & revision governance, DLQ replay/resolve, and 1e lifecycle correlation.',
  },
  {
    id: 'state-machines',
    navLabel: '3. Architecture & State Machines',
    navSubtitle: 'Delivery, ACK deadlines, idempotency & dedup',
    heading: '3. Architecture & State Machines',
    summary:
      'Authoritative state machines for transactional outbox delivery, human acknowledgment obligations, and idempotency vs. semantic deduplication.',
  },
  {
    id: 'integration',
    navLabel: '4. Producer, MIP & Agent MCP',
    navSubtitle: 'Python SDK, HTTP API, WebSocket & uns-mcp',
    heading: '4. Producer, MIP & Agent MCP',
    summary:
      'First-party Market Insights Platform (mip-uns) integration, HTTP producer contracts, WebSocket subprotocol authentication, MCP tool safety, and opt-in channel smoke verification.',
  },
  {
    id: 'runbooks',
    navLabel: '5. Incident Runbooks (TSG-01–06)',
    navSubtitle: 'DLQ replay, leases, timeouts, policies & WAL backups',
    heading: '5. Incident Runbooks (TSG-01–06)',
    summary:
      'Symptom-driven Troubleshooting Guides (TSG-01 through TSG-06) with diagnostic commands, SQLite queries, and safe operator remediation workflows.',
  },
] as const;

const VALID_SECTIONS: ReadonlySet<string> = new Set([
  'overview',
  'workflows',
  'state-machines',
  'integration',
  'runbooks',
  'all',
]);

function parseSectionParam(raw: string | null): DocsSectionId {
  if (raw && VALID_SECTIONS.has(raw)) {
    return raw as DocsSectionId;
  }
  return 'overview';
}

const DOCS_CARDS: readonly DocsCardEntry[] = [
  // =========================================================================
  // SECTION 1: OVERVIEW & VISUAL GRAMMAR
  // =========================================================================
  {
    id: 'overview-capabilities',
    sectionId: 'overview',
    title: 'Session Capability Introspection (GET /ui/session) & Non-Lossy Capability Pills',
    tag: 'AUTH & RBAC',
    keywords:
      'GET /ui/session ConsoleSessionResponse OPERATOR RESPONDER PRODUCER READ-ONLY observer responder producer admin scopes capability pills persistence_mode INV-UI-001',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          On sign-in, the console authenticates against <code>GET /ui/session</code> (
          <code>ConsoleSessionResponse</code>), which returns the verified principal{' '}
          <code>subject</code>, granted <code>scopes</code> (<code>observer</code>,{' '}
          <code>responder</code>, <code>producer</code>, <code>admin</code>), and runtime{' '}
          <code>persistence_mode</code>. Multi-role principals render all applicable capability
          pills simultaneously without hiding lower-ranked capabilities.
        </p>
        <div className="table-container" style={{ border: '1px solid var(--color-divider)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Capability Pill</th>
                <th>Server Scope(s)</th>
                <th>Permitted Console &amp; API Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <span className="nav-badge nav-badge-operator">OPERATOR</span>
                </td>
                <td>
                  <code>admin</code>
                </td>
                <td>
                  Full administrative authority: atomic policy reload (
                  <code>POST /api/v1/policies/reload</code>), dead-letter <strong>Replay</strong> (
                  <code>POST /api/v1/runtime/notifications/&#123;id&#125;/replay</code>) and{' '}
                  <strong>Resolve</strong> (<code>DELETE /api/v1/dlq/&#123;id&#125;</code>), plus
                  all Responder, Producer, and Observer capabilities.
                </td>
              </tr>
              <tr>
                <td>
                  <span className="nav-badge nav-badge-responder">RESPONDER</span>
                </td>
                <td>
                  <code>responder</code> (or <code>admin</code>)
                </td>
                <td>
                  Inline obligation triage on <code>/deliveries/:notificationId</code>:{' '}
                  <strong>Acknowledge</strong> (
                  <code>POST /api/v1/notifications/&#123;id&#125;/ack</code>) and{' '}
                  <strong>Dismiss</strong> (
                  <code>POST /api/v1/notifications/&#123;id&#125;/dismiss</code>) with responder
                  notes, plus interactive WebSocket <code>ack</code>/<code>dismiss</code> commands.
                </td>
              </tr>
              <tr>
                <td>
                  <span className="nav-badge nav-badge-producer">PRODUCER</span>
                </td>
                <td>
                  <code>producer</code> (or <code>admin</code>)
                </td>
                <td>
                  Dry-Run Policy Simulator (<code>POST /api/v1/notifications/simulate</code>) and
                  synthetically tagged <code>[TEST]</code> live verification dispatch (
                  <code>POST /api/v1/notifications</code>) in <code>/policy</code>.
                </td>
              </tr>
              <tr>
                <td>
                  <span className="nav-badge">READ-ONLY</span>
                </td>
                <td>
                  <code>observer</code> only
                </td>
                <td>
                  Strictly non-mutating flight-instrument telemetry across <code>GET /ui/*</code>,{' '}
                  <code>GET /readyz</code>, <code>GET /api/v1/channels/health</code>,{' '}
                  <code>GET /api/v1/dlq</code>, and <code>GET /api/v1/runtime/dead-letters</code>{' '}
                  (enforcing <code>INV-UI-001</code>).
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </>
    ),
  },
  {
    id: 'overview-session-sync',
    sectionId: 'overview',
    title: 'Tab-Memory Credential Security & Multi-Tab BroadcastChannel Synchronization',
    tag: 'SESSION SECURITY',
    keywords:
      'apps/ui/src/auth/session.ts BroadcastChannel uns_console_session UNS_SESSION_REQUEST UNS_SESSION_GRANT UNS_SESSION_SYNC UNS_SESSION_EXPIRE UNS_SESSION_CLEAR tab memory 401 403',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          API credentials are held exclusively in JavaScript module memory (
          <code>apps/ui/src/auth/session.ts</code>) and are <strong>never</strong> written to{' '}
          <code>localStorage</code>, <code>sessionStorage</code>, cookies, or URL query parameters.
          Sibling tabs on the same origin coordinate in-memory state over{' '}
          <code>BroadcastChannel(&apos;uns_console_session&apos;)</code>:
        </p>
        <div className="table-container" style={{ border: '1px solid var(--color-divider)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Channel Message Type</th>
                <th>Trigger &amp; In-Memory Handshake Behavior</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <code>UNS_SESSION_REQUEST</code>
                </td>
                <td>
                  Broadcast by a newly opened browser tab when its in-memory{' '}
                  <code>credential</code> is <code>null</code>.
                </td>
              </tr>
              <tr>
                <td>
                  <code>UNS_SESSION_GRANT</code>
                </td>
                <td>
                  Sent by an authenticated peer tab in response to <code>UNS_SESSION_REQUEST</code>,
                  sharing <code>credential</code>, <code>subject</code>, <code>scopes</code>, and{' '}
                  <code>persistenceMode</code> in memory.
                </td>
              </tr>
              <tr>
                <td>
                  <code>UNS_SESSION_SYNC</code>
                </td>
                <td>
                  Broadcast when an operator signs in or updates session metadata via{' '}
                  <code>startConsoleSession()</code> so open tabs adopt the verified session.
                </td>
              </tr>
              <tr>
                <td>
                  <code>UNS_SESSION_EXPIRE</code>
                </td>
                <td>
                  Broadcast on <code>401 Unauthorized</code> via <code>expireConsoleSession()</code>{' '}
                  (fenced to the matching credential so a late response from an older session never
                  invalidates a newer login). Note: <code>403 Forbidden</code> surfaces an inline
                  scope error without destroying the session.
                </td>
              </tr>
              <tr>
                <td>
                  <code>UNS_SESSION_CLEAR</code>
                </td>
                <td>
                  Broadcast when clicking <strong>Sign out</strong> (
                  <code>clearConsoleSession()</code>), immediately purging credentials across all
                  open tabs.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </>
    ),
  },
  {
    id: 'overview-badge-grammar',
    sectionId: 'overview',
    title: 'Modernist Badge Visual Grammar: Filled Delivery vs. Outlined Human Response',
    tag: 'VISUAL GRAMMAR',
    keywords:
      'Modernist badge visual grammar filled delivery state outlined human response obligation DELIVERED FAILED DEAD-LETTER PENDING DEDUPLICATED ACKED DISMISSED ACK TIMEOUT ACK PENDING Archivo #f3f2f2 #eae9e9 #201e1d #ec3013',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          To prevent operators from conflating <strong>machine channel transport</strong> with{' '}
          <strong>human obligation acknowledgment</strong>, the Modernist design system enforces a
          strict visual dichotomy: <strong>Filled badges</strong> represent transport delivery
          states, while <strong>Outlined badges</strong> represent human response states.
        </p>
        <div className="table-container" style={{ border: '1px solid var(--color-divider)' }}>
          <table className="data-table" data-testid="docs-badge-grammar-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Rendered Badge</th>
                <th>CSS Token / Rule</th>
                <th>Operational Meaning</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <strong>Machine Delivery (Filled)</strong>
                </td>
                <td>
                  <span className="badge tag-delivery-ok">DELIVERED</span>
                </td>
                <td>
                  <code>.tag-delivery-ok</code> (Solid <code>#201e1d</code> ink fill)
                </td>
                <td>
                  At least one configured channel adapter succeeded and committed before worker
                  lease expiration.
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Machine Delivery (Filled)</strong>
                </td>
                <td>
                  <span className="badge tag-delivery-fail">FAILED</span>{' '}
                  <span className="badge tag-delivery-fail">DEAD-LETTER</span>
                </td>
                <td>
                  <code>.tag-delivery-fail</code> (Solid <code>#ec3013</code> signal vermilion)
                </td>
                <td>
                  Exhausted all configured fallback channels across <code>max_attempts</code>;{' '}
                  <code>DEAD-LETTER</code> indicates a <code>GUARANTEED</code> obligation in DLQ (
                  <code>dead_letter = true</code>).
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Machine Delivery (Pending)</strong>
                </td>
                <td>
                  <span className="badge tag-delivery-pending">PENDING</span>
                </td>
                <td>
                  <code>.tag-delivery-pending</code> (Dashed neutral stroke)
                </td>
                <td>
                  Queued in transactional outbox awaiting initial dispatch, backoff retry, or
                  in-flight leader settlement.
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Machine Delivery (Coalesced)</strong>
                </td>
                <td>
                  <span className="badge tag-delivery-info">DEDUPLICATED</span>
                </td>
                <td>
                  <code>.tag-delivery-info</code> (Stone <code>#eae9e9</code> fill)
                </td>
                <td>
                  Suppressed as a semantic duplicate within <code>dedup_window_seconds</code> and
                  linked to canonical <code>obligation_owner_id</code>.
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Human Response (Outlined)</strong>
                </td>
                <td>
                  <span className="badge tag-response-ok">ACKED</span>
                </td>
                <td>
                  <code>.tag-response-ok</code> (<code>1.5px solid #201e1d</code> transparent)
                </td>
                <td>
                  Human operator or agent acknowledged the obligation before <code>deadline</code>.
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Human Response (Outlined)</strong>
                </td>
                <td>
                  <span className="badge tag-response-warn">DISMISSED</span>
                </td>
                <td>
                  <code>.tag-response-warn</code> (<code>1.5px solid</code> neutral outline)
                </td>
                <td>
                  Operator explicitly dismissed the notification obligation with audit attribution.
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Human Response (Outlined)</strong>
                </td>
                <td>
                  <span className="badge tag-response-fail">ACK TIMEOUT</span>
                </td>
                <td>
                  <code>.tag-response-fail</code> (<code>1.5px solid #ec3013</code> vermilion
                  outline)
                </td>
                <td>
                  Acknowledgment deadline elapsed; swept by <code>uns-timeout-worker</code> (
                  <code>ack_status = &quot;TIMED_OUT&quot;</code>,{' '}
                  <code>escalation_required = true</code>).
                </td>
              </tr>
              <tr>
                <td>
                  <strong>Human Response (Outlined)</strong>
                </td>
                <td>
                  <span className="badge tag-response-none">ACK PENDING</span>
                </td>
                <td>
                  <code>.tag-response-none</code> (<code>1.5px dashed</code> transparent outline)
                </td>
                <td>
                  Delivered with <code>require_ack = true</code>; awaiting responder action before{' '}
                  <code>deadline</code>.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </>
    ),
  },

  // =========================================================================
  // SECTION 2: CONSOLE SURFACES & WORKFLOWS
  // =========================================================================
  {
    id: 'workflows-deliveries',
    sectionId: 'workflows',
    title: 'Deliveries & Obligation Triage (/deliveries & /deliveries/:id)',
    tag: 'SURFACE 1',
    keywords:
      'Deliveries /deliveries /deliveries/:notificationId obligation_owner_id ack_inherited effective_ack_status events_truncated 100 events Acknowledge Dismiss POST /api/v1/notifications/{id}/ack dismiss 409 Conflict responder notes',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          The Deliveries Explorer (<code>GET /ui/deliveries</code>) and Delivery Detail view (
          <code>GET /ui/deliveries/&#123;notification_id&#125;</code>) pair channel delivery attempt
          history with the durable runtime obligation ledger (<code>RuntimeDeliveryState</code>):
        </p>
        <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' }}>
          <li>
            <strong>Canonical Owner vs. Deduplicated Follower Lineage:</strong> Surfaces{' '}
            <code>obligation_owner_id</code>, <code>ack_inherited</code>,{' '}
            <code>effective_ack_status</code>, <code>obligation_resolution_status</code>, and{' '}
            <code>obligation_resolution_error</code>. When a notification is deduplicated (
            <code>obligation_owner_id !== notification_id</code>), the detail view links directly to
            the canonical owner and routes ACK/Dismiss actions to that owner.
          </li>
          <li>
            <strong>Bounded Runtime Event Stream:</strong> Renders chronological{' '}
            <code>uns_events</code> rows (<code>ACCEPTED</code>, <code>CHANNEL_ATTEMPT_STARTED</code>
            , <code>CHANNEL_ATTEMPT_RESULT</code>, <code>DELIVERY_RESULT</code>, <code>ACKED</code>)
            capped at the most recent <strong>100 events</strong> (<code>events_total_count</code>,{' '}
            <code>events_truncated</code>).
          </li>
          <li>
            <strong>Inline Responder Acknowledge &amp; Dismiss:</strong> Principals with{' '}
            <code>RESPONDER</code> or <code>OPERATOR</code> capability can execute{' '}
            <code>POST /api/v1/notifications/&#123;id&#125;/ack</code> and{' '}
            <code>POST /api/v1/notifications/&#123;id&#125;/dismiss</code> with optional responder
            notes (<code>metadata.note</code>).
          </li>
          <li>
            <strong>Automatic 409 Conflict Recovery:</strong> If another responder or the timeout
            worker settles the obligation concurrently (returning <code>409 Conflict</code>), the UI
            automatically re-fetches the delivery detail timeline and displays a concurrency notice.
          </li>
        </ul>
        <div>
          <Link to={ROUTES.DELIVERIES} className="btn btn-secondary">
            Open Deliveries Explorer &rarr;
          </Link>
        </div>
      </>
    ),
  },
  {
    id: 'workflows-policy',
    sectionId: 'workflows',
    title: 'Policy Workspace: Catalog, Resolution Trace, Revisions, Simulator & Reload (/policy)',
    tag: 'SURFACE 2',
    keywords:
      'Policy Workspace /policy GET /ui/policies/active GET /ui/policies/effective GET /ui/policies/revisions explicit_override mode_override policy_base sdk_default ACTIVE PREVIEW DRAFT RETIRED simulate [TEST] live dispatch POST /api/v1/policies/reload',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          The Policy Workspace unifies live policy inspection, revision governance, dry-run
          simulation, and atomic reload:
        </p>
        <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' }}>
          <li>
            <strong>Active Policies Catalog (<code>GET /ui/policies/active</code>):</strong> Lists
            all registered active routing policies with clickable rows that populate the inspector
            and synchronize <code>?notification_type=</code> URL deep-links.
          </li>
          <li>
            <strong>Effective Policy Resolution Trace (<code>GET /ui/policies/effective</code>):</strong>{' '}
            Evaluates precedence across <code>explicit_override</code> &rarr;{' '}
            <code>mode_override</code> &rarr; <code>policy_base</code> &rarr;{' '}
            <code>sdk_default</code> for any combination of <code>notification_type</code>,{' '}
            <code>intent</code>, <code>autonomy_mode</code>, and <code>irreversible</code>.
          </li>
          <li>
            <strong>Policy Revision History &amp; Governance (<code>GET /ui/policies/revisions</code>):</strong>{' '}
            Surfaces durable revision records across <code>ACTIVE</code>, <code>PREVIEW</code>,{' '}
            <code>DRAFT</code>, and <code>RETIRED</code> states, including{' '}
            <code>policy_revision_id</code>, <code>supersedes_revision_id</code> lineage,{' '}
            <code>content_hash</code>, and actor attribution (<code>created_by</code>,{' '}
            <code>published_by</code>).
          </li>
          <li>
            <strong>Dry-Run Simulator &amp; Synthetically Tagged <code>[TEST]</code> Dispatch:</strong>{' '}
            Principals with <code>PRODUCER</code> or <code>OPERATOR</code> capability can run
            side-effect-free simulations (<code>POST /api/v1/notifications/simulate</code>) or
            dispatch a live verification signal prefixed with <code>[TEST]</code> (
            <code>source: &quot;uns-console-policy-test&quot;</code>) via{' '}
            <code>POST /api/v1/notifications</code>.
          </li>
          <li>
            <strong>Atomic Policy Reload (<code>POST /api/v1/policies/reload</code>):</strong>{' '}
            Gated by <code>OPERATOR</code> (<code>admin</code> scope); validates YAML policies on
            disk and atomically advances the durable policy snapshot revision.
          </li>
        </ul>
        <div>
          <Link to={ROUTES.POLICY} className="btn btn-secondary">
            Open Policy Workspace &rarr;
          </Link>
        </div>
      </>
    ),
  },
  {
    id: 'workflows-operations',
    sectionId: 'workflows',
    title: 'Operations & Dead-Letter Recovery (/operations)',
    tag: 'SURFACE 3',
    keywords:
      'Operations /operations GET /readyz 503 GET /api/v1/channels/health GET /api/v1/dlq GET /api/v1/runtime/dead-letters Replay Resolve replay_blocked_by replay_block_reason DELETE /api/v1/dlq/{entry_id}',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          The Operations workspace polls four telemetry endpoints independently via{' '}
          <code>Promise.allSettled</code> so a degraded probe or <code>503</code> never blocks
          sibling panels:
        </p>
        <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' }}>
          <li>
            <strong>Readiness &amp; Persistence Probe (<code>GET /readyz</code>):</strong> Decodes
            JSON payloads across both <code>200 OK</code> and <code>503 Service Unavailable</code>{' '}
            to surface database connectivity, policy store hydration, persistence mode, and DLQ
            depth.
          </li>
          <li>
            <strong>Channel Adapter Health (<code>GET /api/v1/channels/health</code>):</strong>{' '}
            Displays per-adapter health status (<code>HEALTHY</code>, <code>DEGRADED</code>,{' '}
            <code>UNHEALTHY</code>), consecutive failures, and last error reason.
          </li>
          <li>
            <strong>Unified Dead-Letter Queue (Full Outer Join):</strong> Correlates{' '}
            <code>GET /api/v1/dlq</code> with <code>GET /api/v1/runtime/dead-letters</code> by{' '}
            <code>notification_id</code>, displaying cycle attempts, failed channels, and{' '}
            <code>replay_blocked_by</code> / <code>replay_block_reason</code>.
          </li>
          <li>
            <strong>Inline Replay vs. Resolve:</strong> Principals with <code>OPERATOR</code>{' '}
            capability can trigger <strong>Replay</strong> (when <code>replay_blocked_by</code> is{' '}
            <code>null</code>) to start delivery Cycle <code>N+1</code>, or{' '}
            <strong>Resolve</strong> (<code>DELETE /api/v1/dlq/&#123;entry_id&#125;</code>) to clear{' '}
            <code>dead_letter = false</code> with an audited <code>FAILURE_RESOLVED</code> event.
          </li>
        </ul>
        <div>
          <Link to={ROUTES.OPERATIONS} className="btn btn-secondary">
            Open Operations Workspace &rarr;
          </Link>
        </div>
      </>
    ),
  },
  {
    id: 'workflows-audit-invariants',
    sectionId: 'workflows',
    title: 'Audit Timeline (/audit 1e & 1d Views) & System Invariants (/invariants)',
    tag: 'SURFACES 4 & 5',
    keywords:
      'Audit Timeline /audit 1e By notification 1d All events TIME TO RESPOND System Invariants /invariants INV-UI-001 GET /ui/invariants GET /ui/audit',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          Compliance verification and lifecycle observability are anchored by the Audit Timeline and
          System Invariants views:
        </p>
        <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' }}>
          <li>
            <strong>Audit Timeline — <code>1e</code> By Notification Lifecycle Table:</strong>{' '}
            Correlates all audit events for each <code>notification_id</code> into a single
            lifecycle row (
            <code>NOTIFICATION | STARTED | DELIVERED | RESPONSE | TIME TO RESPOND</code>), computing
            elapsed response time (<code>ack.received</code> / <code>ack.dismissed</code> /{' '}
            <code>ack.timed_out</code> minus <code>notification.created</code>) with expandable
            per-event drill-down.
          </li>
          <li>
            <strong>Audit Timeline — <code>1d</code> All Events Stream:</strong> Chronological
            compliance event stream with filtering by <code>event_type</code>,{' '}
            <code>notification_id</code>, <code>agent_id</code>, <code>autonomy_mode</code>,{' '}
            <code>correlation_id</code>, and UTC time bounds.
          </li>
          <li>
            <strong>System Invariants (<code>/invariants</code>):</strong> Queries{' '}
            <code>GET /ui/invariants</code> and <code>GET /ui/invariants/summary</code> to verify
            runtime, schema, static-analysis, and test invariants (including{' '}
            <code>INV-UI-001</code>) with links to repository evidence.
          </li>
        </ul>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <Link to={ROUTES.AUDIT} className="btn btn-secondary">
            Open Audit Timeline &rarr;
          </Link>
          <Link to={ROUTES.INVARIANTS} className="btn btn-secondary">
            Open System Invariants &rarr;
          </Link>
        </div>
      </>
    ),
  },

  // =========================================================================
  // SECTION 3: ARCHITECTURE & STATE MACHINES
  // =========================================================================
  {
    id: 'state-machines-delivery',
    sectionId: 'state-machines',
    title: 'Delivery & Deduplication State Machine (uns_notifications.status)',
    tag: 'DELIVERY LIFECYCLE',
    keywords:
      'Delivery State Machine PENDING DELIVERED DEDUPLICATED FAILED dead_letter=true GUARANTEED BEST_EFFORT Replay Cycle N+1 DEDUP_OWNER_PROMOTED OBLIGATION_HANDED_OFF DEDUP_RELINKED max_attempts',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          Every accepted notification in <code>uns_notifications</code> transitions through a
          lease-fenced transactional outbox state machine managed by <code>uns.Runtime</code>:
        </p>
        <pre className="docs-code-block">
          {`[Intake: Runtime.accept()]
   ├── No active dedup leader ──────────────► PENDING (Leader: dedup_owner_id = NULL)
   ├── Active PENDING leader in window ─────► PENDING (Follower: dedup_owner_id = <leader_uuid>)
   └── Active DELIVERED leader in window ───► DEDUPLICATED (dedup_owner_id = <leader_uuid>)

[Worker Dispatch: Runtime.dispatch() — 60s lease_token]
   PENDING (Leader)
   ├── Adapter succeeds before lease expiry ► DELIVERED (Followers settle as DEDUPLICATED)
   ├── Adapter fails (cycle_attempts < max) ► PENDING (Exponential backoff retry)
   ├── Exhausted (BEST_EFFORT mode) ────────► FAILED (dead_letter = false)
   └── Exhausted (GUARANTEED mode) ─────────► FAILED + dead_letter = true (DLQ)
         ├── First pending follower promoted ► DEDUP_OWNER_PROMOTED + OBLIGATION_HANDED_OFF
         ├── Operator POST .../replay ──────► PENDING (Cycle N+1, only when replay_blocked_by is null)
         └── Operator DELETE /api/v1/dlq/{id}► FAILED (dead_letter = false, FAILURE_RESOLVED)`}
        </pre>
      </>
    ),
  },
  {
    id: 'state-machines-ack',
    sectionId: 'state-machines',
    title: 'Obligation Acknowledgment State Machine (uns_notifications.ack_status)',
    tag: 'OBLIGATION LIFECYCLE',
    keywords:
      'Obligation Acknowledgment State Machine PENDING ACKED DISMISSED TIMED_OUT terminal immutability 409 Conflict follower inheritance ack_inherited effective_ack_status uns-timeout-worker escalation_required',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          When a notification with <code>require_ack = true</code> reaches{' '}
          <code>status = &quot;DELIVERED&quot;</code>, <code>Runtime.dispatch()</code> initializes{' '}
          <code>ack_status = &quot;PENDING&quot;</code> and computes{' '}
          <code>deadline = delivered_at + 60 * ack_timeout_minutes</code> (default <code>15m</code>{' '}
          for <code>SAFETY</code>, <code>30m</code> for <code>GOVERNANCE</code>):
        </p>
        <pre className="docs-code-block">
          {`[Before DELIVERED or require_ack = false] ──► ack_status = NULL
[Leader reaches DELIVERED (require_ack = true)]
   └──► ack_status = PENDING (deadline = delivered_at + 60 * ack_timeout_minutes)
          ├── POST /api/v1/notifications/{id}/ack ─────► ACKED (Terminal, actor attributed)
          ├── POST /api/v1/notifications/{id}/dismiss ─► DISMISSED (Terminal, actor attributed)
          └── Runtime.expire() sweep (deadline <= now) ► TIMED_OUT (Terminal, actor="uns-timeout-worker",
                                                                    escalation_required=true)`}
        </pre>
        <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' }}>
          <li>
            <strong>Terminal Immutability &amp; <code>409 Conflict</code>:</strong> Once{' '}
            <code>ack_status</code> enters <code>ACKED</code>, <code>DISMISSED</code>, or{' '}
            <code>TIMED_OUT</code>, any competing transition or different actor raises{' '}
            <code>409 Conflict</code>. Repeating the exact same transition by the same actor is
            idempotent.
          </li>
          <li>
            <strong>Follower Inheritance:</strong> Deduplicated followers inherit their canonical
            owner&apos;s response state via <code>effective_ack_status</code> and{' '}
            <code>ack_inherited = true</code>.
          </li>
        </ul>
      </>
    ),
  },
  {
    id: 'state-machines-idempotency-vs-dedup',
    sectionId: 'state-machines',
    title: 'Idempotency (idempotency_key) vs. Semantic Deduplication (dedup_key)',
    tag: 'DEDUP CONTRACT',
    keywords:
      'idempotency_key dedup_key dedup_window_seconds idempotent_replay 409 Conflict DEDUPLICATED uns_dedup effective_hash',
    render: () => (
      <div className="table-container" style={{ border: '1px solid var(--color-divider)' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Dimension</th>
              <th>
                Exact Request Idempotency (<code>idempotency_key</code>)
              </th>
              <th>
                Semantic Alert Coalescing (<code>dedup_key</code>)
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>Composite Key Scope</strong>
              </td>
              <td>
                <code>SHA-256([principal, source, idempotency_key])</code>
              </td>
              <td>
                <code>SHA-256([principal, source, dedup_key, effective_hash])</code>
              </td>
            </tr>
            <tr>
              <td>
                <strong>Active Horizon</strong>
              </td>
              <td>
                Until operational row is expired by <code>uns-maintain</code> (
                <code>idempotency_seconds</code>)
              </td>
              <td>
                Policy&apos;s <code>dedup_window_seconds</code> (default <code>300s</code>); pending
                leader ownership survives TTL expiry (<code>F-01</code>)
              </td>
            </tr>
            <tr>
              <td>
                <strong>Behavior on Match</strong>
              </td>
              <td>
                Identical payload returns original <code>notification_id</code> with{' '}
                <code>idempotent_replay: true</code>. Mutated payload with same key raises{' '}
                <code>409 Conflict</code>.
              </td>
              <td>
                Creates a new <code>notification_id</code> linked via{' '}
                <code>dedup_owner_id</code> to the window leader; settles as{' '}
                <code>DEDUPLICATED</code> when leader delivers, or promotes first follower if leader
                exhausts retries.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    ),
  },

  // =========================================================================
  // SECTION 4: PRODUCER, MIP & AGENT MCP
  // =========================================================================
  {
    id: 'integration-mip-producer',
    sectionId: 'integration',
    title: 'Python uns.Runtime / uns.Client & Market Insights Platform (mip-uns) Integration',
    tag: 'PRODUCER SDK & MIP',
    keywords:
      'uns.Runtime uns.Client mip-uns examples/mip_producer_demo.py governance.approval_required safety.kill_switch execution.slippage Market Insights Platform',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          First-party Python services and the <strong>Market Insights Platform (MIP)</strong>{' '}
          integrate via <code>uns.Runtime</code> + <code>uns.Client</code> or HTTP using the
          canonical <code>examples/policies/mip-uns</code> policy pack exercised by{' '}
          <code>examples/mip_producer_demo.py</code>:
        </p>
        <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' }}>
          <li>
            <code>governance.approval_required</code> (<code>GOVERNANCE</code>): Mode-aware routing
            and dry-run simulation via <code>client.simulate(request)</code>.
          </li>
          <li>
            <code>safety.kill_switch</code> (<code>SAFETY</code>, <code>irreversible=True</code>):
            Guaranteed multi-channel delivery requiring human acknowledgment (
            <code>require_ack=True</code>).
          </li>
          <li>
            <code>execution.slippage</code> (<code>OPERATIONAL</code>): High-frequency alert storm
            coalescing within <code>dedup_window_seconds</code> with{' '}
            <code>obligation_owner_id</code> lineage.
          </li>
        </ul>
        <pre className="docs-code-block">
          {`# Run standalone local recording MIP producer verification (SQLite + RecordingChannelAdapter)
uv run python examples/mip_producer_demo.py

# Run against live localhost UNS server with policy pack reload
export UNS_API_KEY="<YOUR_UNS_API_KEY>"
uv run python examples/mip_producer_demo.py --base-url http://127.0.0.1:18080 --reload-policies`}
        </pre>
      </>
    ),
  },
  {
    id: 'integration-http-autonomy',
    sectionId: 'integration',
    title: 'HTTP Producer API (POST /api/v1/notifications & /simulate) with AutonomyContext',
    tag: 'HTTP API',
    keywords:
      'POST /api/v1/notifications POST /api/v1/notifications/simulate AutonomyContext agent_id autonomy_mode plan_id decision_snapshot_id execution_snapshot_id PolicyOverrideError',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          Remote producers submit obligations to <code>POST /api/v1/notifications</code> (or
          side-effect-free previews to <code>POST /api/v1/notifications/simulate</code>) with a
          structured <code>autonomy_context</code>. Remember: <strong>Notification is not action
          approval</strong>—delivery or <code>ACKED</code> status records receipt of the obligation,
          not execution capability authorization.
        </p>
        <pre className="docs-code-block">
          {`curl -sS -X POST "$UNS_BASE_URL/api/v1/notifications" \\
  -H "Authorization: Bearer $UNS_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "notification_type": "safety.kill_switch",
    "intent": "SAFETY",
    "title": "MIP automated kill switch engaged on drawdown breach",
    "message": "Intraday drawdown reached 185 bps (limit 150 bps).",
    "source": "mip.risk.kill_switch",
    "irreversible": true,
    "idempotency_key": "mip-kill-switch-20261027-01",
    "dedup_key": "mip:kill_switch:momentum-v4",
    "autonomy_context": {
      "agent_id": "2c5f9b4c-6b3e-4d1a-9c12-4a8f0c8e7b11",
      "autonomy_mode": "LIVE",
      "plan_id": "9a1b2c3d-0000-1111-2222-333344445555",
      "decision_snapshot_id": "4d5e6f7a-1111-2222-3333-444455556666",
      "execution_snapshot_id": "7b8c9d0e-2222-3333-4444-555566667777"
    },
    "metadata": {
      "strategy_id": "momentum-v4",
      "observed_drawdown_bps": 185
    }
  }' | jq .`}
        </pre>
      </>
    ),
  },
  {
    id: 'integration-websocket-mcp-smoke',
    sectionId: 'integration',
    title: 'WebSocket Subprotocol Auth, MCP Server (uns-mcp) & Opt-In Channel Smoke Verifier',
    tag: 'WEBSOCKET, MCP & SMOKE',
    keywords:
      'Sec-WebSocket-Protocol agsignal.v1 bearer base64url_token /ws/agents/ uns-mcp local_mcp.py --enable-writes UNS_MCP_DELIVERY_CONFIRMATION_TOKEN 16 tools scripts/opt_in_channel_smoke.py --dry-run --execute',
    render: () => (
      <>
        <ul style={{ margin: 0, paddingLeft: '20px', display: 'grid', gap: '6px' }}>
          <li>
            <strong>WebSocket Subprotocol Authentication (<code>/ws/agents/&#123;agent_id&#125;</code>):</strong>{' '}
            Query-string tokens are forbidden. Browser clients authenticate via{' '}
            <code>Sec-WebSocket-Protocol: agsignal.v1, bearer.&lt;base64url_nopad_token&gt;</code>{' '}
            (with <code>Origin</code> matching <code>UNS_ALLOWED_ORIGINS</code>); native clients
            pass <code>Authorization: Bearer &lt;token&gt;</code>. Connected responders can send{' '}
            <code>&#123;&quot;type&quot;: &quot;ack&quot;, &quot;notification_id&quot;: &quot;...&quot;&#125;</code>{' '}
            for durable, actor-attributed acknowledgment.
          </li>
          <li>
            <strong>MCP Server (<code>uns-mcp</code> / <code>local_mcp.py</code>):</strong> Starts in
            read-only mode by default exposing <strong>16 tools</strong> for safe inspection and
            simulation. Passing <code>--enable-writes</code> requires persistent{' '}
            <code>UNS_DATABASE_URL</code>, <code>UNS_API_PRINCIPAL</code>, and{' '}
            <code>UNS_MCP_DELIVERY_CONFIRMATION_TOKEN</code>, and every live{' '}
            <code>send_signal</code> call must include <code>deliver=true</code>,{' '}
            <code>operator_intent=&quot;deliver&quot;</code>, and matching{' '}
            <code>operator_confirmation_token</code>.
          </li>
          <li>
            <strong>Opt-In Real-Channel Smoke Verifier (<code>scripts/opt_in_channel_smoke.py</code>):</strong>{' '}
            Defaults to <code>--dry-run</code> (zero external network traffic, masked PII email
            readiness report). Passing <code>--execute</code> dispatches a tagged{' '}
            <code>[UNS OPT-IN SMOKE]</code> signal through configured Slack, Email/SMTP, or
            PagerDuty adapters.
          </li>
        </ul>
        <pre className="docs-code-block">
          {`# 1. Inspect external provider readiness without sending network traffic (exits 0)
uv run python scripts/opt_in_channel_smoke.py --dry-run

# 2. Execute live [UNS OPT-IN SMOKE] verification on configured Slack channel
uv run python scripts/opt_in_channel_smoke.py --execute --channel slack`}
        </pre>
      </>
    ),
  },

  // =========================================================================
  // SECTION 5: INCIDENT RUNBOOKS (TSG-01–06)
  // =========================================================================
  {
    id: 'runbook-tsg-01',
    sectionId: 'runbooks',
    title: 'TSG-01: Dead-Letter Queue (DLQ) Triage & Safe Replay',
    tag: 'TSG-01 · DLQ & REPLAY',
    keywords:
      'TSG-01 Dead-Letter Queue DLQ Triage Safe Replay dlq_depth replay_blocked_by replay_block_reason DEDUP_OWNER_PROMOTED OBLIGATION_HANDED_OFF DELETE /api/v1/dlq F-01 F-02',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          <strong>Symptoms:</strong> <code>GET /readyz</code> reports <code>dlq_depth &gt; 0</code>,
          or <code>/operations</code> shows <code>GUARANTEED</code> notifications in{' '}
          <code>status: &quot;FAILED&quot;</code> with <code>dead_letter: true</code> after
          exhausting <code>max_attempts</code> (default <code>3</code>).
        </p>
        <p style={{ margin: 0 }}>
          <strong>Lineage &amp; Replay Guardrails (<code>F-01</code> / <code>F-02</code>):</strong>{' '}
          When a leader exhausts retries, <code>Runtime._settle_followers</code> promotes the first
          pending follower (<code>DEDUP_OWNER_PROMOTED</code>) and records{' '}
          <code>dedup_successor_id</code> + <code>OBLIGATION_HANDED_OFF</code>. Replay is blocked (
          <code>409 Conflict</code>) whenever <code>replay_blocked_by</code> is non-null (
          <code>PENDING</code>, <code>DELIVERED</code>, <code>DEDUPLICATED</code>, or{' '}
          <code>UNRESOLVED_LINEAGE</code>).
        </p>
        <pre className="docs-code-block">
          {`# 1. Inspect dead letters and check replay_blocked_by / replay_block_reason
curl -sS -H "Authorization: Bearer $UNS_API_KEY" \\
  "$UNS_BASE_URL/api/v1/runtime/dead-letters" | jq .

# 2A. If provider is restored AND replay_blocked_by == null -> Replay (starts Cycle N+1)
curl -sS -X POST -H "Authorization: Bearer $UNS_API_KEY" \\
  "$UNS_BASE_URL/api/v1/runtime/notifications/$NOTIF_ID/replay" | jq .

# 2B. If obligation was satisfied by a successor (replay_blocked_by != null) -> Resolve DLQ entry
curl -sS -X DELETE -H "Authorization: Bearer $UNS_API_KEY" \\
  "$UNS_BASE_URL/api/v1/dlq/$NOTIF_ID" | jq .`}
        </pre>
      </>
    ),
  },
  {
    id: 'runbook-tsg-02',
    sectionId: 'runbooks',
    title: 'TSG-02: Delivery Leases, Worker Crash Recovery & UNKNOWN SMTP Provider Effects',
    tag: 'TSG-02 · LEASES & SMTP',
    keywords:
      'TSG-02 Delivery Leases Worker Crash Recovery UNKNOWN SMTP Provider Effects LEASE_LOST CHANNEL_ATTEMPT_STARTED CHANNEL_ATTEMPT_RESULT provider_effect_may_have_occurred provider_outcome F-03 F-04a F-04b',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          <strong>Symptoms:</strong> Runtime events show <code>CHANNEL_ATTEMPT_STARTED</code>{' '}
          followed by <code>LEASE_LOST</code> (
          <code>provider_effect_may_have_occurred: true</code>), or an email attempt records{' '}
          <code>metadata.provider_outcome = &quot;UNKNOWN&quot;</code> after an SMTP post-admission
          timeout.
        </p>
        <p style={{ margin: 0 }}>
          <strong>Mechanics (<code>F-03</code> / <code>F-04a</code> / <code>F-04b</code>):</strong>{' '}
          Workers claim a 60-second fenced <code>lease_token</code>. Per-channel observations are
          persisted append-only via <code>CHANNEL_ATTEMPT_RESULT</code> even if the lease expires
          before aggregate settlement. <code>EmailAdapter</code> budgets socket timeouts against the
          remaining lease and never locally retries ambiguous post-admission SMTP timeouts.
        </p>
        <pre className="docs-code-block">
          {`# Inspect per-channel attempt observations and lease fencing events before replaying
curl -sS -H "Authorization: Bearer $UNS_API_KEY" \\
  "$UNS_BASE_URL/api/v1/runtime/notifications/$NOTIF_ID" \\
  | jq '.events[] | select(.kind == "CHANNEL_ATTEMPT_STARTED" or .kind == "CHANNEL_ATTEMPT_RESULT" or .kind == "LEASE_LOST")'

# If CHANNEL_ATTEMPT_RESULT shows "success": true, do NOT replay — resolve the DLQ flag instead:
curl -sS -X DELETE -H "Authorization: Bearer $UNS_API_KEY" "$UNS_BASE_URL/api/v1/dlq/$NOTIF_ID"`}
        </pre>
      </>
    ),
  },
  {
    id: 'runbook-tsg-03',
    sectionId: 'runbooks',
    title: 'TSG-03: Acknowledgment Timeouts, Escalations & Callback Retry Exhaustion',
    tag: 'TSG-03 · ACK & CALLBACKS',
    keywords:
      'TSG-03 Acknowledgment Timeouts Escalations Callback Retry Exhaustion TIMED_OUT uns-timeout-worker 409 Conflict 403 principal_override_forbidden callback_pending callback_attempts ix_uns_callbacks F-06',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          <strong>Symptoms:</strong> Responder ACK/Dismiss returns <code>409 Conflict</code> or{' '}
          <code>403 Forbidden</code> (<code>principal_override_forbidden</code>), notifications
          transition to <code>TIMED_OUT</code> via <code>uns-timeout-worker</code>, or embedded
          callbacks stop firing after <code>callback_attempts &gt;= 3</code>.
        </p>
        <p style={{ margin: 0 }}>
          <strong>Mechanics (<code>F-06</code>):</strong> <code>Runtime.expire()</code> sweeps
          overdue <code>PENDING</code> ACKs every 1s. Terminal transitions enqueue callbacks ordered
          by <code>(callback_until, at, id)</code> via <code>ix_uns_callbacks</code> with
          exponential backoff (<code>2 ** callback_attempts</code> seconds, max 3 attempts, 10s
          timeout).
        </p>
        <pre className="docs-code-block">
          {`# 1. Inspect current ACK status, actor, deadline, and response metadata
curl -sS -H "Authorization: Bearer $UNS_API_KEY" \\
  "$UNS_BASE_URL/api/v1/runtime/notifications/$NOTIF_ID" \\
  | jq '{id, status, ack_status, actor, delivered_at, deadline, responded_at, response_metadata}'

# 2. Re-enable exhausted terminal callbacks (callback_attempts >= 3) after restoring receiver
sqlite3 "$UNS_DB_FILE" "
  UPDATE uns_events
  SET callback_attempts = 0, callback_until = at, callback_token = NULL
  WHERE callback_pending = 1 AND callback_attempts >= 3;
"`}
        </pre>
      </>
    ),
  },
  {
    id: 'runbook-tsg-04',
    sectionId: 'runbooks',
    title: 'TSG-04: Policy Lifecycle, Revision Governance, Content Hashing & Override Rejections',
    tag: 'TSG-04 · POLICY AUTHORITY',
    keywords:
      'TSG-04 Policy Lifecycle Revision Governance Content Hashing Override Rejections POST /api/v1/policies/reload 409 422 RETIRED PolicyOverrideError slack_channel email_to pagerduty_severity websocket_user_id F-05',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          <strong>Symptoms:</strong> <code>POST /api/v1/policies/reload</code> fails with{' '}
          <code>409 Conflict</code> or <code>422 Unprocessable Entity</code>, or producer{' '}
          <code>POST /api/v1/notifications</code> fails with <code>422 PolicyOverrideError</code>.
        </p>
        <p style={{ margin: 0 }}>
          <strong>Mechanics (<code>F-05</code>):</strong> Active policies are stored in
          revision-locked snapshots (<code>notification_policy_snapshots</code>). Re-activating a
          previously <code>RETIRED</code> content hash returns <code>409 Conflict</code> until the
          YAML <code>version</code> is incremented. Producer requests cannot weaken{' '}
          <code>ACTIVE</code> policy fields or pass reserved adapter-steering keys (
          <code>slack_channel</code>, <code>email_to</code>, <code>pagerduty_severity</code>,{' '}
          <code>websocket_user_id</code>).
        </p>
        <pre className="docs-code-block">
          {`# 1. Inspect effective policy resolution & field trace
curl -sS -G -H "Authorization: Bearer $UNS_API_KEY" "$UNS_BASE_URL/ui/policies/effective" \\
  --data-urlencode "notification_type=safety.kill_switch" \\
  --data-urlencode "intent=SAFETY" \\
  --data-urlencode "autonomy_mode=LIVE" \\
  --data-urlencode "irreversible=true" | jq .

# 2. Reload YAML policy directory after bumping version on updated/re-enabled policies
curl -sS -X POST -H "Authorization: Bearer $UNS_API_KEY" -H "Content-Type: application/json" \\
  "$UNS_BASE_URL/api/v1/policies/reload" -d '{"policy_dir": "examples/policies/mip-uns"}' | jq .`}
        </pre>
      </>
    ),
  },
  {
    id: 'runbook-tsg-05',
    sectionId: 'runbooks',
    title: 'TSG-05: MCP Transport Safety & Agent WebSocket Recovery Workflows',
    tag: 'TSG-05 · MCP & WEBSOCKET',
    keywords:
      'TSG-05 MCP Transport Safety Agent Recovery Workflows uns-mcp --enable-writes UNS_DATABASE_URL UNS_API_PRINCIPAL UNS_MCP_DELIVERY_CONFIRMATION_TOKEN WS_1008_POLICY_VIOLATION 1008 UNS_ALLOWED_ORIGINS F-07',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          <strong>Symptoms:</strong> <code>uns-mcp --enable-writes</code> exits on startup,{' '}
          <code>send_signal(deliver=True)</code> raises <code>ValueError</code>, or browser/agent
          WebSocket connections close with code <code>1008</code> (
          <code>WS_1008_POLICY_VIOLATION</code>).
        </p>
        <p style={{ margin: 0 }}>
          <strong>Remediation (<code>F-07</code>):</strong> Ensure write-enabled MCP has a
          file-backed SQLite <code>UNS_DATABASE_URL</code>, non-empty{' '}
          <code>UNS_API_PRINCIPAL</code>, and <code>UNS_MCP_DELIVERY_CONFIRMATION_TOKEN</code>, and
          keep the long-lived <code>uns</code> service running so background retries continue if a
          short-lived stdio MCP session disconnects. For WebSocket <code>1008</code> errors, verify{' '}
          <code>UNS_ALLOWED_ORIGINS</code> and pass{' '}
          <code>Sec-WebSocket-Protocol: agsignal.v1, bearer.&lt;base64url_token&gt;</code>.
        </p>
        <pre className="docs-code-block">
          {`# Verify write-enabled MCP configuration before launching stdio host
python3 -c '
from agsignal_mcp.transports.stdio import runtime_config
cfg = runtime_config(enable_writes=True)
print("MCP Write Config Valid:", cfg.mode, "principal=", cfg.operator_principal)
'`}
        </pre>
      </>
    ),
  },
  {
    id: 'runbook-tsg-06',
    sectionId: 'runbooks',
    title: 'TSG-06: SQLite WAL Retention Maintenance (uns-maintain) & Verified Online Backups (uns-maintain-and-backup.sh)',
    tag: 'TSG-06 · MAINTENANCE & BACKUP',
    keywords:
      'TSG-06 SQLite WAL Retention Maintenance uns-maintain Verified Online Backups uns-maintain-and-backup.sh --archive FileExistsError oversized_notification_ids RETENTION_APPLIED PRAGMA quick_check F-08a F-08b',
    render: () => (
      <>
        <p style={{ margin: 0 }}>
          <strong>Symptoms:</strong> <code>uns-maintain --apply --archive</code> raises{' '}
          <code>FileExistsError</code>, reports <code>oversized_notification_ids</code>, or
          non-archive mode leaves <code>uns_events</code> / audit row counts unchanged.
        </p>
        <p style={{ margin: 0 }}>
          <strong>Mechanics (<code>F-08a</code> / <code>F-08b</code>):</strong> Without{' '}
          <code>--archive</code>, <code>uns-maintain --apply</code> expires settled operational rows
          from <code>uns_notifications</code> and <code>uns_dedup</code> while preserving audit
          history and embedding removed rows in a <code>RETENTION_APPLIED</code> receipt. With{' '}
          <code>--archive &lt;new-file.json&gt;</code>, it exclusively creates a mode{' '}
          <code>0600</code> archive file (<code>O_CREAT | O_EXCL</code>), <code>fsync</code>s and
          verifies its SHA-256 digest, prunes all 5 tables, and records a compact archive receipt.
          Pair retention runs with verified online SQLite backups (
          <code>uns-maintain-and-backup.sh</code> / <code>sqlite3 .backup</code> +{' '}
          <code>PRAGMA quick_check</code>).
        </p>
        <pre className="docs-code-block">
          {`# 1. Dry-run retention preview (no rows modified)
.venv/bin/uns-maintain --database-url "$UNS_DATABASE_URL" \\
  --cutoff "2026-10-01T00:00:00Z" --idempotency-seconds 86400 --batch-size 100 | jq .

# 2. Apply archived retention with a unique filename + verified online SQLite backup (uns-maintain-and-backup.sh pattern)
ARCHIVE_FILE="/var/backups/uns/archive-$(date -u +%Y%m%dT%H%M%SZ)-$(uuidgen | tr '[:upper:]' '[:lower:]').json"
.venv/bin/uns-maintain --database-url "$UNS_DATABASE_URL" \\
  --cutoff "2026-10-01T00:00:00Z" --idempotency-seconds 86400 --batch-size 500 \\
  --apply --operator "oncall-operator" --archive "$ARCHIVE_FILE"

BACKUP_FILE="/var/backups/uns/uns-$(date -u +%Y%m%dT%H%M%SZ).db"
sqlite3 "$UNS_DB_FILE" ".backup '$BACKUP_FILE'"
sqlite3 "$BACKUP_FILE" "PRAGMA quick_check;"`}
        </pre>
      </>
    ),
  },
];

export function DocsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState('');

  const selectedSection = parseSectionParam(searchParams.get('section'));
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const isSearching = normalizedQuery.length > 0;

  const handleSelectSection = (sectionId: DocsSectionId) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('section', sectionId);
    setSearchParams(nextParams, { replace: false });
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    if (value.trim().length > 0 && searchParams.get('section') !== 'all') {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set('section', 'all');
      setSearchParams(nextParams, { replace: true });
    }
  };

  const handleClearSearch = () => {
    setSearchQuery('');
  };

  const visibleSections = useMemo(() => {
    return SECTION_META.map((section) => {
      const sectionCards = DOCS_CARDS.filter((card) => {
        if (card.sectionId !== section.id) {
          return false;
        }
        if (!isSearching && selectedSection !== 'all' && selectedSection !== section.id) {
          return false;
        }
        if (!isSearching) {
          return true;
        }
        const haystack = `${section.heading} ${card.title} ${card.tag} ${card.keywords}`.toLowerCase();
        return haystack.includes(normalizedQuery);
      });
      return {
        section,
        cards: sectionCards,
      };
    }).filter((entry) => entry.cards.length > 0);
  }, [isSearching, normalizedQuery, selectedSection]);

  const totalMatchingCards = useMemo(
    () => visibleSections.reduce((acc, item) => acc + item.cards.length, 0),
    [visibleSections]
  );

  return (
    <div className="docs-page" data-testid="docs-page">
      {/* Architectural 2-Column Page Header */}
      <header className="page-header">
        <div>
          <h1>Documentation &amp; Runbooks</h1>
        </div>
        <p className="page-description">
          In-portal operator manual, Modernist badge visual grammar, state-machine reference,
          producer &amp; MCP integration guides, and TSG-01–06 incident runbooks.
        </p>
      </header>

      {/* Instant Keyword Search Bar */}
      <div className="docs-search-bar" role="search" aria-label="Documentation search">
        <div className="docs-search-cell">
          <label htmlFor="docs-search-input" className="field-label">
            Search Documentation &amp; Runbooks (All 5 Sections)
          </label>
          <input
            id="docs-search-input"
            data-testid="docs-search-input"
            type="text"
            className="modernist-input"
            placeholder="Filter by keyword, endpoint, event kind, or runbook (e.g., TSG-01, LEASE_LOST, BroadcastChannel, mip-uns)..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>
        <div className="docs-search-actions">
          <span
            className="monospace"
            style={{ fontSize: '12px', color: 'var(--color-neutral-700)', alignSelf: 'center' }}
            data-testid="docs-match-count"
          >
            {isSearching
              ? `${totalMatchingCards} matching topic${totalMatchingCards === 1 ? '' : 's'}`
              : `Section: ${selectedSection.toUpperCase()}`}
          </span>
          {isSearching && (
            <button
              type="button"
              className="btn btn-secondary"
              data-testid="docs-search-clear"
              onClick={handleClearSearch}
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Two-Column Split Layout: 260px Sticky Left Index + Main Documentation Reader */}
      <div className="docs-split-layout">
        <aside className="docs-nav-rail" aria-label="Documentation sections">
          <div className="docs-nav-sticky">
            <div className="docs-nav-header">Workspace Index</div>
            <ul className="docs-nav-list">
              {SECTION_META.map((sec) => {
                const isActive = !isSearching && selectedSection === sec.id;
                return (
                  <li key={sec.id} className="docs-nav-item">
                    <button
                      type="button"
                      data-testid={`docs-nav-${sec.id}`}
                      className={`docs-nav-btn ${isActive ? 'active' : ''}`}
                      aria-current={isActive ? 'true' : undefined}
                      onClick={() => {
                        if (isSearching) {
                          setSearchQuery('');
                        }
                        handleSelectSection(sec.id);
                      }}
                    >
                      <span>{sec.navLabel}</span>
                      <span className="docs-nav-btn-sub">{sec.navSubtitle}</span>
                    </button>
                  </li>
                );
              })}
              <li className="docs-nav-item">
                <button
                  type="button"
                  data-testid="docs-nav-all"
                  className={`docs-nav-btn ${
                    isSearching || selectedSection === 'all' ? 'active' : ''
                  }`}
                  aria-current={isSearching || selectedSection === 'all' ? 'true' : undefined}
                  onClick={() => {
                    if (isSearching) {
                      setSearchQuery('');
                    }
                    handleSelectSection('all');
                  }}
                >
                  <span>All Sections (Full Reference)</span>
                  <span className="docs-nav-btn-sub">View all 5 sections on one page</span>
                </button>
              </li>
            </ul>
          </div>
        </aside>

        {/* Main Documentation Reader */}
        <section className="docs-reader" aria-live="polite">
          {visibleSections.length === 0 ? (
            <div className="empty-state" data-testid="docs-empty-state">
              <p>
                No documentation topics or incident runbooks matched{' '}
                <code>{searchQuery.trim()}</code>.
              </p>
            </div>
          ) : (
            visibleSections.map(({ section, cards }) => (
              <div
                key={section.id}
                className="docs-section-block"
                data-testid={`docs-section-${section.id}`}
              >
                <div className="docs-section-header">
                  <div>
                    <h2>{section.heading}</h2>
                    <p
                      style={{
                        margin: '4px 0 0',
                        fontSize: '13px',
                        color: 'var(--color-neutral-700)',
                      }}
                    >
                      {section.summary}
                    </p>
                  </div>
                  <span className="badge badge-default">{section.id.toUpperCase()}</span>
                </div>

                <div className="docs-card-grid">
                  {cards.map((card) => (
                    <article
                      key={card.id}
                      className="docs-card"
                      data-testid={`docs-card-${card.id}`}
                    >
                      <div className="docs-card-header">
                        <h3>{card.title}</h3>
                        <span className="badge badge-default">{card.tag}</span>
                      </div>
                      {card.render()}
                    </article>
                  ))}
                </div>
              </div>
            ))
          )}
        </section>
      </div>
    </div>
  );
}

export default DocsPage;
