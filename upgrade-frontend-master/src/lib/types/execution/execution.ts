/* eslint-disable @typescript-eslint/no-explicit-any */
import { inputExecutors } from "./input-execution";
import { languageExecutors } from "./language-execution";
import { voicesynthesisExecutors } from "./voicesynthesis";
import { imagegenExecutors } from "./imagegen-execution";
import { googleExecutors } from "./google-execution";
import { utilsExecutors } from "./utils-execution";

export type ExecutionStatus = 'idle' | 'running' | 'completed' | 'error';
export const api_base_url = '/api/v1'
// export const api_base_url = 'http://localhost:2321/api/v1'
export interface NodeExecutionData {
  id: string;
  status: ExecutionStatus;
  input?: any;
  output?: any;
  error?: string;
}

export interface WorkflowExecution {
  id: string;
  status: ExecutionStatus;
  startTime: Date;
  endTime?: Date;
  nodes: Record<string, NodeExecutionData>;
  error?: string;
}

export interface ExecutionResult {
  success: boolean;
  data?: any;
  error?: string;
}

export type NodeExecutor = (input: any, settings: any, user_id: string) => Promise<ExecutionResult>;

export const nodeExecutors: Record<string, NodeExecutor> = {
  ...inputExecutors, 
  ...languageExecutors,
  ...imagegenExecutors,
  ...voicesynthesisExecutors,
  ...googleExecutors,
  ...utilsExecutors 
};

