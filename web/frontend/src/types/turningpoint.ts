export interface TurningPoint {
  date: string;
  type: string;
  title: string;
  strength: 'high' | 'medium' | 'low';
  summary: string;
}

export interface TurningPointsResponse {
  stock_name: string;
  ticker: string;
  as_of_date: string | null;
  turning_points: TurningPoint[];
}