import { AGENT_NODES, FLOW_EDGES, NODE_W, NODE_H } from '../../data/agentFlow';

function port(from, to) {
  const a = AGENT_NODES.find((n) => n.id === from);
  const b = AGENT_NODES.find((n) => n.id === to);
  if (!a || !b) return null;

  const x1 = a.x + NODE_W;
  const y1 = a.y + NODE_H / 2;
  const x2 = b.x;
  const y2 = b.y + NODE_H / 2;
  const mx = (x1 + x2) / 2;

  return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
}

export default function FlowEdges({ activeIds = [] }) {
  const canvasW = 2200;
  const canvasH = 820;

  return (
    <svg className="flow-edges" viewBox={`0 0 ${canvasW} ${canvasH}`} aria-hidden="true">
      <defs>
        <marker id="flow-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" className="flow-edge-marker" />
        </marker>
        <marker id="flow-arrow-active" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" className="flow-edge-marker-active" />
        </marker>
      </defs>

      {FLOW_EDGES.map(({ from, to, dashed }) => {
        const d = port(from, to);
        if (!d) return null;
        const active = activeIds.includes(from) && activeIds.includes(to);
        return (
          <path
            key={`${from}-${to}`}
            d={d}
            fill="none"
            className={active ? 'flow-edge-path flow-edge-path--active' : 'flow-edge-path'}
            strokeDasharray={dashed && !active ? '6 4' : undefined}
            markerEnd={active ? 'url(#flow-arrow-active)' : 'url(#flow-arrow)'}
          />
        );
      })}
    </svg>
  );
}
