import { DecisionColors } from '../constants/theme';

/**
 * Single source of truth for how a guardrail decision action is labelled and
 * colored across the app (ResultCard, AuditLogScreen). Keeping this here
 * instead of duplicated per-screen avoids the two views drifting out of sync.
 */

const HUMAN_LABELS = {
  ALLOW: 'Allowed',
  REWRITE: 'Rewritten',
  CLARIFY: 'Clarify',
  REVIEW: 'Review',
  BLOCK: 'Blocked',
  UNKNOWN: 'Unknown',
};

/**
 * @param {unknown} rawAction
 * @returns {{ action: string, label: string, colors: { fg: string, bg: string, border: string } }}
 */
export function getDecisionMeta(rawAction) {
  const action = String(rawAction || 'UNKNOWN').toUpperCase();
  const colors = DecisionColors[action] || DecisionColors.UNKNOWN;
  const label = HUMAN_LABELS[action] || action;
  return { action, label, colors };
}

/**
 * Pulls the decision action out of a /guardrail/evaluate (or evaluate-image)
 * response, tolerating both a flat shape and a nested `decision` object -
 * the backend has used both across its history, so this stays defensive.
 */
export function extractAction(data) {
  return data?.action || data?.decision?.action || data?.policy_decision?.action || 'UNKNOWN';
}

export function extractReason(data) {
  return (
    data?.reason ||
    data?.decision?.reason ||
    data?.explanation?.reason ||
    data?.explanation?.resolution_message ||
    'No explanation provided.'
  );
}

export function extractGeneratedResponse(data) {
  return data?.response || data?.generation?.response || data?.generated_text || null;
}
