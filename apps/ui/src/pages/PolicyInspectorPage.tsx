/**
 * PolicyInspectorPage — Policy Workspace (/policy)
 *
 * Surface 4 of the UNS Console Responder & Operator Workflows specification:
 * - Active Policies Catalog table (GET /ui/policies/active) with one-click selection
 * - ?notification_type= deep-link auto-population and inspection
 * - Effective Policy Inspector & Resolution Trace (GET /ui/policies/effective)
 * - Dry-Run Simulator (POST /api/v1/notifications/simulate) & Tagged Live Test Sender
 *   (POST /api/v1/notifications with [TEST] prefix and source: "uns_console_policy_test")
 *   for producer / admin scopes
 * - Atomic Two-Phase Policy Reload (POST /api/v1/policies/reload with {}) for admin scope
 */

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Link, useInRouterContext, useLocation } from 'react-router-dom';
import {
  activateApprovedProposal,
  activateDraftRevision,
  approveProposalToDraft,
  createPolicyProposal,
  fetchActivePolicies,
  fetchPolicyProposalDetail,
  fetchPolicyProposals,
  fetchPolicyRevisions,
  promoteProposalToShadow,
  rejectPolicyProposal,
  reloadPolicies,
  sendTestNotification,
  simulateNotification,
} from '../api/policies';
import { getConsoleSession, hasScope, subscribeConsoleSession } from '../auth/session';
import {
  PolicyInspectorForm,
  type PolicyExternalSelection,
} from '../components/PolicyInspectorForm';
import { ResolutionTraceDisplay } from '../components/ResolutionTraceDisplay';
import { usePolicyInspector } from '../hooks/usePolicyInspector';
import type {
  ActivePolicySummary,
  AutonomyMode,
  DeltaState,
  NotificationIntent,
  PolicyInspectorParams,
  PolicyLifecycleStatus,
  PolicyPromotionResponse,
  PolicyProposalSummary,
  PolicyReloadResponsePayload,
  PolicyRevisionSummary,
  SendNotificationResponsePayload,
  SimulateNotificationResponsePayload,
} from '../types/api';

const DEFAULT_AGENT_ID = '00000000-0000-4000-8000-000000000001';

function getPolicyStatusBadgeClass(status: string): string {
  switch (status.toUpperCase()) {
    case 'ACTIVE':
    case 'APPLIED':
    case 'APPROVED':
    case 'PASSED':
      return 'badge tag-delivery-ok';
    case 'DRAFT':
    case 'PREVIEW':
    case 'SHADOW':
    case 'PROPOSED':
    case 'PENDING':
      return 'badge tag-delivery-pending';
    case 'REJECTED':
    case 'FAILED':
      return 'badge tag-delivery-failed';
    case 'RETIRED':
    default:
      return 'badge badge-default';
  }
}

function formatPolicyValue(val: unknown): string {
  if (val === null || val === undefined) {
    return 'null';
  }
  if (Array.isArray(val)) {
    return val.join(', ');
  }
  if (typeof val === 'object') {
    return JSON.stringify(val);
  }
  return String(val);
}

function resolveCatalogIntent(
  notificationType: string,
  activePolicies: ActivePolicySummary[],
  policyRevisions: PolicyRevisionSummary[]
): NotificationIntent | null {
  const activeMatch = activePolicies.find(
    (p) => p.notification_type === notificationType && p.intent !== null
  );
  if (activeMatch?.intent) {
    return activeMatch.intent;
  }
  const revisionMatch = policyRevisions.find(
    (r) => r.notification_type === notificationType && r.intent !== null
  );
  return revisionMatch?.intent ?? null;
}

function RouterQueryNotificationTypeSync({
  onSelectType,
}: {
  onSelectType: (notificationType: string) => void;
}) {
  const location = useLocation();
  const handledRef = useRef<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const raw = params.get('notification_type')?.trim() ?? null;
    if (raw && handledRef.current !== raw) {
      handledRef.current = raw;
      onSelectType(raw);
    }
  }, [location.search, onSelectType]);

  return null;
}

export function PolicyInspectorPage() {
  const inRouter = useInRouterContext();
  const session = useSyncExternalStore(subscribeConsoleSession, getConsoleSession);
  const canProduce = hasScope(session, 'producer');
  const isAdmin = hasScope(session, 'admin');

  const { result, loading, error, inspect, clear } = usePolicyInspector();

  // Active policy catalog, revision history, & proposals state
  const [activePolicies, setActivePolicies] = useState<ActivePolicySummary[]>([]);
  const [policyRevisions, setPolicyRevisions] = useState<PolicyRevisionSummary[]>([]);
  const [proposals, setProposals] = useState<PolicyProposalSummary[]>([]);
  const [selectedProposalDetail, setSelectedProposalDetail] =
    useState<PolicyProposalSummary | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [revisionsError, setRevisionsError] = useState<string | null>(null);
  const [proposalsError, setProposalsError] = useState<string | null>(null);
  const [catalogView, setCatalogView] = useState<
    'all' | 'active' | 'revisions' | 'proposals'
  >('all');
  const [revisionStatusFilter, setRevisionStatusFilter] = useState<
    'ALL' | PolicyLifecycleStatus
  >('ALL');
  const [proposalStateFilter, setProposalStateFilter] = useState<'ALL' | DeltaState>('ALL');

  // Proposal creation & action state
  const [propPolicyType, setPropPolicyType] = useState('');
  const [propFieldPath, setPropFieldPath] = useState('channels');
  const [propProposedValue, setPropProposedValue] = useState('SLACK, PAGERDUTY');
  const [propReasoning, setPropReasoning] = useState(
    'Add PagerDuty channel for operational redundancy.'
  );
  const [propPromoteShadow, setPropPromoteShadow] = useState(true);
  const [proposalSubmitting, setProposalSubmitting] = useState(false);
  const [proposalActionBusyId, setProposalActionBusyId] = useState<string | null>(null);
  const [promotionBanner, setPromotionBanner] = useState<PolicyPromotionResponse | null>(
    null
  );
  const [proposalActionError, setProposalActionError] = useState<string | null>(null);

  // External selection sync for PolicyInspectorForm
  const [externalSelection, setExternalSelection] =
    useState<PolicyExternalSelection | null>(null);
  const selectionSeqRef = useRef(0);
  const pendingQueryTypeRef = useRef<{
    type: string;
    resolvedIntent: NotificationIntent | null;
  } | null>(null);

  // Simulator & Test Sender state
  const [simNotificationType, setSimNotificationType] = useState('');
  const [simIntent, setSimIntent] = useState<NotificationIntent>('OPERATIONAL');
  const [simAutonomyMode, setSimAutonomyMode] = useState<AutonomyMode>('LIVE');
  const [simIrreversible, setSimIrreversible] = useState(false);
  const [simTitle, setSimTitle] = useState('Policy routing verification');
  const [simMessage, setSimMessage] = useState(
    'Verifying channel routing and acknowledgment policy from UNS Console.'
  );
  const [simSource, setSimSource] = useState('uns-console');
  const [simAgentId, setSimAgentId] = useState(DEFAULT_AGENT_ID);

  const [simulating, setSimulating] = useState(false);
  const [simulationResult, setSimulationResult] =
    useState<SimulateNotificationResponsePayload | null>(null);
  const [confirmingTestSend, setConfirmingTestSend] = useState(false);
  const [sendingTest, setSendingTest] = useState(false);
  const [testSendResult, setTestSendResult] =
    useState<SendNotificationResponsePayload | null>(null);
  const [simulatorError, setSimulatorError] = useState<string | null>(null);

  // Admin Policy Reload state
  const [confirmingReload, setConfirmingReload] = useState(false);
  const [reloadingPolicies, setReloadingPolicies] = useState(false);
  const [reloadResult, setReloadResult] = useState<PolicyReloadResponsePayload | null>(
    null
  );
  const [reloadError, setReloadError] = useState<string | null>(null);

  const loadCatalog = useCallback(async () => {
    const hasActiveLoader = typeof fetchActivePolicies === 'function';
    const hasRevisionsLoader = typeof fetchPolicyRevisions === 'function';
    const hasProposalsLoader = typeof fetchPolicyProposals === 'function';
    if (!hasActiveLoader && !hasRevisionsLoader && !hasProposalsLoader) return;

    setCatalogLoading(true);
    setCatalogError(null);
    setRevisionsError(null);
    setProposalsError(null);

    try {
      if (hasActiveLoader) {
        const response = await fetchActivePolicies();
        if (response && Array.isArray(response.items)) {
          setActivePolicies(response.items);
        }
      }
    } catch (err) {
      setCatalogError(
        err instanceof Error ? err.message : 'Unable to load active policies.'
      );
    }

    try {
      if (hasRevisionsLoader) {
        const revisionsResponse = await fetchPolicyRevisions();
        if (revisionsResponse && Array.isArray(revisionsResponse.items)) {
          setPolicyRevisions(revisionsResponse.items);
        }
      }
    } catch (err) {
      setRevisionsError(
        err instanceof Error ? err.message : 'Unable to load policy revisions.'
      );
    }

    try {
      if (hasProposalsLoader) {
        const proposalsResponse = await fetchPolicyProposals();
        if (proposalsResponse && Array.isArray(proposalsResponse.items)) {
          setProposals(proposalsResponse.items);
        }
      }
    } catch (err) {
      setProposalsError(
        err instanceof Error ? err.message : 'Unable to load policy proposals.'
      );
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  const applyPolicySelection = useCallback(
    (
      notificationType: string,
      intent: NotificationIntent = 'OPERATIONAL',
      autonomyMode: AutonomyMode = 'LIVE'
    ) => {
      selectionSeqRef.current += 1;
      setExternalSelection({
        notification_type: notificationType,
        intent,
        autonomy_mode: autonomyMode,
        seq: selectionSeqRef.current,
      });
      setSimNotificationType(notificationType);
      setSimIntent(intent);
      setSimAutonomyMode(autonomyMode);
      setSimIrreversible(false);
      setSimulationResult(null);
      setTestSendResult(null);
      setSimulatorError(null);
      void inspect({
        notification_type: notificationType,
        intent,
        autonomy_mode: autonomyMode,
        irreversible: false,
      });
    },
    [inspect]
  );

  const handleQueryTypeSelect = useCallback(
    (notificationType: string) => {
      const matchedIntent = resolveCatalogIntent(
        notificationType,
        activePolicies,
        policyRevisions
      );
      pendingQueryTypeRef.current = {
        type: notificationType,
        resolvedIntent: matchedIntent,
      };
      applyPolicySelection(notificationType, matchedIntent ?? 'OPERATIONAL', 'LIVE');
    },
    [activePolicies, applyPolicySelection, policyRevisions]
  );

  useEffect(() => {
    const pending = pendingQueryTypeRef.current;
    if (!pending || pending.resolvedIntent !== null) return;
    const matchedIntent = resolveCatalogIntent(
      pending.type,
      activePolicies,
      policyRevisions
    );
    if (matchedIntent !== null) {
      pendingQueryTypeRef.current = {
        type: pending.type,
        resolvedIntent: matchedIntent,
      };
      if (matchedIntent !== 'OPERATIONAL') {
        applyPolicySelection(pending.type, matchedIntent, 'LIVE');
      }
    }
  }, [activePolicies, applyPolicySelection, policyRevisions]);

  const handleInspect = (params: PolicyInspectorParams) => {
    pendingQueryTypeRef.current = null;
    setSimNotificationType(params.notification_type);
    setSimIntent(params.intent);
    setSimAutonomyMode(params.autonomy_mode);
    setSimIrreversible(Boolean(params.irreversible));
    void inspect(params);
  };

  const handleClear = () => {
    pendingQueryTypeRef.current = null;
    clear();
  };

  async function handleSimulate() {
    const trimmedType = simNotificationType.trim();
    if (!trimmedType) {
      setSimulatorError('Notification type is required for simulation.');
      return;
    }
    setSimulating(true);
    setSimulatorError(null);
    setSimulationResult(null);
    setTestSendResult(null);

    try {
      const response = await simulateNotification({
        notification_type: trimmedType,
        intent: simIntent,
        title: simTitle.trim() || 'Policy simulation preview',
        message: simMessage.trim() || 'Dry-run simulation from UNS Console.',
        source: simSource.trim() || 'uns-console',
        autonomy_context: {
          autonomy_mode: simAutonomyMode,
          agent_id: simAgentId.trim() || DEFAULT_AGENT_ID,
        },
        irreversible: simIrreversible,
      });
      setSimulationResult(response);
    } catch (err) {
      setSimulatorError(
        err instanceof Error ? err.message : 'Simulation request failed.'
      );
    } finally {
      setSimulating(false);
    }
  }

  async function handleConfirmTestSend() {
    const trimmedType = simNotificationType.trim();
    if (!trimmedType || sendingTest) return;
    setSendingTest(true);
    setSimulatorError(null);
    setTestSendResult(null);
    setSimulationResult(null);

    const rawTitle = simTitle.trim() || 'Policy verification';
    const taggedTitle = rawTitle.startsWith('[TEST]') ? rawTitle : `[TEST] ${rawTitle}`;
    const effectiveTestSource =
      !simSource.trim() || simSource.trim() === 'uns-console'
        ? 'uns-console-policy-test'
        : simSource.trim();

    try {
      const response = await sendTestNotification({
        notification_type: trimmedType,
        intent: simIntent,
        title: taggedTitle,
        message: simMessage.trim() || 'Live policy test notification from UNS Console.',
        source: effectiveTestSource,
        autonomy_context: {
          autonomy_mode: simAutonomyMode,
          agent_id: simAgentId.trim() || DEFAULT_AGENT_ID,
        },
        irreversible: simIrreversible,
        metadata: {
          source: 'uns_console_policy_test',
          triggered_by: session.subject ?? 'console_operator',
        },
      });
      setConfirmingTestSend(false);
      setTestSendResult(response);
    } catch (err) {
      setSimulatorError(
        err instanceof Error ? err.message : 'Live test notification dispatch failed.'
      );
    } finally {
      setSendingTest(false);
    }
  }

  async function handleConfirmReload() {
    if (reloadingPolicies) return;
    setReloadingPolicies(true);
    setReloadError(null);
    setReloadResult(null);

    try {
      const response = await reloadPolicies();
      setConfirmingReload(false);
      setReloadResult(response);
      await loadCatalog();
    } catch (err) {
      setReloadError(
        err instanceof Error ? err.message : 'Failed to reload policies from server.'
      );
    } finally {
      setReloadingPolicies(false);
    }
  }

  function parseProposedValueInput(fieldPath: string, raw: string): unknown {
    const trimmed = raw.trim();
    if (fieldPath === 'channels' || fieldPath.endsWith('.channels')) {
      return trimmed
        .split(',')
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
    }
    if (fieldPath === 'require_ack' || fieldPath.endsWith('.require_ack')) {
      return trimmed.toLowerCase() === 'true' || trimmed === '1';
    }
    if (
      fieldPath === 'dedup_window_seconds' ||
      fieldPath === 'ack_timeout_minutes' ||
      fieldPath.endsWith('.ack_timeout_minutes') ||
      fieldPath === 'priority_override'
    ) {
      if (trimmed === '' || trimmed.toLowerCase() === 'null') {
        return null;
      }
      const parsed = Number(trimmed);
      return Number.isNaN(parsed) ? trimmed : parsed;
    }
    return trimmed;
  }

  async function handleCreateProposal() {
    const trimmedType = propPolicyType.trim() || simNotificationType.trim();
    if (!trimmedType) {
      setProposalActionError('Policy type (notification_type) is required to submit a proposal.');
      return;
    }
    if (!propReasoning.trim()) {
      setProposalActionError('Reasoning is required for governed policy proposals.');
      return;
    }
    if (typeof createPolicyProposal !== 'function') return;

    setProposalSubmitting(true);
    setProposalActionError(null);
    setPromotionBanner(null);

    try {
      const created = await createPolicyProposal({
        policy_type: trimmedType,
        field_path: propFieldPath,
        proposed_value: parseProposedValueInput(propFieldPath, propProposedValue),
        reasoning: propReasoning.trim(),
        confidence: 0.9,
        evidence_count: 1,
        promote_to_shadow: propPromoteShadow,
      });
      setSelectedProposalDetail(created);
      await loadCatalog();
    } catch (err) {
      setProposalActionError(
        err instanceof Error ? err.message : 'Failed to create policy proposal.'
      );
    } finally {
      setProposalSubmitting(false);
    }
  }

  async function handleInspectProposal(deltaId: string) {
    if (typeof fetchPolicyProposalDetail !== 'function') {
      const localMatch = proposals.find((p) => p.delta_id === deltaId) ?? null;
      setSelectedProposalDetail(localMatch);
      return;
    }
    setProposalActionBusyId(deltaId);
    setProposalActionError(null);
    try {
      const detail = await fetchPolicyProposalDetail(deltaId);
      setSelectedProposalDetail(detail);
    } catch (err) {
      setProposalActionError(
        err instanceof Error ? err.message : 'Unable to load proposal shadow evidence.'
      );
    } finally {
      setProposalActionBusyId(null);
    }
  }

  async function handlePromoteShadow(deltaId: string) {
    if (typeof promoteProposalToShadow !== 'function') return;
    setProposalActionBusyId(deltaId);
    setProposalActionError(null);
    setPromotionBanner(null);
    try {
      const updated = await promoteProposalToShadow(
        deltaId,
        'Promoted to SHADOW from UNS Console'
      );
      setSelectedProposalDetail(updated);
      await loadCatalog();
    } catch (err) {
      setProposalActionError(
        err instanceof Error ? err.message : 'Failed to promote proposal to SHADOW.'
      );
    } finally {
      setProposalActionBusyId(null);
    }
  }

  async function handleApproveToDraft(deltaId: string) {
    if (typeof approveProposalToDraft !== 'function') return;
    setProposalActionBusyId(deltaId);
    setProposalActionError(null);
    setPromotionBanner(null);
    try {
      const res = await approveProposalToDraft(
        deltaId,
        'Approved into DRAFT after shadow evidence verification'
      );
      setPromotionBanner(res);
      if (res.delta) {
        setSelectedProposalDetail(res.delta);
      }
      await loadCatalog();
    } catch (err) {
      setProposalActionError(
        err instanceof Error ? err.message : 'Failed to approve proposal into DRAFT.'
      );
    } finally {
      setProposalActionBusyId(null);
    }
  }

  async function handleActivateProposal(deltaId: string) {
    if (typeof activateApprovedProposal !== 'function') return;
    setProposalActionBusyId(deltaId);
    setProposalActionError(null);
    setPromotionBanner(null);
    try {
      const res = await activateApprovedProposal(
        deltaId,
        'Explicit operator activation DRAFT -> ACTIVE from UNS Console'
      );
      setPromotionBanner(res);
      if (res.delta) {
        setSelectedProposalDetail(res.delta);
      }
      await loadCatalog();
    } catch (err) {
      setProposalActionError(
        err instanceof Error ? err.message : 'Failed to activate DRAFT policy revision.'
      );
    } finally {
      setProposalActionBusyId(null);
    }
  }

  async function handleRejectProposal(deltaId: string) {
    if (typeof rejectPolicyProposal !== 'function') return;
    setProposalActionBusyId(deltaId);
    setProposalActionError(null);
    setPromotionBanner(null);
    try {
      const updated = await rejectPolicyProposal(
        deltaId,
        'Rejected by operator in UNS Console'
      );
      setSelectedProposalDetail(updated);
      await loadCatalog();
    } catch (err) {
      setProposalActionError(
        err instanceof Error ? err.message : 'Failed to reject policy proposal.'
      );
    } finally {
      setProposalActionBusyId(null);
    }
  }

  async function handleActivateRevision(policyId: string) {
    if (typeof activateDraftRevision !== 'function') return;
    setProposalActionBusyId(policyId);
    setProposalActionError(null);
    setPromotionBanner(null);
    try {
      const res = await activateDraftRevision(
        policyId,
        'Explicit operator activation DRAFT -> ACTIVE from Revision History'
      );
      setPromotionBanner(res);
      if (res.delta) {
        setSelectedProposalDetail(res.delta);
      }
      await loadCatalog();
    } catch (err) {
      setProposalActionError(
        err instanceof Error ? err.message : 'Failed to activate DRAFT revision.'
      );
    } finally {
      setProposalActionBusyId(null);
    }
  }

  return (
    <div className="policy-inspector-page" data-testid="policy-inspector-page">
      {inRouter && <RouterQueryNotificationTypeSync onSelectType={handleQueryTypeSelect} />}
      {/* Page Header */}
      <header className="page-header">
        <div>
          <h1>Policy Inspector</h1>
        </div>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-start',
            gap: '12px',
          }}
        >
          <p className="page-description">
            View effective policy values and resolution trace for any notification type.
            All data is read-only.
          </p>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            {inRouter ? (
              <Link
                to="/docs?section=runbooks&q=TSG-04"
                className="btn btn-secondary"
                data-testid="policy-runbook-link"
              >
                Runbook: TSG-04 →
              </Link>
            ) : (
              <a
                href="/docs?section=runbooks&q=TSG-04"
                className="btn btn-secondary"
                data-testid="policy-runbook-link"
              >
                Runbook: TSG-04 →
              </a>
            )}

            {/* Admin Operator Policy Reload Bar */}
            {isAdmin && (
              <div
                className="policy-reload-bar"
                data-testid="policy-reload-bar"
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}
              >
                {!confirmingReload ? (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setConfirmingReload(true)}
                    disabled={reloadingPolicies}
                    data-testid="initiate-policy-reload-btn"
                  >
                    Reload Policies from Server Directory
                  </button>
                ) : (
                  <div
                    data-testid="policy-reload-confirm-panel"
                    style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}
                  >
                    <span style={{ fontSize: '12px', fontWeight: 600 }}>
                      Validate and reload YAML policies from configured server directory?
                    </span>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void handleConfirmReload()}
                      disabled={reloadingPolicies}
                      data-testid="confirm-policy-reload-btn"
                    >
                      {reloadingPolicies ? 'Reloading…' : 'Confirm Reload'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => setConfirmingReload(false)}
                      disabled={reloadingPolicies}
                      data-testid="cancel-policy-reload-btn"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      {reloadResult && (
        <div
          role="status"
          data-testid="policy-reload-result"
          style={{
            padding: '12px 24px',
            borderBottom: '2px solid var(--color-divider)',
            backgroundColor: 'var(--color-surface)',
          }}
        >
          <strong>Policies reloaded atomically:</strong> {reloadResult.loaded_count} loaded,{' '}
          {reloadResult.persisted_count} persisted, {reloadResult.policy_count} active (
          {reloadResult.notification_types.join(', ') || 'none'}).
        </div>
      )}

      {reloadError && (
        <div
          role="alert"
          data-testid="policy-reload-error"
          style={{
            padding: '12px 24px',
            borderBottom: '2px solid var(--color-accent)',
            backgroundColor: 'var(--color-accent-100)',
            color: 'var(--color-accent-800)',
          }}
        >
          Policy reload failed: {reloadError}
        </div>
      )}

      {/* Two-Column Split Layout (1b: Query Pane on Left, Resolution Trace / Poster on Right) */}
      <section className="policy-split-layout">
        <div className="policy-query-pane">
          <PolicyInspectorForm
            onInspect={handleInspect}
            onClear={handleClear}
            loading={loading}
            externalSelection={externalSelection}
          />
        </div>

        <div className="policy-trace-pane">
          {/* Loading State */}
          {loading && (
            <div className="loading-state" data-testid="loading-state">
              <p>Resolving policy...</p>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="error-state" data-testid="error-state">
              <div className="error-message">
                <strong>Error resolving policy</strong>
                <p>{error.message}</p>
                {error.code && <p className="error-code">Code: {error.code}</p>}
                {error.requestId && <p className="error-request-id">Request ID: {error.requestId}</p>}
              </div>
            </div>
          )}

          {/* Results */}
          {result && !loading && !error && <ResolutionTraceDisplay response={result} />}

          {/* Empty State Poster (1b) */}
          {!result && !loading && !error && (
            <div className="policy-empty-poster" data-testid="empty-state">
              <div className="policy-empty-eyebrow">Resolution Trace — Awaiting Query</div>
              <p className="policy-empty-statement">
                Enter a notification type and click "Inspect Policy" to view resolution details.
              </p>
              <div className="policy-precedence-grid">
                <div>
                  <strong>01. Type Match</strong>
                  Exact notification_type or wildcard domain fallback.
                </div>
                <div>
                  <strong>02. Mode Override</strong>
                  PREVIEW / SHADOW channel clamping &amp; suppression rules.
                </div>
                <div>
                  <strong>03. Guardrail Floor</strong>
                  Irreversible &amp; SAFETY intent minimum delivery guarantees.
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Catalog / Revision Governance View Bar when policies, revisions, or proposals exist */}
      {(activePolicies.length > 0 ||
        policyRevisions.length > 0 ||
        proposals.length > 0 ||
        canProduce ||
        isAdmin) && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 24px',
            background: 'var(--color-surface)',
            borderBottom: '1px solid var(--color-divider)',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-heading)',
              fontSize: '11px',
              fontWeight: 800,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'var(--color-neutral-700)',
            }}
          >
            Policy Governance Workspace
          </span>
          <div className="seg" role="group" aria-label="Policy catalog view" data-testid="policy-catalog-view-toggle">
            <button
              type="button"
              className={`seg-opt ${catalogView === 'all' ? 'active' : ''}`}
              onClick={() => setCatalogView('all')}
              data-testid="policy-view-all-btn"
            >
              All Views
            </button>
            <button
              type="button"
              className={`seg-opt ${catalogView === 'active' ? 'active' : ''}`}
              onClick={() => setCatalogView('active')}
              data-testid="policy-view-active-btn"
            >
              Active Catalog ({activePolicies.length})
            </button>
            <button
              type="button"
              className={`seg-opt ${catalogView === 'revisions' ? 'active' : ''}`}
              onClick={() => setCatalogView('revisions')}
              data-testid="policy-view-revisions-btn"
            >
              Revision History &amp; Lineage ({policyRevisions.length})
            </button>
            <button
              type="button"
              className={`seg-opt ${catalogView === 'proposals' ? 'active' : ''}`}
              onClick={() => setCatalogView('proposals')}
              data-testid="policy-view-proposals-btn"
            >
              Proposals &amp; Shadow Evidence ({proposals.length})
            </button>
          </div>
        </div>
      )}

      {/* Active Policies Catalog Table */}
      {activePolicies.length > 0 &&
        catalogView !== 'revisions' &&
        catalogView !== 'proposals' && (
        <section
          data-testid="active-policies-section"
          style={{ borderBottom: '2px solid var(--color-divider)' }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '16px 24px',
              background: 'var(--color-surface)',
              borderBottom: '1px solid var(--color-divider)',
            }}
          >
            <h2 style={{ margin: 0, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Active Policies Catalog ({activePolicies.length})
            </h2>
            <span style={{ fontSize: '12px', color: 'var(--color-neutral-700)' }}>
              Click any policy row to populate the Inspector and Simulator
            </span>
          </div>
          {catalogError && <p className="field-error" style={{ padding: '0 24px' }}>{catalogError}</p>}
          <div className="table-container">
            <table className="data-table" data-testid="active-policies-table">
              <thead>
                <tr>
                  <th>Notification Type</th>
                  <th>Default Intent</th>
                  <th>LIVE Channels</th>
                  <th>Delivery Mode</th>
                  <th>Require ACK</th>
                  <th>ACK Timeout</th>
                  <th>Dedup Window</th>
                </tr>
              </thead>
              <tbody>
                {activePolicies.map((policy) => (
                  <tr
                    key={policy.notification_type}
                    onClick={() => {
                      pendingQueryTypeRef.current = null;
                      applyPolicySelection(
                        policy.notification_type,
                        policy.intent ?? 'OPERATIONAL',
                        'LIVE'
                      );
                    }}
                    style={{ cursor: 'pointer' }}
                    data-testid={`active-policy-row-${policy.notification_type}`}
                  >
                    <td className="monospace">
                      <strong>{policy.notification_type}</strong>
                    </td>
                    <td>{policy.intent ?? 'SDK Default'}</td>
                    <td>{policy.channels.join(', ') || 'SDK Default'}</td>
                    <td>{policy.delivery_mode ?? 'SDK Default'}</td>
                    <td>
                      {policy.require_ack === null
                        ? 'SDK Default'
                        : policy.require_ack
                          ? 'Yes'
                          : 'No'}
                    </td>
                    <td className="timestamp">
                      {policy.ack_timeout_seconds !== null
                        ? `${policy.ack_timeout_seconds}s`
                        : '-'}
                    </td>
                    <td className="timestamp">{policy.dedup_window_seconds}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Policy Revision History & Lineage Table */}
      {(policyRevisions.length > 0 || catalogView === 'revisions') &&
        catalogView !== 'active' &&
        catalogView !== 'proposals' && (
          <section
            data-testid="policy-revisions-section"
            style={{ borderBottom: '2px solid var(--color-divider)' }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '16px 24px',
                background: 'var(--color-surface)',
                borderBottom: '1px solid var(--color-divider)',
                gap: '12px',
                flexWrap: 'wrap',
              }}
            >
              <div>
                <h2
                  style={{
                    margin: 0,
                    fontSize: '14px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                  }}
                >
                  Policy Revision History &amp; Lineage ({policyRevisions.length})
                </h2>
                <span style={{ fontSize: '12px', color: 'var(--color-neutral-700)' }}>
                  Inspect ACTIVE, PREVIEW, DRAFT, and RETIRED revisions — click any row to load into Inspector &amp; Simulator
                </span>
              </div>

              <div
                className="seg"
                role="group"
                aria-label="Filter revisions by lifecycle status"
                data-testid="policy-revision-status-filter"
              >
                {(['ALL', 'ACTIVE', 'PREVIEW', 'DRAFT', 'RETIRED'] as const).map(
                  (statusOpt) => (
                    <button
                      key={statusOpt}
                      type="button"
                      className={`seg-opt ${
                        revisionStatusFilter === statusOpt ? 'active' : ''
                      }`}
                      onClick={() => setRevisionStatusFilter(statusOpt)}
                      data-testid={`policy-status-filter-${statusOpt}`}
                    >
                      {statusOpt}
                    </button>
                  )
                )}
              </div>
            </div>

            {revisionsError && (
              <p className="field-error" style={{ padding: '0 24px' }}>
                {revisionsError}
              </p>
            )}

            <div className="table-container">
              <table className="data-table" data-testid="policy-revisions-table">
                <thead>
                  <tr>
                    <th>Notification Type</th>
                    <th>Version</th>
                    <th>Status</th>
                    <th>Lineage</th>
                    <th>Config Hash</th>
                    <th>Default Intent</th>
                    <th>Routing Channels</th>
                    <th>Delivery Mode</th>
                    <th>Require ACK</th>
                    <th>Dedup Window</th>
                  </tr>
                </thead>
                <tbody>
                  {policyRevisions
                    .filter(
                      (rev) =>
                        revisionStatusFilter === 'ALL' ||
                        rev.status.toUpperCase() === revisionStatusFilter
                    )
                    .map((rev) => (
                      <tr
                        key={`${rev.notification_type}-${rev.version}-${rev.status}-${rev.config_hash ?? ''}`}
                        onClick={() => {
                          pendingQueryTypeRef.current = null;
                          applyPolicySelection(
                            rev.notification_type,
                            rev.intent ?? 'OPERATIONAL',
                            'LIVE'
                          );
                        }}
                        style={{ cursor: 'pointer' }}
                        data-testid={`policy-revision-row-${rev.notification_type}-${rev.version}`}
                      >
                        <td className="monospace">
                          <strong>{rev.notification_type}</strong>
                        </td>
                        <td className="monospace">{rev.version}</td>
                        <td>
                          <span
                            className={getPolicyStatusBadgeClass(rev.status)}
                            data-testid={`policy-revision-status-${rev.notification_type}-${rev.version}`}
                          >
                            {rev.status}
                          </span>
                        </td>
                        <td
                          className="monospace"
                          title={rev.previous_version_id ?? 'Root revision'}
                          data-testid={`policy-revision-lineage-${rev.notification_type}-${rev.version}`}
                        >
                          {rev.previous_version_id
                            ? `Supersedes: ${rev.previous_version_id.slice(0, 8)}...`
                            : 'ROOT'}
                        </td>
                        <td
                          className="monospace"
                          title={rev.config_hash ?? undefined}
                        >
                          {rev.config_hash ? rev.config_hash.slice(0, 12) : '-'}
                        </td>
                        <td>{rev.intent ?? 'SDK Default'}</td>
                        <td>{rev.channels.join(', ') || 'SDK Default'}</td>
                        <td>{rev.delivery_mode ?? 'SDK Default'}</td>
                        <td>
                          {rev.require_ack === null
                            ? 'SDK Default'
                            : rev.require_ack
                              ? 'Yes'
                              : 'No'}
                        </td>
                        <td className="timestamp">
                          {rev.dedup_window_seconds}s
                          {isAdmin &&
                            rev.status.toUpperCase() === 'DRAFT' &&
                            rev.policy_id && (
                              <button
                                type="button"
                                className="btn btn-primary"
                                style={{ marginLeft: '8px', padding: '2px 8px', fontSize: '11px' }}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (rev.policy_id) {
                                    void handleActivateRevision(rev.policy_id);
                                  }
                                }}
                                disabled={proposalActionBusyId === rev.policy_id}
                                data-testid={`activate-revision-btn-${rev.notification_type}-${rev.version}`}
                              >
                                Activate DRAFT &rarr; ACTIVE
                              </button>
                            )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

      {/* Governed Policy Proposals & Shadow Evidence Workspace (Milestone v0.5.0 / Issue #47) */}
      {(proposals.length > 0 ||
        catalogView === 'proposals' ||
        canProduce ||
        isAdmin) &&
        catalogView !== 'active' &&
        catalogView !== 'revisions' && (
          <section
            data-testid="policy-proposals-section"
            style={{ borderBottom: '2px solid var(--color-divider)' }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '16px 24px',
                background: 'var(--color-surface)',
                borderBottom: '1px solid var(--color-divider)',
                gap: '12px',
                flexWrap: 'wrap',
              }}
            >
              <div>
                <h2
                  style={{
                    margin: 0,
                    fontSize: '14px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                  }}
                >
                  Proposals &amp; Shadow Evidence ({proposals.length})
                </h2>
                <span style={{ fontSize: '12px', color: 'var(--color-neutral-700)' }}>
                  Proposal &rarr; Shadow Evidence (PREVIEW) &rarr; Guard Check &rarr; Approved DRAFT &rarr; Explicit Activation
                </span>
              </div>

              <div
                className="seg"
                role="group"
                aria-label="Filter proposals by lifecycle state"
                data-testid="policy-proposal-state-filter"
              >
                {(['ALL', 'PROPOSED', 'SHADOW', 'APPROVED', 'APPLIED', 'REJECTED'] as const).map(
                  (stateOpt) => (
                    <button
                      key={stateOpt}
                      type="button"
                      className={`seg-opt ${
                        proposalStateFilter === stateOpt ? 'active' : ''
                      }`}
                      onClick={() => setProposalStateFilter(stateOpt)}
                      data-testid={`policy-proposal-filter-${stateOpt}`}
                    >
                      {stateOpt}
                    </button>
                  )
                )}
              </div>
            </div>

            {promotionBanner && (
              <div
                role="status"
                data-testid="policy-promotion-banner"
                style={{
                  padding: '12px 24px',
                  borderBottom: '1px solid var(--color-divider)',
                  backgroundColor: 'var(--color-surface)',
                }}
              >
                <strong>{promotionBanner.message}</strong> — Revision{' '}
                <span className="monospace">v{promotionBanner.version}</span> (
                <span className="monospace">{promotionBanner.status}</span>, hash{' '}
                <span className="monospace">
                  {promotionBanner.config_hash.slice(0, 12)}
                </span>
                )
              </div>
            )}

            {(proposalsError || proposalActionError) && (
              <div
                role="alert"
                data-testid="policy-proposal-error"
                style={{
                  padding: '10px 24px',
                  borderBottom: '1px solid var(--color-accent)',
                  backgroundColor: 'var(--color-accent-100)',
                  color: 'var(--color-accent-800)',
                }}
              >
                {proposalActionError ?? proposalsError}
              </div>
            )}

            {/* Propose PolicyDelta Form for Producer / Admin */}
            {(canProduce || isAdmin) && (
              <div
                data-testid="propose-delta-form"
                style={{
                  padding: '16px 24px',
                  borderBottom: '1px solid var(--color-divider)',
                  backgroundColor: 'var(--color-bg)',
                }}
              >
                <div
                  style={{
                    fontSize: '12px',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    marginBottom: '10px',
                  }}
                >
                  Propose Governed Policy Delta
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
                    gap: '10px',
                    marginBottom: '10px',
                  }}
                >
                  <div>
                    <label
                      htmlFor="proposal-policy-type"
                      className="field-label"
                      style={{ display: 'block', marginBottom: '4px' }}
                    >
                      Target Notification Type
                    </label>
                    <input
                      id="proposal-policy-type"
                      type="text"
                      className="modernist-input monospace"
                      value={propPolicyType}
                      onChange={(e) => setPropPolicyType(e.target.value)}
                      placeholder={simNotificationType || 'e.g., trading.order_placed'}
                      data-testid="proposal-policy-type-input"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="proposal-field-path"
                      className="field-label"
                      style={{ display: 'block', marginBottom: '4px' }}
                    >
                      Policy Field
                    </label>
                    <select
                      id="proposal-field-path"
                      className="modernist-select monospace"
                      value={propFieldPath}
                      onChange={(e) => setPropFieldPath(e.target.value)}
                      data-testid="proposal-field-path-select"
                    >
                      <option value="channels">channels</option>
                      <option value="dedup_window_seconds">dedup_window_seconds</option>
                      <option value="ack_timeout_minutes">ack_timeout_minutes</option>
                      <option value="require_ack">require_ack</option>
                      <option value="delivery_mode">delivery_mode</option>
                      <option value="intent">intent</option>
                      <option value="mode_overrides.LIVE.channels">
                        mode_overrides.LIVE.channels
                      </option>
                      <option value="mode_overrides.LIVE.require_ack">
                        mode_overrides.LIVE.require_ack
                      </option>
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="proposal-value"
                      className="field-label"
                      style={{ display: 'block', marginBottom: '4px' }}
                    >
                      Proposed Value
                    </label>
                    <input
                      id="proposal-value"
                      type="text"
                      className="modernist-input monospace"
                      value={propProposedValue}
                      onChange={(e) => setPropProposedValue(e.target.value)}
                      placeholder="e.g., SLACK, PAGERDUTY or 120"
                      data-testid="proposal-value-input"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="proposal-reasoning"
                      className="field-label"
                      style={{ display: 'block', marginBottom: '4px' }}
                    >
                      Proposal Rationale
                    </label>
                    <input
                      id="proposal-reasoning"
                      type="text"
                      className="modernist-input"
                      value={propReasoning}
                      onChange={(e) => setPropReasoning(e.target.value)}
                      data-testid="proposal-reasoning-input"
                    />
                  </div>
                </div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '14px',
                    flexWrap: 'wrap',
                  }}
                >
                  <label
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '12px',
                      cursor: 'pointer',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={propPromoteShadow}
                      onChange={(e) => setPropPromoteShadow(e.target.checked)}
                      data-testid="proposal-promote-shadow-checkbox"
                    />
                    Start Shadow Evaluation Immediately (PREVIEW)
                  </label>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void handleCreateProposal()}
                    disabled={proposalSubmitting}
                    data-testid="submit-proposal-btn"
                  >
                    {proposalSubmitting ? 'Submitting…' : 'Submit Proposal'}
                  </button>
                </div>
              </div>
            )}

            {proposals.length > 0 ? (
              <div className="table-container">
                <table className="data-table" data-testid="policy-proposals-table">
                  <thead>
                    <tr>
                      <th>Policy Type</th>
                      <th>Field &amp; Proposed Change</th>
                      <th>State</th>
                      <th>Shadow Samples &amp; Win Rate</th>
                      <th>Threshold &amp; Guard Gates</th>
                      <th>Baseline Hash Verification</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {proposals
                      .filter(
                        (prop) =>
                          proposalStateFilter === 'ALL' ||
                          prop.state.toUpperCase() === proposalStateFilter
                      )
                      .map((prop) => {
                        const agg = prop.shadow_aggregate;
                        const latestGuard =
                          prop.guard_results.length > 0
                            ? prop.guard_results[prop.guard_results.length - 1]
                            : null;
                        const busy = proposalActionBusyId === prop.delta_id;
                        return (
                          <tr
                            key={prop.delta_id}
                            data-testid={`proposal-row-${prop.delta_id}`}
                          >
                            <td className="monospace">
                              <strong>{prop.policy_type}</strong>
                              <div
                                style={{
                                  fontSize: '11px',
                                  color: 'var(--color-neutral-700)',
                                }}
                              >
                                {prop.reasoning}
                              </div>
                            </td>
                            <td className="monospace">
                              <div>
                                <strong>{prop.field_path}</strong>
                              </div>
                              <div style={{ fontSize: '11px' }}>
                                {formatPolicyValue(prop.current_value)} &rarr;{' '}
                                <strong>{formatPolicyValue(prop.proposed_value)}</strong>
                              </div>
                            </td>
                            <td>
                              <span
                                className={getPolicyStatusBadgeClass(prop.state)}
                                data-testid={`proposal-state-${prop.delta_id}`}
                              >
                                {prop.state}
                              </span>
                            </td>
                            <td
                              className="monospace"
                              data-testid={`proposal-samples-${prop.delta_id}`}
                            >
                              {agg ? (
                                <>
                                  <div>
                                    <strong>{agg.total_decisions}</strong> samples (
                                    {Math.round(agg.win_rate * 100)}% win)
                                  </div>
                                  <div style={{ fontSize: '11px' }}>
                                    +{agg.improved_decisions} / ={agg.neutral_decisions} / -
                                    {agg.degraded_decisions}
                                  </div>
                                </>
                              ) : (
                                <span>No shadow samples</span>
                              )}
                            </td>
                            <td>
                              <div
                                style={{
                                  display: 'flex',
                                  flexWrap: 'wrap',
                                  gap: '4px',
                                }}
                              >
                                <span
                                  className={
                                    agg?.min_sample_met
                                      ? 'badge tag-delivery-ok'
                                      : 'badge tag-delivery-pending'
                                  }
                                  data-testid={`proposal-min-samples-badge-${prop.delta_id}`}
                                >
                                  SAMPLES: {agg?.min_sample_met ? 'PASS' : 'PENDING'}
                                </span>
                                <span
                                  className={
                                    agg?.accuracy_threshold_met
                                      ? 'badge tag-delivery-ok'
                                      : agg?.status === 'FAILED'
                                        ? 'badge tag-delivery-failed'
                                        : 'badge tag-delivery-pending'
                                  }
                                  data-testid={`proposal-accuracy-badge-${prop.delta_id}`}
                                >
                                  ACCURACY:{' '}
                                  {agg?.accuracy_threshold_met
                                    ? 'PASS'
                                    : agg?.status === 'FAILED'
                                      ? 'FAIL'
                                      : 'PENDING'}
                                </span>
                                {latestGuard && (
                                  <span
                                    className={
                                      latestGuard.allowed
                                        ? 'badge tag-delivery-ok'
                                        : 'badge tag-delivery-failed'
                                    }
                                    data-testid={`proposal-guard-badge-${prop.delta_id}`}
                                  >
                                    {latestGuard.stage}:{' '}
                                    {latestGuard.allowed ? 'PASS' : 'BLOCKED'}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="monospace">
                              <span
                                className={
                                  prop.baseline_hash_matches
                                    ? 'badge tag-delivery-ok'
                                    : 'badge tag-delivery-failed'
                                }
                                data-testid={`proposal-baseline-badge-${prop.delta_id}`}
                              >
                                {prop.baseline_hash_matches
                                  ? 'BASELINE VERIFIED'
                                  : 'BASELINE STALE'}
                              </span>
                              <div
                                style={{ fontSize: '11px', marginTop: '4px' }}
                                title={prop.baseline_hash ?? undefined}
                              >
                                v{prop.baseline_version ?? 1} ·{' '}
                                {prop.baseline_hash
                                  ? prop.baseline_hash.slice(0, 10)
                                  : 'none'}
                              </div>
                            </td>
                            <td>
                              <div
                                style={{
                                  display: 'flex',
                                  flexWrap: 'wrap',
                                  gap: '6px',
                                }}
                              >
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  style={{ padding: '4px 8px', fontSize: '11px' }}
                                  onClick={() => void handleInspectProposal(prop.delta_id)}
                                  disabled={busy}
                                  data-testid={`inspect-proposal-btn-${prop.delta_id}`}
                                >
                                  Evidence
                                </button>
                                {isAdmin && prop.state === 'PROPOSED' && (
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    style={{ padding: '4px 8px', fontSize: '11px' }}
                                    onClick={() => void handlePromoteShadow(prop.delta_id)}
                                    disabled={busy || !prop.can_promote_to_shadow}
                                    data-testid={`promote-shadow-btn-${prop.delta_id}`}
                                  >
                                    Promote to SHADOW
                                  </button>
                                )}
                                {isAdmin && prop.state === 'SHADOW' && (
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    style={{ padding: '4px 8px', fontSize: '11px' }}
                                    onClick={() => void handleApproveToDraft(prop.delta_id)}
                                    disabled={busy || !prop.can_approve}
                                    data-testid={`approve-proposal-btn-${prop.delta_id}`}
                                  >
                                    Approve to DRAFT
                                  </button>
                                )}
                                {isAdmin && prop.state === 'APPROVED' && (
                                  <button
                                    type="button"
                                    className="btn btn-primary"
                                    style={{ padding: '4px 8px', fontSize: '11px' }}
                                    onClick={() => void handleActivateProposal(prop.delta_id)}
                                    disabled={busy || !prop.can_activate}
                                    data-testid={`activate-draft-btn-${prop.delta_id}`}
                                  >
                                    Activate DRAFT &rarr; ACTIVE
                                  </button>
                                )}
                                {isAdmin &&
                                  (prop.state === 'PROPOSED' ||
                                    prop.state === 'SHADOW' ||
                                    prop.state === 'APPROVED') && (
                                    <button
                                      type="button"
                                      className="btn btn-secondary"
                                      style={{ padding: '4px 8px', fontSize: '11px' }}
                                      onClick={() => void handleRejectProposal(prop.delta_id)}
                                      disabled={busy}
                                      data-testid={`reject-proposal-btn-${prop.delta_id}`}
                                    >
                                      Reject
                                    </button>
                                  )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div
                style={{ padding: '16px 24px', fontSize: '13px', color: 'var(--color-neutral-700)' }}
                data-testid="proposals-empty-message"
              >
                No policy delta proposals recorded yet.
              </div>
            )}

            {/* Selected Proposal Evidence & Guard Detail Drawer */}
            {selectedProposalDetail && (
              <div
                data-testid="proposal-evidence-detail"
                style={{
                  padding: '16px 24px',
                  borderTop: '1px solid var(--color-divider)',
                  backgroundColor: 'var(--color-surface)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '10px',
                  }}
                >
                  <h3 style={{ margin: 0, fontSize: '13px', textTransform: 'uppercase' }}>
                    Shadow Evidence &amp; Guard Ledger — {selectedProposalDetail.policy_type} (
                    {selectedProposalDetail.field_path})
                  </h3>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ padding: '2px 8px', fontSize: '11px' }}
                    onClick={() => setSelectedProposalDetail(null)}
                    data-testid="close-proposal-detail-btn"
                  >
                    Close
                  </button>
                </div>
                <div
                  className="monospace"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: '10px',
                    fontSize: '12px',
                    marginBottom: '12px',
                  }}
                >
                  <div>
                    <strong>Candidate Hash:</strong>{' '}
                    {selectedProposalDetail.candidate_hash.slice(0, 16)}
                  </div>
                  <div>
                    <strong>Baseline Hash:</strong>{' '}
                    {selectedProposalDetail.baseline_hash?.slice(0, 16) ?? 'none'}
                  </div>
                  <div>
                    <strong>Active Hash:</strong>{' '}
                    {selectedProposalDetail.current_active_hash?.slice(0, 16) ?? 'none'}
                  </div>
                  <div>
                    <strong>Proposed By:</strong> {selectedProposalDetail.proposed_by}
                  </div>
                </div>
                {selectedProposalDetail.shadow_results &&
                  selectedProposalDetail.shadow_results.length > 0 && (
                    <div>
                      <div
                        style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          marginBottom: '6px',
                        }}
                      >
                        Recent Shadow Decision Samples (
                        {selectedProposalDetail.shadow_results.length})
                      </div>
                      <ul
                        style={{ margin: 0, paddingLeft: '18px', fontSize: '12px' }}
                        data-testid="proposal-shadow-samples-list"
                      >
                        {selectedProposalDetail.shadow_results.slice(0, 5).map((sample) => (
                          <li key={sample.result_id} className="monospace">
                            decision={sample.decision_id} · changed=
                            {sample.changed ? 'true' : 'false'} · score=
                            {sample.improvement_score ?? 0}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            )}
          </section>
        )}

      {catalogLoading && activePolicies.length === 0 && policyRevisions.length === 0 && (
        <div style={{ padding: '12px 24px', fontSize: '12px' }}>
          Loading active policy catalog…
        </div>
      )}

      {/* Dry-Run Simulator & Tagged Live Test Sender (Producer / Admin scopes) */}
      {canProduce && (
        <section
          data-testid="policy-simulator-section"
          style={{
            padding: '24px',
            background: 'var(--color-bg)',
            borderBottom: '2px solid var(--color-divider)',
          }}
        >
          <h2 style={{ marginTop: 0, fontSize: '18px' }}>
            Dry-Run Simulator &amp; Tagged Live Test Dispatch
          </h2>
          <p style={{ marginTop: 0, color: 'var(--color-neutral-700)', fontSize: '13px' }}>
            Preview routing decisions with zero side effects, or dispatch a synthetically tagged{' '}
            <code>[TEST]</code> notification attributed to{' '}
            <code>{session.subject ?? 'authenticated producer'}</code>.
          </p>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: '12px',
              marginBottom: '12px',
            }}
          >
            <div>
              <label htmlFor="sim-notification-type" className="field-label" style={{ display: 'block', marginBottom: '6px' }}>
                Notification Type
              </label>
              <input
                id="sim-notification-type"
                type="text"
                className="modernist-input monospace"
                value={simNotificationType}
                onChange={(e) => setSimNotificationType(e.target.value)}
                placeholder="e.g., trading.order_placed"
                data-testid="sim-notification-type-input"
              />
            </div>

            <div>
              <label htmlFor="sim-intent" className="field-label" style={{ display: 'block', marginBottom: '6px' }}>
                Intent
              </label>
              <select
                id="sim-intent"
                className="modernist-select"
                value={simIntent}
                onChange={(e) => setSimIntent(e.target.value as NotificationIntent)}
                data-testid="sim-intent-select"
              >
                <option value="SAFETY">SAFETY</option>
                <option value="GOVERNANCE">GOVERNANCE</option>
                <option value="OPERATIONAL">OPERATIONAL</option>
                <option value="INFORMATIONAL">INFORMATIONAL</option>
              </select>
            </div>

            <div>
              <label htmlFor="sim-autonomy-mode" className="field-label" style={{ display: 'block', marginBottom: '6px' }}>
                Autonomy Mode
              </label>
              <select
                id="sim-autonomy-mode"
                className="modernist-select"
                value={simAutonomyMode}
                onChange={(e) => setSimAutonomyMode(e.target.value as AutonomyMode)}
                data-testid="sim-autonomy-mode-select"
              >
                <option value="PREVIEW">PREVIEW</option>
                <option value="SHADOW">SHADOW</option>
                <option value="LIVE">LIVE</option>
              </select>
            </div>

            <div>
              <label htmlFor="sim-title" className="field-label" style={{ display: 'block', marginBottom: '6px' }}>
                Title
              </label>
              <input
                id="sim-title"
                type="text"
                className="modernist-input"
                value={simTitle}
                onChange={(e) => setSimTitle(e.target.value)}
                data-testid="sim-title-input"
              />
            </div>

            <div>
              <label htmlFor="sim-source" className="field-label" style={{ display: 'block', marginBottom: '6px' }}>
                Producer Source
              </label>
              <input
                id="sim-source"
                type="text"
                className="modernist-input monospace"
                value={simSource}
                onChange={(e) => setSimSource(e.target.value)}
                data-testid="sim-source-input"
              />
            </div>

            <div>
              <label htmlFor="sim-agent-id" className="field-label" style={{ display: 'block', marginBottom: '6px' }}>
                Agent UUID
              </label>
              <input
                id="sim-agent-id"
                type="text"
                className="modernist-input monospace"
                value={simAgentId}
                onChange={(e) => setSimAgentId(e.target.value)}
                data-testid="sim-agent-id-input"
              />
            </div>
          </div>

          <div style={{ marginBottom: '14px' }}>
            <label htmlFor="sim-message" className="field-label" style={{ display: 'block', marginBottom: '6px' }}>
              Message Body
            </label>
            <input
              id="sim-message"
              type="text"
              className="modernist-input"
              value={simMessage}
              onChange={(e) => setSimMessage(e.target.value)}
              data-testid="sim-message-input"
            />
          </div>

          {simulatorError && (
            <div
              role="alert"
              data-testid="simulator-error"
              style={{
                marginBottom: '12px',
                padding: '10px 14px',
                border: '1.5px solid var(--color-accent)',
                backgroundColor: 'var(--color-accent-100)',
                color: 'var(--color-accent-800)',
              }}
            >
              {simulatorError}
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void handleSimulate()}
              disabled={simulating || sendingTest}
              data-testid="simulate-btn"
            >
              {simulating ? 'Simulating…' : 'Simulate (Dry-Run)'}
            </button>

            {!confirmingTestSend ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setConfirmingTestSend(true)}
                disabled={simulating || sendingTest || !simNotificationType.trim()}
                data-testid="initiate-test-send-btn"
              >
                Send Live Test Notification
              </button>
            ) : (
              <div
                data-testid="confirm-test-send-panel"
                style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}
              >
                <span style={{ fontSize: '12px', fontWeight: 600 }}>
                  Dispatch live <code>[TEST]</code> notification to configured channels?
                </span>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleConfirmTestSend()}
                  disabled={sendingTest}
                  data-testid="confirm-test-send-btn"
                >
                  {sendingTest ? 'Dispatching…' : 'Confirm Live Test Send'}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setConfirmingTestSend(false)}
                  disabled={sendingTest}
                  data-testid="cancel-test-send-btn"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          {simulationResult && (
            <div
              className="card"
              data-testid="simulation-result-card"
              style={{ marginTop: '16px', backgroundColor: 'var(--color-surface)' }}
            >
              <h3 style={{ marginTop: 0, fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Dry-Run Simulation Outcome
              </h3>
              <dl
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: '12px',
                  margin: 0,
                }}
              >
                <div>
                  <dt className="field-label">Simulated Outcome</dt>
                  <dd data-testid="sim-result-status" style={{ margin: '4px 0 0', fontWeight: 600 }}>
                    {simulationResult.status}
                  </dd>
                </div>
                <div>
                  <dt className="field-label">Resolved Channels</dt>
                  <dd data-testid="sim-result-channels" style={{ margin: '4px 0 0', fontFamily: 'var(--font-mono)' }}>
                    {simulationResult.channels_attempted.join(', ') || 'None'}
                  </dd>
                </div>
                <div>
                  <dt className="field-label">Delivery Mode</dt>
                  <dd data-testid="sim-result-delivery-mode" style={{ margin: '4px 0 0', fontFamily: 'var(--font-mono)' }}>
                    {simulationResult.delivery_mode}
                  </dd>
                </div>
                <div>
                  <dt className="field-label">Require ACK</dt>
                  <dd data-testid="sim-result-require-ack" style={{ margin: '4px 0 0', fontWeight: 600 }}>
                    {simulationResult.require_ack ? 'Yes' : 'No'}
                  </dd>
                </div>
                <div>
                  <dt className="field-label">Policy Source</dt>
                  <dd data-testid="sim-result-policy-source" style={{ margin: '4px 0 0', fontFamily: 'var(--font-mono)' }}>
                    {simulationResult.policy_source}
                  </dd>
                </div>
              </dl>
              {simulationResult.warnings.length > 0 && (
                <ul style={{ marginTop: '8px', marginBottom: 0 }}>
                  {simulationResult.warnings.map((w, idx) => (
                    <li key={idx}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {testSendResult && (
            <div
              role="status"
              data-testid="test-send-result-card"
              style={{
                marginTop: '16px',
                padding: '12px 16px',
                border: '1.5px solid var(--color-text)',
                backgroundColor: 'var(--color-surface)',
              }}
            >
              <strong>Live [TEST] notification accepted:</strong>{' '}
              <span className="monospace">{testSendResult.notification_id}</span> (
              {testSendResult.status}){' '}
              {inRouter ? (
                <Link
                  to={`/deliveries/${testSendResult.notification_id}`}
                  data-testid="test-send-delivery-link"
                >
                  View Delivery Timeline &rarr;
                </Link>
              ) : (
                <a
                  href={`/deliveries/${testSendResult.notification_id}`}
                  data-testid="test-send-delivery-link"
                >
                  View Delivery Timeline &rarr;
                </a>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export default PolicyInspectorPage;
