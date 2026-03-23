import { useMemo } from 'react';
import SummaryCard from './cards/SummaryCard';
import SignalCard from './cards/SignalCard';
import PositioningCard from './cards/PositioningCard';
import { Card } from './ui/card';
import useInterpretation from '../hooks/useInterpretation';
import type { LongTermItem } from '../types/chart';

interface LongTermAnalysisProps {
  stockName: string;
  stockCode: string;
  currentSector: string;
  data?: LongTermItem[];
  isSidebarOpen?: boolean;
}

export default function LongTermAnalysis({
  stockCode,
  currentSector,
  data,
  isSidebarOpen = false,
}: LongTermAnalysisProps) {
  const {
    summary,
    signals,
    loading,
    error: errorMsg,
  } = useInterpretation(stockCode, 'long');

  const sectorPosition = useMemo(() => {
    if (!data || data.length === 0) {
      return {
        totalCompanies: 0,
        currentRank: 0,
        topPercent: 0,
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

    return {
      totalCompanies,
      currentRank,
      topPercent,
    };
  }, [data, stockCode]);

  return (
    <div className="space-y-2 transition-all duration-300">
      <SummaryCard
        summary={summary}
        loading={loading}
        error={errorMsg}
        emptyMessage="아직 중장기 AI 해석 데이터가 없습니다."
      />

      <div
        className={`grid gap-2.5 overflow-visible transition-all duration-300 ${
          isSidebarOpen ? 'grid-cols-6' : 'grid-cols-1'
        }`}
      >
        {loading && (
          <Card className="col-span-full border-gray-200 bg-white p-4">
            <p className="text-sm text-gray-500">중장기 주요 신호를 불러오는 중...</p>
          </Card>
        )}

        {!loading && !errorMsg && signals.length === 0 && (
          <Card className="col-span-full border-gray-200 bg-white p-4">
            <p className="text-sm text-gray-400">아직 중장기 주요 신호 데이터가 없습니다.</p>
          </Card>
        )}

        {!loading &&
          signals.map((signal, index) => (
            <SignalCard
              key={`${signal.feature}-${index}`}
              item={signal}
              isCompact={isSidebarOpen}
            />
          ))}
      </div>

      <PositioningCard
        currentSector={currentSector}
        totalCompanies={sectorPosition.totalCompanies}
        currentRank={sectorPosition.currentRank}
        topPercent={sectorPosition.topPercent}
      />
    </div>
  );
}