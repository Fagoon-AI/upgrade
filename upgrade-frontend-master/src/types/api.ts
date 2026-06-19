export interface ChatResponse {
  response: string;
  files?: string[];
}

export interface TranscriptionResponse {
  transcription: string;
}

export interface UploadResponse {
  url: string;
}

export interface EvaluationResponse {
  factual_accuracy: string;
  ground_truth: string;
  confidence_score: number;
}

export interface ImagenResponse {
  url: string;
}

export interface ChatRequestBody {
  message: string;
  internet_search: boolean; // Changed from webSearch
  files?: string[];
}
