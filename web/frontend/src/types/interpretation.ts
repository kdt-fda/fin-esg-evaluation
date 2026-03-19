export type SignalDirection = 'positive' | 'negative';
export type SignalStrength = 'high' | 'medium' | 'low';

export interface InterpretationSignal {
  feature: string;
  signal: string;
  direction: SignalDirection;
  strength: SignalStrength;
  reason: string;
}

export interface InterpretationPayload {
  ai_summary?: string;
  main_signals?: InterpretationSignal[];
}

export interface InterpretationResponse {
  ticker: string;
  pred_date: string | null;
  interpretation: InterpretationPayload | null;
}