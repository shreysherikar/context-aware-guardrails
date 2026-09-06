import { DecisionColors } from '../../constants/theme';
import {
  extractAction,
  extractGeneratedResponse,
  extractReason,
  getDecisionMeta,
} from '../../lib/decision';

describe('getDecisionMeta', () => {
  it.each(['ALLOW', 'REWRITE', 'CLARIFY', 'REVIEW', 'BLOCK'])(
    'resolves known action %s to its own color set and a human label',
    (action) => {
      const meta = getDecisionMeta(action);
      expect(meta.action).toBe(action);
      expect(meta.colors).toBe(DecisionColors[action]);
      expect(meta.label).not.toBe(action); // human label should differ from the raw enum
    }
  );

  it('is case-insensitive', () => {
    expect(getDecisionMeta('allow').action).toBe('ALLOW');
  });

  it('falls back to UNKNOWN for a missing action, but preserves an unrecognized one for debugging', () => {
    expect(getDecisionMeta(undefined).action).toBe('UNKNOWN');
    expect(getDecisionMeta(undefined).colors).toBe(DecisionColors.UNKNOWN);
    // An action the UI doesn't recognize is still surfaced as-is (uppercased)
    // rather than silently hidden behind "UNKNOWN" — useful when a backend
    // change introduces a new action value before the app is updated.
    expect(getDecisionMeta('not-a-real-action').action).toBe('NOT-A-REAL-ACTION');
    expect(getDecisionMeta('not-a-real-action').colors).toBe(DecisionColors.UNKNOWN);
  });
});

describe('extractAction / extractReason / extractGeneratedResponse', () => {
  it('reads a flat response shape', () => {
    const data = { action: 'BLOCK', reason: 'prompt injection', response: null };
    expect(extractAction(data)).toBe('BLOCK');
    expect(extractReason(data)).toBe('prompt injection');
    expect(extractGeneratedResponse(data)).toBeNull();
  });

  it('reads a nested decision/explanation/generation shape', () => {
    const data = {
      decision: { action: 'REVIEW', reason: 'IP exposure' },
      explanation: { resolution_message: 'escalated to a human reviewer' },
      generation: { response: 'here is the safe response' },
    };
    expect(extractAction(data)).toBe('REVIEW');
    expect(extractReason(data)).toBe('IP exposure');
    expect(extractGeneratedResponse(data)).toBe('here is the safe response');
  });

  it('falls back to a default reason when none is present anywhere', () => {
    expect(extractReason({})).toBe('No explanation provided.');
  });
});
