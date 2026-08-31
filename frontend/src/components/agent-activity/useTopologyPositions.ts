import { useEffect, useMemo, useState } from "react";
import {
  clampGraphPosition,
  graphPositionStorageKey,
  mergeSavedGraphPositions,
  type ActivityGraphNode,
  type GraphPosition,
} from "@/hooks/useAgentActivityViewModel";

function readPositions(key: string): Record<string, GraphPosition> | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed as Record<string, GraphPosition> : null;
  } catch {
    return null;
  }
}

function positionRecord(nodes: readonly ActivityGraphNode[]): Record<string, GraphPosition> {
  return Object.fromEntries(nodes.map((node) => [node.id, { xPct: node.xPct, yPct: node.yPct }]));
}

export function useTopologyPositions(
  defaultNodes: readonly ActivityGraphNode[],
  projectScopeId: string | null,
) {
  const storageKey = graphPositionStorageKey(projectScopeId);
  const identityKey = useMemo(
    () => defaultNodes.map((node) => node.id).sort().join("|"),
    [defaultNodes],
  );
  const [positions, setPositions] = useState<ActivityGraphNode[]>(() =>
    mergeSavedGraphPositions(defaultNodes, readPositions(storageKey)),
  );

  useEffect(() => {
    setPositions(mergeSavedGraphPositions(defaultNodes, readPositions(storageKey)));
  }, [defaultNodes, identityKey, storageKey]);

  const previewMove = (id: string, position: GraphPosition) => {
    const clamped = clampGraphPosition(position);
    setPositions((current) => current.map((node) => node.id === id ? { ...node, ...clamped } : node));
  };

  const commitMove = (id: string, position: GraphPosition) => {
    const clamped = clampGraphPosition(position);
    setPositions((current) => {
      const next = current.map((node) => node.id === id ? { ...node, ...clamped } : node);
      window.localStorage.setItem(storageKey, JSON.stringify(positionRecord(next)));
      return next;
    });
  };

  const organize = () => {
    window.localStorage.removeItem(storageKey);
    setPositions([...defaultNodes]);
  };

  return { positions, previewMove, commitMove, organize };
}
