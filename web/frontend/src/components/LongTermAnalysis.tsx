import { useMemo, useState } from 'react';
import SummaryCard from './cards/SummaryCard';
import SignalCard from './cards/SignalCard';
import PositioningCard from './cards/PositioningCard';
import { Card } from './ui/card';
import type { LongTermItem } from '../types/chart';
import type { InterpretationSignal } from '../types/interpretation';

interface LongTermAnalysisProps {
  stockName: string;
  stockCode: string;
  currentSector: string;
  data?: LongTermItem[];
  summary?: string;
  signals?: InterpretationSignal[];
  isSidebarOpen?: boolean;
}

type TabType = 'ai' | 'chart';

export default function LongTermAnalysis({
  stockCode,
  currentSector,
  data,
  summary = '',
  signals = [],
  isSidebarOpen = false,
}: LongTermAnalysisProps) {
  const [activeTab, setActiveTab] = useState<TabType>('ai');

  const loading = false;
  const errorMsg = null;

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
    <div className="space-y-3 transition-all duration-300">
      <div className="flex items-center gap-2">
        <button
          onClick={() => setActiveTab('ai')}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
            activeTab === 'ai'
              ? 'bg-blue-500 text-white shadow-sm'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          AI 해석
        </button>

        <button
          onClick={() => setActiveTab('chart')}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
            activeTab === 'chart'
              ? 'bg-blue-500 text-white shadow-sm'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          차트 해석
        </button>
      </div>

      {activeTab === 'ai' && (
        <>
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
        </>
      )}

      {activeTab === 'chart' && (
        <PositioningCard
          currentSector={currentSector}
          totalCompanies={sectorPosition.totalCompanies}
          currentRank={sectorPosition.currentRank}
          topPercent={sectorPosition.topPercent}
        />
      )}
    </div>
  );
}