import { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';
import { TrendingUp, TrendingDown, Info, MousePointer } from 'lucide-react';

interface PredictionReason {
  factor: string;
  impact: string;
  contribution: number;
}

interface ChartDataPoint {
  date: string;
  actual: number;
  predicted?: number;
  reason?: PredictionReason[];
  changeReason?: string;
}

interface ShortTermPredictionChartProps {
  title: string;
  data: ChartDataPoint[];
  confidence: number;
  pastCount?: number;
  onReasonClick?: (data: ChartDataPoint) => void;
}

function formatTickLabel(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function getYear(value: string): number | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.getFullYear();
}

export default function ShortTermPredictionChart({
  title,
  data,
  confidence,
  pastCount = 0,
  onReasonClick,
}: ShortTermPredictionChartProps) {
  const [tooltipData, setTooltipData] = useState<{ x: number; y: number; data: ChartDataPoint } | null>(null);

  const MIN_WINDOW = 30;
  const [sliderValue, setSliderValue] = useState(999999);

  const sliderMax = Math.max(0, pastCount - MIN_WINDOW);
  const clampedSlider = Math.min(sliderValue, sliderMax);

  const visibleData = useMemo(() => {
    if (pastCount <= 0 || data.length <= MIN_WINDOW) return data;
    return data.slice(clampedSlider);
  }, [data, pastCount, clampedSlider]);

  const spansMultipleYears = useMemo(() => {
    if (visibleData.length < 2) return false;
    const years = visibleData.map((d) => getYear(d.date)).filter((y): y is number => y !== null);
    return new Set(years).size >= 2;
  }, [visibleData]);

  const CustomXAxisTick = ({ x, y, payload, index }: any) => {
    const value: string = payload?.value ?? '';
    const label = formatTickLabel(value);

    let showYear = false;
    let yearText: string | null = null;

    if (spansMultipleYears && typeof index === 'number' && index > 0) {
      const currentDate = new Date(visibleData[index]?.date);
      const previousDate = new Date(visibleData[index - 1]?.date);

      const currentYear = currentDate.getFullYear();
      const previousYear = previousDate.getFullYear();
      const currentMonth = currentDate.getMonth(); // 0 = January

      // 연도가 바뀌고, 현재 tick이 1월일 때만 연도 표시
      if (currentYear !== previousYear && currentMonth === 0) {
        showYear = true;
        yearText = String(currentYear);
      }
    }

    return (
      <g>
        <text x={x} y={y + 12} textAnchor="middle" fill="#6b7280" fontSize={11}>
          {label}
        </text>
        {showYear && yearText && (
          <text x={x} y={y + 24} textAnchor="middle" fill="#9ca3af" fontSize={10}>
            {yearText}
          </text>
        )}
      </g>
    );
  };

  const tickInterval = useMemo(() => {
    const n = visibleData.length;
    if (n <= 60) return Math.max(0, Math.floor(n / 6));
    if (n <= 250) return Math.max(0, Math.floor(n / 8));
    return Math.max(0, Math.floor(n / 10));
  }, [visibleData.length]);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const d: ChartDataPoint = payload[0].payload;
      return (
        <div className="bg-white p-4 rounded-lg shadow-lg border border-gray-200 max-w-xs">
          <p className="font-semibold text-gray-900 mb-2">{formatTickLabel(d.date)}</p>
          {d.actual !== undefined && (
            <p className="text-sm text-gray-700">
              실제: <span className="font-semibold">{d.actual.toLocaleString()}원</span>
            </p>
          )}
          {d.predicted !== undefined && (
            <p className="text-sm text-blue-600">
              예측: <span className="font-semibold">{d.predicted.toLocaleString()}원</span>
            </p>
          )}
        </div>
      );
    }
    return null;
  };

  const handleMouseMove = (e: any) => {
    if (e && e.activePayload && e.activePayload.length > 0) {
      const dataPoint: ChartDataPoint = e.activePayload[0].payload;
      if (dataPoint.reason) {
        setTooltipData({
          x: e.chartX,
          y: e.chartY,
          data: dataPoint,
        });
      } else {
        setTooltipData(null);
      }
    }
  };

  const handleMouseLeave = () => {
    setTooltipData(null);
  };

  return (
    <div className="bg-white rounded-xl shadow-sm p-6 flex-1">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h3 className="text-xl font-semibold text-gray-900 mb-2">{title}</h3>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">예측 신뢰도</span>
            <div className="flex items-center gap-2">
              <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    confidence >= 80 ? 'bg-green-500' : confidence >= 60 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${confidence}%` }}
                />
              </div>
              <span className="text-sm font-semibold text-gray-900">{confidence}%</span>
            </div>
          </div>
        </div>
        <Info className="text-gray-400" size={20} />
      </div>

      <div className="relative">
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={visibleData} onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}>
            <defs>
              <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.1} />
                <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="colorPredicted" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.1} />
                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />

            <XAxis
              dataKey="date"
              tick={<CustomXAxisTick />}
              tickLine={{ stroke: '#e5e7eb' }}
              interval={tickInterval}
              height={spansMultipleYears ? 40 : 25}
            />

            <YAxis
              tick={{ fill: '#6b7280', fontSize: 12 }}
              tickLine={{ stroke: '#e5e7eb' }}
              tickFormatter={(value) => `${(value / 1000).toFixed(0)}k`}
            />

            <Tooltip content={<CustomTooltip />} />

            <Area
              type="monotone"
              dataKey="actual"
              stroke="#3b82f6"
              strokeWidth={2}
              fill="url(#colorActual)"
              name="실제 주가"
            />

            <Area
              type="monotone"
              dataKey="predicted"
              stroke="#10b981"
              strokeWidth={2}
              strokeDasharray="5 5"
              fill="url(#colorPredicted)"
              name="예측 주가"
            />
          </AreaChart>
        </ResponsiveContainer>

        {tooltipData && (
          <div
            onClick={() => onReasonClick?.(tooltipData.data)}
            className="absolute bg-white p-6 rounded-xl shadow-2xl border-2 border-blue-500 max-w-lg z-10 cursor-pointer hover:shadow-3xl hover:border-blue-600 transition-all"
            style={{
              left: Math.min(Math.max(tooltipData.x - 200, 20), window.innerWidth - 450),
              top: tooltipData.y + 40,
            }}
          >
            <div className="flex items-center justify-between mb-4 pb-3 border-b-2 border-gray-200">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 rounded-lg">
                  {tooltipData.data.predicted !== undefined && tooltipData.data.actual !== undefined ? (
                    tooltipData.data.predicted > tooltipData.data.actual ? (
                      <TrendingUp className="text-green-600" size={24} />
                    ) : (
                      <TrendingDown className="text-red-600" size={24} />
                    )
                  ) : (
                    <TrendingUp className="text-blue-600" size={24} />
                  )}
                </div>

                <div>
                  <h4 className="font-bold text-gray-900 text-lg">예측 근거</h4>
                  <p className="text-sm text-gray-500">{formatTickLabel(tooltipData.data.date)}</p>
                </div>
              </div>

              <div className="flex items-center gap-2 text-blue-600 text-sm animate-pulse">
                <MousePointer size={16} />
                <span>클릭하여 상세보기</span>
              </div>
            </div>

            {tooltipData.data.changeReason && (
              <p className="text-base text-gray-800 mb-4 p-3 bg-blue-50 rounded-lg font-medium leading-relaxed">
                {tooltipData.data.changeReason}
              </p>
            )}

            {tooltipData.data.reason && (
              <div className="space-y-3">
                <h5 className="font-semibold text-gray-700 text-sm">주요 영향 요인</h5>

                {tooltipData.data.reason.map((r, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    <div
                      className={`mt-1 w-3 h-3 rounded-full flex-shrink-0 ${
                        r.contribution > 0 ? 'bg-green-500' : 'bg-red-500'
                      }`}
                    />

                    <div className="flex-1">
                      <p className="font-semibold text-gray-900 mb-1">{r.factor}</p>
                      <p className="text-sm text-gray-600 mb-2 leading-relaxed">{r.impact}</p>

                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${r.contribution > 0 ? 'bg-green-500' : 'bg-red-500'}`}
                            style={{ width: `${Math.min(Math.abs(r.contribution) * 10, 100)}%` }}
                          />
                        </div>

                        <span className={`text-sm font-bold ${r.contribution > 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {r.contribution > 0 ? '+' : ''}
                          {r.contribution}%
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {pastCount > MIN_WINDOW && sliderMax > 0 && (
        <div className="mt-4 px-1">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 whitespace-nowrap">2023~</span>

            <div className="relative flex-1">
              <input
                type="range"
                min={0}
                max={sliderMax}
                value={clampedSlider}
                onChange={(e) => setSliderValue(Number(e.target.value))}
                className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
                style={{
                  background: `linear-gradient(to right, #e5e7eb 0%, #e5e7eb ${
                    sliderMax > 0 ? (clampedSlider / sliderMax) * 100 : 0
                  }%, #3b82f6 ${sliderMax > 0 ? (clampedSlider / sliderMax) * 100 : 0}%, #3b82f6 100%)`,
                }}
              />
            </div>

            <span className="text-xs text-gray-400 whitespace-nowrap">최근+예측</span>
          </div>

          <div className="mt-1 text-[11px] text-gray-400">
            현재 표시: {visibleData.length}개 포인트 (오른쪽 끝 고정)
          </div>
        </div>
      )}
    </div>
  );
}

export type { ChartDataPoint };