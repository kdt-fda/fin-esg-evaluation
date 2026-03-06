import {
  TrendingUp,
  ChevronUp,
  ChevronDown,
  Minus,
} from 'lucide-react';

interface ScoreProps {
  stockName: string;
  stockCode: string;
  basePrice: number;
}

interface ScenarioItem {
  label: string;
  prob: number;
  ret: number;
  icon: React.ReactNode;
  color: string;
  bg: string;
  border: string;
}

interface SignalItem {
  label: string;
  positive: boolean;
}

interface LongTermChartProps extends ScoreProps {
  confidence?: number;
  overallScore?: number;
  expectedReturn?: number;
  aiSummary?: string;
  scenarios?: ScenarioItem[];
  signals?: SignalItem[];
}

export default function LongTermChart({
  stockName,
  stockCode,
  basePrice,
  confidence = 78,
  overallScore = 74,
  expectedReturn = 18.4,
  aiSummary = '이 종목은 업종 효과와 재무 안정성 개선 요인이 긍정적으로 반영되며 상위권 기대수익 후보로 평가됩니다. 다만 외국인 수급 요인은 단기 변동성을 만들 가능성이 있습니다.',
  scenarios,
  signals,
}: LongTermChartProps) {
  const grade =
    overallScore >= 90 ? 'S' :
    overallScore >= 80 ? 'A' :
    overallScore >= 70 ? 'B+' :
    overallScore >= 60 ? 'B' :
    overallScore >= 50 ? 'C' : 'D';

  const targetPrice = Math.round(basePrice * (1 + expectedReturn / 100));

  const scenarioList: ScenarioItem[] = scenarios ?? [
    {
      label: '낙관 시나리오',
      prob: 30,
      ret: 31.2,
      icon: <ChevronUp size={16} />,
      color: '#10b981',
      bg: '#ecfdf5',
      border: '#a7f3d0',
    },
    {
      label: '기본 시나리오',
      prob: 50,
      ret: expectedReturn,
      icon: <Minus size={16} />,
      color: '#3b82f6',
      bg: '#eff6ff',
      border: '#bfdbfe',
    },
    {
      label: '비관 시나리오',
      prob: 20,
      ret: -4.1,
      icon: <ChevronDown size={16} />,
      color: '#ef4444',
      bg: '#fef2f2',
      border: '#fecaca',
    },
  ];

  const signalList: SignalItem[] = signals ?? [
    { label: 'PER 저평가', positive: true },
    { label: '매출 성장 지속', positive: true },
    { label: '부채비율 개선', positive: true },
    { label: '외국인 매도세', positive: false },
    { label: '업황 둔화 우려', positive: false },
  ];

  return (
    <div className="bg-white rounded-xl shadow-sm p-6 flex-1">
      {/* 헤더 */}
      <div className="mb-5">
        <h3 className="text-xl font-semibold text-gray-900 mb-1">
          중장기 성장 예측
        </h3>

        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">9개월 수익률 예측 모델</span>
          <span className="text-sm text-gray-300">·</span>
          <span className="text-sm text-gray-500">예측 신뢰도</span>
          <div className="flex items-center gap-2">
            <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  confidence >= 80
                    ? 'bg-green-500'
                    : confidence >= 60
                    ? 'bg-yellow-500'
                    : 'bg-red-500'
                }`}
                style={{ width: `${confidence}%` }}
              />
            </div>
            <span className="text-sm font-semibold text-gray-900">{confidence}%</span>
          </div>
        </div>
      </div>

      {/* 카드 1 : 핵심 수치 */}
      <div className="flex items-center gap-4 p-5 rounded-2xl bg-gradient-to-r from-blue-50 to-emerald-50 border border-blue-100 mb-5">
        <div className="text-center px-4 border-r border-blue-200 min-w-[120px]">
          <p className="text-xs text-gray-500 mb-1">종합 점수</p>
          <p className="text-4xl font-black text-blue-600 leading-none">
            {overallScore}
            <span className="text-base font-normal text-gray-400">/100</span>
          </p>
          <p className="mt-2 text-xs font-semibold text-blue-700">AI 등급 {grade}</p>
        </div>

        <div className="flex-1">
          <p className="text-xs text-gray-500 mb-1">기본 시나리오 수익률</p>
          <p className="text-4xl font-black text-emerald-600 leading-none">
            {expectedReturn > 0 ? '+' : ''}
            {expectedReturn}%
          </p>
          <p className="mt-2 text-sm text-gray-600">
            9개월 후 예측 · 목표가{' '}
            <span className="font-semibold text-gray-800">
              {targetPrice.toLocaleString()}원
            </span>
          </p>
        </div>

        <div className="w-14 h-14 rounded-full bg-emerald-100 flex items-center justify-center shrink-0">
          <TrendingUp className="text-emerald-600" size={26} />
        </div>
      </div>

      {/* 카드 2 : AI 분석 요약 */}
      <div className="p-4 rounded-xl border bg-white shadow-sm mb-5">
        <p className="text-xs font-semibold text-gray-600 mb-2">
          AI 분석 요약
        </p>
        <div className="text-sm text-gray-700 leading-relaxed">
          {aiSummary}
        </div>
      </div>

      {/* 카드 3 : 시나리오별 수익률 */}
      <div className="mb-5">
        <p className="text-xs font-semibold text-gray-600 mb-2">
          시나리오별 수익률 예측
        </p>

        <div className="space-y-2">
          {scenarioList.map((s) => (
            <div
              key={s.label}
              className="flex items-center gap-3 p-3 rounded-lg border"
              style={{
                backgroundColor: s.bg,
                borderColor: s.border,
              }}
            >
              <div className="flex items-center gap-1.5 w-28 shrink-0">
                <span style={{ color: s.color }}>{s.icon}</span>
                <span className="text-xs font-medium text-gray-700">
                  {s.label}
                </span>
              </div>

              <div className="flex-1 h-1.5 bg-white/70 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${s.prob}%`,
                    backgroundColor: s.color,
                  }}
                />
              </div>

              <span className="text-xs text-gray-500 w-8 shrink-0">
                {s.prob}%
              </span>

              <span
                className="text-sm font-bold w-16 text-right shrink-0"
                style={{ color: s.color }}
              >
                {s.ret > 0 ? '+' : ''}
                {s.ret}%
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 카드 4 : 주요 신호 */}
      <div className="p-4 rounded-xl border bg-white shadow-sm">
        <p className="text-xs font-semibold text-gray-600 mb-2">
          주요 신호
        </p>

        <div className="flex flex-wrap gap-2">
          {signalList.map((s) => (
            <div
              key={s.label}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${
                s.positive
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-red-50 text-red-600 border-red-200'
              }`}
            >
              {s.positive ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {s.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}