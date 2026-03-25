import { useState } from 'react';
import { Card } from './ui/card';
import SummaryCard from './cards/SummaryCard';
import SignalCard from './cards/SignalCard';
import TurningPointsCard from './cards/TurningPointCard';
import useTurningPoints from '../hooks/useTurningPoint';
import type { InterpretationSignal } from '../types/interpretation';

interface ShortTermAnalysisProps {
  stockName: string;
  stockCode: string;
  summary?: string;
  signals?: InterpretationSignal[];
  isSidebarOpen?: boolean;
}

type TabType = 'ai' | 'chart';

export default function ShortTermAnalysis({
  stockCode,
  summary = '',
  signals = [],
  isSidebarOpen = false,
}: ShortTermAnalysisProps) {
  const [activeTab, setActiveTab] = useState<TabType>('ai');

  const interpretationLoading = false;
  const interpretationError = null;

  const {
    turningPoints,
    loading: turningLoading,
    error: turningError,
  } = useTurningPoints(stockCode);

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
            loading={interpretationLoading}
            error={interpretationError}
            emptyMessage="아직 단기 AI 해석 데이터가 없습니다."
          />

          <div
            className={`grid gap-2.5 overflow-visible transition-all duration-300 ${
              isSidebarOpen ? 'grid-cols-6' : 'grid-cols-1'
            }`}
          >
            {!interpretationLoading && !interpretationError && signals.length === 0 && (
              <Card className="col-span-full border-gray-200 bg-white p-4">
                <p className="text-sm text-gray-400">아직 단기 주요 신호 데이터가 없습니다.</p>
              </Card>
            )}

            {!interpretationLoading &&
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
        <TurningPointsCard
          turningPoints={turningPoints}
          loading={turningLoading}
          error={turningError}
        />
      )}
    </div>
  );
}