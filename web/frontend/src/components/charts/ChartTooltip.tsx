import type { ChartDataPoint } from '../../types/chart';

interface ShortChartTooltipProps {
  active?: boolean;
  payload?: any[];
  formatTickLabel: (value: string) => string;
}

export default function ShortChartTooltip({
  active,
  payload,
  formatTickLabel,
}: ShortChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const d: ChartDataPoint = payload[0].payload;

  return (
    <div className="bg-white p-4 rounded-lg shadow-lg border border-gray-200 max-w-xs">
      <p className="font-semibold text-gray-900 mb-2">{formatTickLabel(d.date)}</p>

      {d.actual !== undefined && (
        <p className="text-sm text-gray-700">
          실제: <span className="font-semibold">{d.actual.toLocaleString()}원</span>
        </p>
      )}

      {d.predicted !== undefined && !d.isPredictionBridge && (
        <p className="text-sm text-blue-600">
          예측: <span className="font-semibold">{d.predicted.toLocaleString()}원</span>
        </p>
      )}
    </div>
  );
}