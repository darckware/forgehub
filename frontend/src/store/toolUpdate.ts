import { create } from "zustand";
import type { MonitoredTool } from "@/hooks/useToolVersions";

export interface ToolUpdateOutput {
  tool: MonitoredTool;
  output: string;
  error: string | null;
}

interface ToolUpdateState {
  // Per-tool, not a single value -- otherwise starting a second tool's
  // update clobbered the first's "running" state (its spinner vanished
  // mid-flight, its button re-enabled) and, worse, whichever update
  // finished last silently overwrote the other's result. Two tools update
  // fully independently (no shared lock on the backend/bridge), so the UI
  // must track them independently too.
  updatingTools: Set<MonitoredTool>;
  updateOutputs: Partial<Record<MonitoredTool, ToolUpdateOutput>>;
  // Which tool's detail panel is open -- an accordion (one at a time) is
  // fine here, unlike the two above; it's just which result you're
  // looking at, not which update is in flight.
  expandedTool: MonitoredTool | null;
  startUpdate: (tool: MonitoredTool) => void;
  finishUpdate: (result: ToolUpdateOutput) => void;
  failUpdate: (tool: MonitoredTool, error: string) => void;
  setExpandedTool: (tool: MonitoredTool | null) => void;
}

export const useToolUpdateStore = create<ToolUpdateState>((set) => ({
  updatingTools: new Set(),
  updateOutputs: {},
  expandedTool: null,
  startUpdate: (tool) =>
    set((s) => ({
      updatingTools: new Set(s.updatingTools).add(tool),
      updateOutputs: { ...s.updateOutputs, [tool]: undefined },
    })),
  finishUpdate: (result) =>
    set((s) => {
      const updatingTools = new Set(s.updatingTools);
      updatingTools.delete(result.tool);
      return {
        updatingTools,
        updateOutputs: { ...s.updateOutputs, [result.tool]: result },
        expandedTool: result.tool,
      };
    }),
  failUpdate: (tool, error) =>
    set((s) => {
      const updatingTools = new Set(s.updatingTools);
      updatingTools.delete(tool);
      return {
        updatingTools,
        updateOutputs: { ...s.updateOutputs, [tool]: { tool, output: "", error } },
        expandedTool: tool,
      };
    }),
  setExpandedTool: (tool) => set({ expandedTool: tool }),
}));
