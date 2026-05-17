import type { Node, Edge } from "reactflow";

export interface HookDef {
  shell?: string;
  python?: string;
}

export interface StageData {
  name: string;
  tools: string[];
  description: string;
  on_enter: HookDef[];
  on_exit: HookDef[];
  isTerminal?: boolean;
  extra?: Record<string, unknown>;
}

export interface ConditionDef {
  type: string;
  params: Record<string, unknown>;
}

export interface EdgeData {
  conditions: ConditionDef[];
  on_fail: string | null;
  description: string;
}

export type StageNode = Node<StageData>;
export type CondEdge = Edge<EdgeData>;
