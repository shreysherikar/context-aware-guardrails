import { MoreHorizontal, CheckCircle2, Loader2, Clock, Circle, AlertCircle } from 'lucide-react';

const STATUS = {
  complete: { label: 'Complete', Icon: CheckCircle2, cls: 'complete' },
  running:  { label: 'Running',  Icon: Loader2,      cls: 'running' },
  pending:  { label: 'Pending',  Icon: Clock,        cls: 'pending' },
  idle:     { label: 'Idle',     Icon: Circle,       cls: 'idle' },
  error:    { label: 'Error',    Icon: AlertCircle,  cls: 'error' },
};

export default function AgentNode({ node, state, selected, onSelect }) {
  const meta = state || { status: 'idle', tokens: 0, duration: '—', task: node.description };
  const st = STATUS[meta.status] || STATUS.idle;
  const StatusIcon = st.Icon;

  return (
    <button
      type="button"
      className={`flow-node${selected ? ' selected' : ''}${meta.status !== 'idle' ? ` is-${meta.status}` : ''}`}
      style={{ left: node.x, top: node.y, width: 220 }}
      onClick={() => onSelect?.(node.id)}
      aria-pressed={selected}
    >
      <div className="flow-node-head">
        <span className={`flow-node-status flow-node-status--${st.cls}`}>
          <StatusIcon size={12} className={meta.status === 'running' ? 'spin' : ''} />
          {st.label}
        </span>
        <span className="flow-node-menu" aria-hidden="true">
          <MoreHorizontal size={14} />
        </span>
      </div>

      <h3 className="flow-node-name">{node.name}</h3>
      <p className="flow-node-type">{node.type}</p>

      <div className="flow-node-model">
        <span className="flow-node-model-dot" />
        {node.model}
      </div>

      <div className="flow-node-metrics">
        <span>{meta.tokens || 0} tokens</span>
        <span>{meta.duration || '—'}</span>
      </div>

      <p className="flow-node-task">{meta.task || node.description}</p>
    </button>
  );
}
