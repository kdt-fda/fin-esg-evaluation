import { useMemo } from 'react';
import { ArrowUp, ArrowDown, Trophy } from 'lucide-react';
import { Badge } from './ui/badge';
import { Card } from './ui/card';

interface LongTermItem {
  code: string;
  name: string;
  sector: string;
  score: number;
}

interface LongTermAnalysisProps {
  stockName: string;
  stockCode: string;
  currentSector: string;
  data?: LongTermItem[];
  isExpanded?: boolean;
}

interface SignalItem {
  label: string;
  value: string;
  impact: string;
}

const getMockShapSignals = (_stockName: string, _stockCode: string) => ({
  positiveSignals: [
    { label: 'ROE', value: '15.2%', impact: '+8.5' },
    { label: '영업이익률', value: '12.8%', impact: '+7.2' },
    { label: 'PER 저평가', value: '12.5배', impact: '+6.8' },
    { label: '현금비율', value: '145%', impact: '+6.5' },
    { label: '매출성장', value: '18.5%', impact: '+5.9' },
    { label: 'R&D 투자', value: '8.2조', impact: '+5.3' },
  ] as SignalItem[],
  negativeSignals: [
    { label: '부채비율', value: '45.2%', impact: '-4.2' },
    { label: '외국인지분', value: '52.3%', impact: '-3.8' },
    { label: '업종 변동성', value: '높음', impact: '-2.9' },
  ] as SignalItem[],
  summary:
    '수익성과 성장성 지표가 우수해 섹터 내 상위권 투자 매력도를 보이고 있으나, 일부 재무 안정성 및 외부 수급 요인은 점검이 필요합니다.',
});

export default function LongTermAnalysis({
  stockName,
  stockCode,
  currentSector,
  data,
  isExpanded = false,
}: LongTermAnalysisProps) {
  const shapData = getMockShapSignals(stockName, stockCode);

  const sectorPosition = useMemo(() => {
    if (!data || data.length === 0) {
      return {
        totalCompanies: 0,
        currentRank: 0,
        topPercent: 0,
        avgScore: 0,
      };
    }

    const sorted = [...data].sort((a, b) => b.score - a.score);
    const selectedIndex = sorted.findIndex((item) => item.code === stockCode);

    const totalCompanies = sorted.length;
    const currentRank = selectedIndex >= 0 ? selectedIndex + 1 : 0;

    const topPercent =
      currentRank > 0 && totalCompanies > 0
        ? Math.round((currentRank / totalCompanies) * 100)
        : 0;

    const avgScore =
      totalCompanies > 0
        ? data.reduce((sum, item) => sum + item.score, 0) / totalCompanies
        : 0;

    return {
      totalCompanies,
      currentRank,
      topPercent,
      avgScore,
    };
  }, [data, stockCode]);

  return (
    <div className="space-y-4 transition-all duration-300">
      <Card className="p-4 border-sky-200 bg-gradient-to-br from-sky-50 to-cyan-50">
        <div className="flex items-start gap-2.5">
          <div className="p-1.5 rounded-lg bg-sky-100 shrink-0">
            <Trophy className="h-5 w-5 text-sky-600" />
          </div>

          <div className="flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-900 mb-1">섹터 내 포지셔닝</h3>
            <p className="text-sm text-slate-600 mb-3">
              {currentSector} {sectorPosition.totalCompanies}개 기업 중
              투자 매력도 기준 위치입니다.
            </p>

            <div className="flex items-center gap-4">
              <div>
                <p className="text-xs text-slate-500 mb-1">순위</p>
                <p className="text-xl font-bold text-sky-700">
                  {sectorPosition.currentRank > 0 ? `${sectorPosition.currentRank}위` : '-'}
                </p>
              </div>

              <div className="h-10 w-px bg-sky-200" />

              <div>
                <p className="text-xs text-slate-500 mb-1">상위</p>
                <p className="text-xl font-bold text-cyan-700">
                  {sectorPosition.topPercent > 0 ? `${sectorPosition.topPercent}%` : '-'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-3.5 bg-white border-gray-200">
        <h3 className="text-sm font-semibold text-gray-900 mb-2">AI 종합 해석</h3>
        <p className="text-sm text-gray-600 leading-snug">
          {shapData.summary}
        </p>
      </Card>

      <Card className="p-4 bg-white border-gray-200">
        <h3 className="text-sm font-semibold text-gray-900 mb-3">주요 신호 (SHAP 분석)</h3>

        {!isExpanded && (
          <div className="space-y-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <ArrowUp className="h-4 w-4 text-sky-600" />
                <span className="text-sm font-medium text-sky-700">긍정적 신호</span>
              </div>

              <div className="flex flex-wrap gap-2">
                {shapData.positiveSignals.map((signal, index) => (
                  <Badge
                    key={`positive-${index}`}
                    variant="outline"
                    className="px-3 py-2 bg-sky-50 border-sky-300 text-sky-700"
                  >
                    <ArrowUp className="h-3 w-3 mr-1" />
                    <span className="font-semibold">{signal.label}</span>
                    <span className="mx-2 text-sky-900">{signal.value}</span>
                    <span className="text-xs font-semibold text-sky-600">{signal.impact}</span>
                  </Badge>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-2">
                <ArrowDown className="h-4 w-4 text-rose-600" />
                <span className="text-sm font-medium text-rose-700">부정적 신호</span>
              </div>

              <div className="flex flex-wrap gap-2">
                {shapData.negativeSignals.map((signal, index) => (
                  <Badge
                    key={`negative-${index}`}
                    variant="outline"
                    className="px-3 py-2 bg-rose-50 border-rose-300 text-rose-700"
                  >
                    <ArrowDown className="h-3 w-3 mr-1" />
                    <span className="font-semibold">{signal.label}</span>
                    <span className="mx-2 text-rose-900">{signal.value}</span>
                    <span className="text-xs font-semibold text-rose-600">{signal.impact}</span>
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}

        {isExpanded && (
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <ArrowUp className="h-4 w-4 text-sky-600" />
                <span className="text-sm font-medium text-sky-700">긍정적 신호</span>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {shapData.positiveSignals.map((signal, index) => (
                  <Badge
                    key={`positive-expanded-${index}`}
                    variant="outline"
                    className="px-2.5 py-1.5 bg-sky-50 border-sky-300 text-sky-700"
                  >
                    <ArrowUp className="h-3 w-3 mr-1" />
                    <span className="font-semibold">{signal.label}</span>
                    <span className="mx-2 text-sky-900">{signal.value}</span>
                    <span className="text-xs font-semibold text-sky-600">{signal.impact}</span>
                  </Badge>
                ))}
              </div>
            </div>

            <div>
              <div className="flex items-center gap-2 mb-3">
                <ArrowDown className="h-4 w-4 text-rose-600" />
                <span className="text-sm font-medium text-rose-700">부정적 신호</span>
              </div>

              <div className="flex flex-wrap gap-2">
                {shapData.negativeSignals.map((signal, index) => (
                  <Badge
                    key={`negative-expanded-${index}`}
                    variant="outline"
                    className="px-2.5 py-1.5 bg-rose-50 border-rose-300 text-rose-700"
                  >
                    <ArrowDown className="h-3 w-3 mr-1" />
                    <span className="font-semibold">{signal.label}</span>
                    <span className="mx-2 text-rose-900">{signal.value}</span>
                    <span className="text-xs font-semibold text-rose-600">{signal.impact}</span>
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}