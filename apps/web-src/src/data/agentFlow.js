/** Agent flow graph — pipeline stages + specialist agents from services/agent. */

export const AGENT_NODES = [
  {
    id: 'input',
    name: 'Input Gateway',
    type: 'Product agent',
    model: 'ContextGuard v1',
    description: 'Receives text or image prompts and assigns a conversation ID.',
    x: 40, y: 60,
    layer: 'intake',
  },
  {
    id: 'compliance_guard',
    name: 'Compliance Guard',
    type: 'Guard agent',
    model: 'Policy Engine',
    description: 'Always-on gate. Runs risk classification and policy before specialists.',
    x: 280, y: 60,
    layer: 'security',
  },
  {
    id: 'risk_classifier',
    name: 'Risk Classifier',
    type: 'Subagent',
    model: 'Groq / Heuristic',
    description: 'Scores injection, PHI/PII, off-label, and sensitivity categories.',
    x: 520, y: 60,
    layer: 'security',
  },
  {
    id: 'policy_engine',
    name: 'Policy Engine',
    type: 'Subagent',
    model: 'YAML Rules',
    description: 'Maps risk to ALLOW, REWRITE, CLARIFY, REVIEW, or BLOCK.',
    x: 760, y: 60,
    layer: 'security',
  },
  {
    id: 'sanitization',
    name: 'Sanitization Agent',
    type: 'Subagent',
    model: 'Regex + NLP',
    description: 'Redacts PII/PHI when policy returns REWRITE.',
    x: 760, y: 220,
    layer: 'security',
  },
  {
    id: 'router',
    name: 'Agent Router',
    type: 'Orchestrator',
    model: 'Pattern Match',
    description: 'Selects primary and supporting specialists from prompt patterns.',
    x: 1000, y: 140,
    layer: 'routing',
  },
  {
    id: 'general',
    name: 'General Assistant',
    type: 'Specialist agent',
    model: 'Claude Sonnet',
    description: 'Default FieldAssist colleague for broad internal questions.',
    x: 1240, y: 40,
    layer: 'specialist',
  },
  {
    id: 'research',
    name: 'Research Agent',
    type: 'Enrichment agent',
    model: 'Claude Sonnet + Web',
    description: 'Searches the web and grounds answers in cited sources.',
    x: 1240, y: 160,
    layer: 'specialist',
  },
  {
    id: 'hcp_engagement',
    name: 'HCP Engagement',
    type: 'Specialist agent',
    model: 'Claude Sonnet',
    description: 'Compliant outreach, follow-ups, and HCP communication.',
    x: 1240, y: 280,
    layer: 'specialist',
  },
  {
    id: 'analytics',
    name: 'Analytics Agent',
    type: 'Specialist agent',
    model: 'Claude Sonnet',
    description: 'Summarizes aggregate CRM and campaign KPIs.',
    x: 1240, y: 400,
    layer: 'specialist',
  },
  {
    id: 'compliance_coach',
    name: 'Compliance Coach',
    type: 'Specialist agent',
    model: 'Claude Sonnet',
    description: 'Explains policy, fair balance, and approved-claim rules.',
    x: 1240, y: 520,
    layer: 'specialist',
  },
  {
    id: 'optical',
    name: 'Optical Analysis',
    type: 'Specialist agent',
    model: 'OCR + Vision',
    description: 'Interprets text extracted from uploaded document images.',
    x: 1240, y: 640,
    layer: 'specialist',
  },
  {
    id: 'ocr',
    name: 'OCR Extractor',
    type: 'Subagent',
    model: 'Tesseract',
    description: 'Extracts text from uploaded images for optical analysis.',
    x: 520, y: 220,
    layer: 'optical',
  },
  {
    id: 'optical_analyzer',
    name: 'Optical Analyzer',
    type: 'Subagent',
    model: 'Heuristic',
    description: 'Assesses document risk from OCR output.',
    x: 520, y: 340,
    layer: 'optical',
  },
  {
    id: 'web_search',
    name: 'Web Search Bridge',
    type: 'Enrichment agent',
    model: 'DuckDuckGo',
    description: 'Fetches public sources when Research Agent is activated.',
    x: 1480, y: 160,
    layer: 'enrichment',
  },
  {
    id: 'llm_gateway',
    name: 'LLM Gateway',
    type: 'Generation agent',
    model: 'Groq / Ollama',
    description: 'Generates the answer using the routed system prompt.',
    x: 1720, y: 280,
    layer: 'generation',
  },
  {
    id: 'output_guardrail',
    name: 'Output Guardrail',
    type: 'Guard agent',
    model: 'Groq Classifier',
    description: 'Checks generated output for policy violations.',
    x: 1960, y: 280,
    layer: 'generation',
  },
  {
    id: 'messenger',
    name: 'Messenger Agent',
    type: 'Subagent',
    model: 'Template + LLM',
    description: 'Composes user-facing explanation with issues and corrections.',
    x: 1960, y: 420,
    layer: 'response',
  },
  {
    id: 'feedback',
    name: 'Feedback Builder',
    type: 'Subagent',
    model: 'Deterministic',
    description: 'Builds issues, corrections, and pharma remediation hints.',
    x: 1720, y: 420,
    layer: 'response',
  },
  {
    id: 'audit',
    name: 'Audit Logger',
    type: 'Subagent',
    model: 'SQLite',
    description: 'Persists the full decision trail for compliance review.',
    x: 1960, y: 560,
    layer: 'response',
  },
];

export const FLOW_EDGES = [
  { from: 'input', to: 'compliance_guard' },
  { from: 'compliance_guard', to: 'risk_classifier' },
  { from: 'risk_classifier', to: 'policy_engine' },
  { from: 'policy_engine', to: 'sanitization', dashed: true },
  { from: 'policy_engine', to: 'router' },
  { from: 'sanitization', to: 'router', dashed: true },
  { from: 'input', to: 'ocr', dashed: true },
  { from: 'ocr', to: 'optical_analyzer', dashed: true },
  { from: 'optical_analyzer', to: 'risk_classifier', dashed: true },
  { from: 'router', to: 'general' },
  { from: 'router', to: 'research' },
  { from: 'router', to: 'hcp_engagement' },
  { from: 'router', to: 'analytics' },
  { from: 'router', to: 'compliance_coach' },
  { from: 'router', to: 'optical' },
  { from: 'research', to: 'web_search' },
  { from: 'general', to: 'llm_gateway' },
  { from: 'research', to: 'llm_gateway' },
  { from: 'hcp_engagement', to: 'llm_gateway' },
  { from: 'analytics', to: 'llm_gateway' },
  { from: 'compliance_coach', to: 'llm_gateway' },
  { from: 'optical', to: 'llm_gateway' },
  { from: 'web_search', to: 'llm_gateway', dashed: true },
  { from: 'llm_gateway', to: 'output_guardrail' },
  { from: 'output_guardrail', to: 'feedback' },
  { from: 'feedback', to: 'messenger' },
  { from: 'messenger', to: 'audit' },
  { from: 'policy_engine', to: 'messenger', dashed: true },
];

const PIPELINE_ALWAYS = [
  'input', 'compliance_guard', 'risk_classifier', 'policy_engine', 'router',
  'llm_gateway', 'output_guardrail', 'feedback', 'messenger', 'audit',
];

const TERMINAL_ACTIONS = new Set(['BLOCK', 'CLARIFY', 'REVIEW']);

export function traceFromResponse(response, prompt) {
  const states = {};
  for (const node of AGENT_NODES) {
    states[node.id] = { status: 'idle', tokens: 0, duration: '—', task: node.description };
  }

  for (const id of PIPELINE_ALWAYS) {
    states[id] = { status: 'complete', tokens: randTokens(), duration: randDuration(), task: states[id]?.task };
  }

  if (response?.active_agents) {
    for (const agent of response.active_agents) {
      if (states[agent.id]) {
        states[agent.id] = {
          status: 'complete',
          tokens: randTokens(),
          duration: randDuration(),
          task: prompt?.slice(0, 80) || agent.name,
        };
      }
    }
  }

  if (response?.primary_agent && states[response.primary_agent]) {
    states[response.primary_agent].status = 'running';
    states[response.primary_agent].task = `Primary · ${prompt?.slice(0, 72) || 'Active task'}`;
  }

  if (response?.action === 'REWRITE' && states.sanitization) {
    states.sanitization.status = 'complete';
    states.sanitization.tokens = randTokens();
    states.sanitization.duration = randDuration();
  }

  if (response?.web_search_used && states.web_search) {
    states.web_search.status = 'complete';
    states.web_search.tokens = (response.web_sources?.length || 0) * 120;
    states.web_search.duration = randDuration();
    states.web_search.task = `${response.web_sources?.length || 0} sources retrieved`;
  }

  if (response?.input_type === 'image') {
    states.ocr.status = 'complete';
    states.optical_analyzer.status = 'complete';
    states.optical.status = 'complete';
  }

  if (TERMINAL_ACTIONS.has(response?.action)) {
    states.llm_gateway.status = 'idle';
    states.output_guardrail.status = 'idle';
    states.policy_engine.status = 'complete';
    states.policy_engine.task = `Terminal · ${response.action}`;
    if (states.messenger) {
      states.messenger.status = 'complete';
      states.messenger.task = response.message?.slice(0, 80) || 'Terminal response';
    }
  }

  if (response?.blocked) {
    states.policy_engine.status = 'error';
    states.policy_engine.task = 'Blocked by policy';
  }

  return states;
}

export function idleStates() {
  const states = {};
  for (const node of AGENT_NODES) {
    states[node.id] = { status: 'idle', tokens: 0, duration: '—', task: node.description };
  }
  states.compliance_guard.status = 'pending';
  states.risk_classifier.status = 'pending';
  states.policy_engine.status = 'pending';
  return states;
}

export function runningStates() {
  const states = idleStates();
  for (const id of ['input', 'compliance_guard', 'risk_classifier', 'policy_engine']) {
    states[id] = { status: 'running', tokens: 0, duration: '…', task: 'Processing…' };
  }
  return states;
}

export function countByStatus(states) {
  const counts = { complete: 0, running: 0, pending: 0, idle: 0, error: 0 };
  for (const node of AGENT_NODES) {
    const s = states[node.id]?.status || 'idle';
    counts[s] = (counts[s] || 0) + 1;
  }
  return counts;
}

function randTokens() {
  return Math.floor(80 + Math.random() * 420);
}

function randDuration() {
  return `${(0.1 + Math.random() * 2.4).toFixed(1)} sec`;
}

export const NODE_W = 220;
export const NODE_H = 130;
