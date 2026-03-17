import { useEffect, useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Activity,
  AlertCircle,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Zap,
} from 'lucide-react';
import { Card } from './ui/card';
import { Badge } from './ui/badge';

interface ShortTermAnalysisProps {
  stockName: string;
  stockCode: string;
  isSidebarOpen?: boolean;
}

type CardStatus = 'bullish' | 'bearish' | 'neutral' | 'caution';

interface AnalysisCard {
  key: string;
  title: string;
  status: CardStatus;
  badge: string;
  summary: string;
  value?: {
    ma5?: number;
    ma20?: number;
    rsi?: number;
    macd?: number;
    bb_upper?: number;
    bb_lower?: number;
    foreign?: string;
    institution?: string;
    change_pct?: number;
  };
}

interface TurningPoint {
  date: string;
  type: string;
  title: string;
  strength: 'high' | 'medium' | 'low';
  summary: string;
}

interface TurningPointsResponse {
  stock_name: string;
  ticker: string;
  as_of_date: string | null;
  turning_points: TurningPoint[];
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

const getMockAnalysisData = (_stockName: string, _stockCode: string) => {
  const cards: AnalysisCard[] = [
    {
      key: 'trend',
      title: '이동평균',
      status: 'bullish',
      badge: '골든크로스',
      summary: '최근 5거래일 내 5일선이 20일선을 상향 돌파해 단기 추세 개선 신호가 확인됐습니다.',
      value: {
        ma5: 69200,
        ma20: 67800,
      },
    },
    {
      key: 'momentum',
      title: '모멘텀',
      status: 'bullish',
      badge: 'RSI 58.3',
      summary: '현재 RSI가 과열 구간은 아니고 MACD도 우호적이어서 단기 모멘텀은 비교적 양호합니다.',
      value: {
        rsi: 58.3,
        macd: 0.42,
      },
    },
    {
      key: 'volatility',
      title: '볼린저밴드',
      status: 'neutral',
      badge: '중상단',
      summary: '현재 가격이 밴드 중상단에서 움직이고 있어 강세 우위이지만 아직 돌파 신호로 단정할 단계는 아닙니다.',
      value: {
        bb_upper: 71500,
        bb_lower: 66200,
      },
    },
    {
      key: 'flow',
      title: '수급',
      status: 'bullish',
      badge: '순매수',
      summary: '최근 5거래일 기준 외국인(+258억)과 기관(+142억) 수급이 모두 우호적이어서 단기 흐름을 지지합니다.',
      value: {
        foreign: '+258억',
        institution: '+142억',
      },
    },
  ];

  return { cards };
};

const getStatusConfig = (status: CardStatus) => {
  const configs = {
    bullish: {
      bg: 'bg-sky-50',
      border: 'border-sky-300',
      text: 'text-sky-700',
      iconBg: 'bg-sky-100',
      icon: TrendingUp,
      arrow: ArrowUpRight,
    },
    bearish: {
      bg: 'bg-rose-50',
      border: 'border-rose-300',
      text: 'text-rose-700',
      iconBg: 'bg-rose-100',
      icon: TrendingDown,
      arrow: ArrowDownRight,
    },
    neutral: {
      bg: 'bg-slate-50',
      border: 'border-slate-300',
      text: 'text-slate-700',
      iconBg: 'bg-slate-100',
      icon: Activity,
      arrow: Minus,
    },
    caution: {
      bg: 'bg-amber-50',
      border: 'border-amber-300',
      text: 'text-amber-700',
      iconBg: 'bg-amber-100',
      icon: AlertCircle,
      arrow: AlertCircle,
    },
  };

  return configs[status];
};

const getTurningPointStatus = (point: TurningPoint): CardStatus => {
  if (
    point.type === 'golden_cross' ||
    point.type === 'macd_cross_up' ||
    point.type === 'bb_upper_breakout'
  ) {
    return 'bullish';
  }

  if (
    point.type === 'death_cross' ||
    point.type === 'macd_cross_down' ||
    point.type === 'bb_lower_breakout'
  ) {
    return 'bearish';
  }

  if (point.type === 'msci_event') {
    return 'caution';
  }

  return 'neutral';
};

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr);
  return `${date.getMonth() + 1}/${date.getDate()}`;
};

export default function ShortTermAnalysis({
  stockName,
  stockCode,
  isSidebarOpen = false,
}: ShortTermAnalysisProps) {
  const data = getMockAnalysisData(stockName, stockCode);

  const [turningPoints, setTurningPoints] = useState<TurningPoint[]>([]);
  const [turningLoading, setTurningLoading] = useState(false);
  const [turningError, setTurningError] = useState<string | null>(null);

  useEffect(() => {
    if (!stockCode || stockCode === '-') {
      setTurningPoints([]);
      setTurningError(null);
      return;
    }

    const controller = new AbortController();

    const fetchTurningPoints = async () => {
      setTurningLoading(true);
      setTurningError(null);

      try {
        const res = await fetch(
          `${API_BASE}/api/stocks/${encodeURIComponent(stockCode)}/turning-points`,
          { signal: controller.signal }
        );

        if (!res.ok) {
          throw new Error(await res.text());
        }

        const json = (await res.json()) as TurningPointsResponse;
        setTurningPoints(json.turning_points ?? []);
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
        console.error(err);
        setTurningError(err?.message ?? '변곡점 데이터를 불러오지 못했습니다.');
        setTurningPoints([]);
      } finally {
        setTurningLoading(false);
      }
    };

    fetchTurningPoints();

    return () => controller.abort();
  }, [stockCode]);

  const sortedTurningPoints = [...turningPoints].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
  );

  return (
    <div className="space-y-2 transition-all duration-300">
      <div
        className={`grid gap-2.5 transition-all duration-300 ${
          isSidebarOpen ? 'grid-cols-4' : 'grid-cols-1'
        }`}
      >
        {data.cards.map((card) => {
          const config = getStatusConfig(card.status);
          const StatusIcon = config.icon;
          const ArrowIcon = config.arrow;

          return (
            <Card
              key={card.key}
              className={`p-3 border transition-all duration-300 hover:shadow-md ${
                isSidebarOpen ? config.bg : 'bg-white'
              } ${config.border}`}
            >
              {isSidebarOpen && (
                <>
                  <div className="flex items-start justify-between mb-3">
                    <div className={`p-1.5 rounded ${config.iconBg}`}>
                      <StatusIcon className={`h-4 w-4 ${config.text}`} />
                    </div>
                    <ArrowIcon className={`h-4 w-4 ${config.text}`} />
                  </div>

                  <h4 className="text-sm font-semibold mb-2 text-gray-900">{card.title}</h4>

                  <Badge
                    variant="outline"
                    className={`text-xs ${config.bg} ${config.text} border ${config.border}`}
                  >
                    {card.badge}
                  </Badge>
                </>
              )}

              {!isSidebarOpen && (
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${config.iconBg} shrink-0`}>
                    <StatusIcon className={`h-5 w-5 ${config.text}`} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-2 gap-3">
                      <h4 className="font-semibold text-gray-900">{card.title}</h4>

                      <Badge
                        variant="outline"
                        className={`shrink-0 ${config.bg} ${config.text} border ${config.border}`}
                      >
                        {card.badge}
                      </Badge>
                    </div>

                    <p className="text-sm text-gray-600 leading-relaxed mb-2">
                      {card.summary}
                    </p>

                    {card.value && (
                      <div className="pt-2 border-t border-gray-100">
                        <div className="flex flex-wrap gap-3 text-xs">
                          {card.key === 'trend' && (
                            <>
                              <div>
                                <span className="text-gray-500">MA5: </span>
                                <span className="font-medium text-gray-900">
                                  {card.value.ma5?.toLocaleString()}원
                                </span>
                              </div>
                              <div>
                                <span className="text-gray-500">MA20: </span>
                                <span className="font-medium text-gray-900">
                                  {card.value.ma20?.toLocaleString()}원
                                </span>
                              </div>
                            </>
                          )}

                          {card.key === 'momentum' && (
                            <>
                              <div>
                                <span className="text-gray-500">RSI: </span>
                                <span className="font-medium text-gray-900">{card.value.rsi}</span>
                              </div>
                              <div>
                                <span className="text-gray-500">MACD: </span>
                                <span className="font-medium text-gray-900">{card.value.macd}</span>
                              </div>
                            </>
                          )}

                          {card.key === 'volatility' && (
                            <>
                              <div>
                                <span className="text-gray-500">상단: </span>
                                <span className="font-medium text-gray-900">
                                  {card.value.bb_upper?.toLocaleString()}
                                </span>
                              </div>
                              <div>
                                <span className="text-gray-500">하단: </span>
                                <span className="font-medium text-gray-900">
                                  {card.value.bb_lower?.toLocaleString()}
                                </span>
                              </div>
                            </>
                          )}

                          {card.key === 'flow' && (
                            <>
                              <div>
                                <span className="text-gray-500">외국인: </span>
                                <span
                                  className={`font-medium ${
                                    (card.value.foreign ?? '').startsWith('-')
                                      ? 'text-rose-600'
                                      : 'text-sky-600'
                                  }`}
                                >
                                  {card.value.foreign}
                                </span>
                              </div>
                              <div>
                                <span className="text-gray-500">기관: </span>
                                <span
                                  className={`font-medium ${
                                    (card.value.institution ?? '').startsWith('-')
                                      ? 'text-rose-600'
                                      : 'text-sky-600'
                                  }`}
                                >
                                  {card.value.institution}
                                </span>
                              </div>
                            </>
                          )}

                          {card.key === 'volume' && (
                            <div>
                              <span className="text-gray-500">증감률: </span>
                              <span
                                className={`font-medium ${
                                  (card.value.change_pct ?? 0) > 0
                                    ? 'text-sky-600'
                                    : 'text-rose-600'
                                }`}
                              >
                                {(card.value.change_pct ?? 0) > 0 ? '+' : ''}
                                {card.value.change_pct}%
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {isSidebarOpen && (
        <Card className="p-4 bg-white border-slate-200 transition-all duration-300">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-4 w-4 text-slate-600" />
            <h4 className="text-sm font-semibold text-gray-900">최근 주요 변곡점</h4>
          </div>

          {turningLoading && (
            <p className="text-xs text-slate-500">변곡점 데이터를 불러오는 중...</p>
          )}

          {!turningLoading && turningError && (
            <p className="text-xs text-rose-600">{turningError}</p>
          )}

          {!turningLoading && !turningError && sortedTurningPoints.length === 0 && (
            <p className="text-xs text-slate-500">
              최근 구간에서 감지된 주요 변곡점이 없습니다.
            </p>
          )}

          {!turningLoading && !turningError && sortedTurningPoints.length > 0 && (
            <div className="relative">
              <div className="absolute left-[7px] top-2 bottom-2 w-0.5 bg-slate-200" />

              <div className="space-y-4">
                {sortedTurningPoints.map((point, index) => {
                  const pointStatus = getTurningPointStatus(point);
                  const config = getStatusConfig(pointStatus);

                  return (
                    <div key={`${point.date}-${point.type}-${index}`} className="relative pl-7">
                      <div
                        className={`absolute left-0 top-2 h-4 w-4 rounded-full border-2 border-white shadow-sm ${config.iconBg}`}
                      >
                        <div className={`h-full w-full rounded-full ${config.bg.replace('50', '400')}`} />
                      </div>

                      <div>
                        <div
                          className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 border ${config.bg} ${config.border} mb-2`}
                        >
                          <span className={`text-[11px] font-medium ${config.text}`}>
                            {formatDate(point.date)}
                          </span>
                          <span className="text-slate-300">•</span>
                          <span className={`text-xs font-semibold ${config.text}`}>
                            {point.title}
                          </span>
                        </div>

                        <p className="text-xs leading-relaxed text-slate-600 pl-1">
                          {point.summary}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Card>
      )}

      <Card className="p-3 bg-slate-50 border-slate-200">
        <div className="flex items-start gap-2">
          <AlertCircle className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />
          <p className="text-xs text-slate-600 leading-relaxed">
            {!isSidebarOpen &&
              ' 사이드바가 열려 있을 때는 핵심 카드와 최근 주요 변곡점을 요약해 보여줍니다.'}
            {isSidebarOpen &&
              ' 사이드바를 닫으면 각 기술적 지표의 설명과 세부 수치를 더 자세히 확인할 수 있습니다.'}
          </p>
        </div>
      </Card>
    </div>
  );
}