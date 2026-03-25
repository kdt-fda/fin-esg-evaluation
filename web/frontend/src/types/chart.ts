export interface PredictionReason {
  factor: string;
  impact: string;
  contribution: number;
}

export interface ChartDataPoint {
  date: string;
  actual?: number;
  predicted?: number;
  reason?: PredictionReason[];
  changeReason?: string;
  isPredictionBridge?: boolean;
}

export interface LongTermItem {
  code: string;
  name: string;
  sector: string;
  score: number;
}