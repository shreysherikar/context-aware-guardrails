import { useMemo, useRef } from 'react';
import AgentNode from './AgentNode';
import FlowEdges from './FlowEdges';
import { AGENT_NODES } from '../../data/agentFlow';

export default function AgentFlowCanvas({ nodeStates, selectedId, onSelectNode }) {
  const wrapRef = useRef(null);

  const activeIds = useMemo(() => {
    return AGENT_NODES
      .filter((n) => {
        const s = nodeStates[n.id]?.status;
        return s && s !== 'idle';
      })
      .map((n) => n.id);
  }, [nodeStates]);

  return (
    <div className="flow-canvas-wrap" ref={wrapRef}>
      <div className="flow-canvas">
        <FlowEdges activeIds={activeIds} />
        {AGENT_NODES.map((node) => (
          <AgentNode
            key={node.id}
            node={node}
            state={nodeStates[node.id]}
            selected={selectedId === node.id}
            onSelect={onSelectNode}
          />
        ))}
      </div>
    </div>
  );
}
