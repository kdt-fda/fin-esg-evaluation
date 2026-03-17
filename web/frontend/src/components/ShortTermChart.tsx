import { useMemo, useState } from 'react';
import { Area, AreaChart, CartesianGrid, Tooltip, ResponsiveContainer, XAxis, YAxis} from 'recharts';
import { Info, X } from 'lucide-react';

interface PredictionReason {
  factor: string;
  impact: string;
  contribution: number;
}

interface ChartDataPoint {
  date: string;
  actual?: number;
  predicted?: number;
  reason?: PredictionReason[];
  changeReason?: string;
}

interface ShortTermPredictionChartProps {
  title: string;
  data: ChartDataPoint[];
  confidence: number;
  pastCount?: number;
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
}: ShortTermPredictionChartProps) {
  const MIN_WINDOW = 30;
  const [sliderValue, setSliderValue] = useState(999999);
  const [showInfoModal, setShowInfoModal] = useState(false);

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

  const tickInterval = useMemo(() => {
    const n = visibleData.length;

    if (n <= 60) return Math.max(0, Math.floor(n / 6));
    if (n <= 250) return Math.max(0, Math.floor(n / 8));

    return Math.max(0, Math.floor(n / 10));
  }, [visibleData.length]);

  const normalizedConfidence = useMemo(() => {
    if (!Number.isFinite(confidence)) return 0;
    return Math.max(0, Math.min(100, Number(confidence.toFixed(1))));
  }, [confidence]);



  const axisMeta = useMemo(() => {
    const ticks = new Set<string>();
    const yearMarkers = new Set<string>();

    visibleData.forEach((item, index) => {
      const currentYear = getYear(item.date);
      const previousYear =
        index > 0 ? getYear(visibleData[index - 1].date) : null;

      // 기본 날짜 tick
      if (index % (tickInterval + 1) === 0) {
        ticks.add(item.date);
      }

      // 연도 시작 지점 tick
      if (currentYear !== null && (index === 0 || currentYear !== previousYear)) {
        ticks.add(item.date);
        yearMarkers.add(item.date);
      }
    });

    const displayTicks = Array.from(ticks).sort(
      (a, b) => new Date(a).getTime() - new Date(b).getTime()
    );

    return {
      displayTicks,
      yearMarkers,
    };
  }, [visibleData, tickInterval]);


  const CustomXAxisTick = ({ x, y, payload }: any) => {
    const value: string = payload?.value ?? '';
    const label = formatTickLabel(value);

    const isYearMarker =
      spansMultipleYears && axisMeta.yearMarkers.has(value);

    const yearText = getYear(value);

    return (
      <g>
        {/* 연도 시작 지점이면 날짜 대신 연도만 아래에 표시 */}
        {!isYearMarker && (
          <text
            x={x}
            y={y + 12}
            textAnchor="middle"
            fill="#6b7280"
            fontSize={11}
          >
            {label}
          </text>
        )}

        {isYearMarker && yearText && (
          <text
            x={x}
            y={y + 26}
            textAnchor="middle"
            fill="#9ca3af"
            fontSize={10}
          >
            {yearText}
          </text>
        )}
      </g>
    );
  };


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
                    normalizedConfidence >= 80 ? 'bg-green-500' : normalizedConfidence >= 60 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${normalizedConfidence}%` }}
                />
              </div>
              <span className="text-sm font-semibold text-gray-900">{confidence}%</span>
            </div>
          </div>
        </div>

        <Info
          className="text-gray-400 cursor-pointer hover:text-blue-600 transition-colors"
          size={20}
          onClick={() => setShowInfoModal(true)}
        />
      </div>

      <div className="relative">
        <ResponsiveContainer width="100%" height={spansMultipleYears ? 330 : 300}>
          <AreaChart data={visibleData}>
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
              ticks = {axisMeta.displayTicks}
              tickLine={{ stroke: '#e5e7eb' }}
              interval={0}
              height={spansMultipleYears ? 48 : 25}
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

          <div className="mt-3 flex items-center justify-between gap-4">
            <div className="flex items-center gap-5">
              <div className="flex items-center gap-2 text-gray-700">
                <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                <span className="text-sm">실제 주가</span>
              </div>

              <div className="flex items-center gap-2 text-gray-700">
                <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                <span className="text-sm">예측 주가</span>
              </div>
            </div>

            <div className="text-xs text-gray-400 whitespace-nowrap">
              차트에 마우스를 올려 예측값을 확인하세요.
            </div>
          </div>
        </div>
      )}

      {showInfoModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          onClick={() => setShowInfoModal(false)}
        >
          <div
            className="mx-4 w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center justify-between">
              <h4 className="text-lg font-bold text-gray-900">단기 예측 차트 정보</h4>
              <button
                type="button"
                onClick={() => setShowInfoModal(false)}
                className="text-gray-400 transition-colors hover:text-gray-600"
                aria-label="닫기"
              >
                <X size={22} />
              </button>
            </div>

            <div className="space-y-4 text-sm leading-6 text-gray-700">
              <div>
                <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <div className="w-1 h-4 bg-blue-500 rounded-full"></div>
                  차트 개요
                </h5>
                <p>
                  이 차트는 향후 20 영업일까지의 주가 변동을 예측합니다. 과거 3년간의 주가 데이터를 기반으로 단기 변동성 요인을 분석하여 일별 예측값을 제공합니다.
                </p>
              </div>

              <div>
                <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <div className="w-1 h-4 bg-green-500 rounded-full"></div>
                  예측 신뢰도: {normalizedConfidence}%
                </h5>
                <p>
                  예측 신뢰도는 방향 적중률과 가격 오차를 함께 반영한 점수입니다.
                </p>
              </div>

              <div>
                <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <div className="w-1 h-4 bg-purple-500 rounded-full"></div>
                  주요 분석 요소
                </h5>
                <ul className="list-disc space-y-1 pl-5">
                  <li>주가 기본 흐름: 시가, 고가, 저가, 종가, 거래량</li>
                  <li>추세 지표: 5일·20일 이동평균선, 골든크로스, 데드크로스</li>
                  <li>수급 지표: 외국인·기관·개인 순매수 금액</li>
                  <li>기술적 지표: RSI, MACD, MACD 시그널</li>
                  <li>변동성 지표: 볼린저밴드 상단/하단, 밴드 돌파 여부</li>
                  <li>외부 변수: 나스닥 지수, 원/달러 환율, 유가(WTI)</li>
                  <li>이벤트 변수: MSCI 리밸런싱 여부, 공매도 잔고</li>
                </ul>
              </div>

              <div className="border-t border-gray-200 pt-4">
                <p className="text-xs text-gray-500">
                  💡 차트에 마우스를 올리면 해당 시점의 실제값과 예측값을 확인할 수 있습니다.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export type { ChartDataPoint };