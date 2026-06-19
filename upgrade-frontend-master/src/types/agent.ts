export enum AgentToolEnum {
  'research' = 'research',
  'web_search' = 'web_search',
}

export interface IAgentProfile {
  agent_name: string;
  description: string;
image: string;
}

export interface IModelSettings {
  llm_model: string;
  temperature: number;
}

export interface IAgentView{
  agent_id: string,
  name: string,
  description: string
  image: string
}

export interface IAgent {
  id?: string,
  profile: IAgentProfile;
  system_prompt: string;
  model_settings: IModelSettings;
  is_public: boolean
  knowledge_base: {
    urls: string[];
    file: string[];
  };
  tools: AgentToolEnum[];
}
