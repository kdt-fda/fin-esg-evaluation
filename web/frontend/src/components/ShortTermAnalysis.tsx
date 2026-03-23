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
      <div className="inline-flex items-center rounded-2xl border border-white/60 bg-white/70 p-1 shadow-sm backdrop-blur-md">
        <button
          onClick={() => setActiveTab('ai')}
          className={`rounded-xl px-4 py-2 text-sm font-medium tracking-tight transition-all duration-200 ${
            activeTab === 'ai'
              ? 'bg-white text-gray-900 shadow-[0_1px_2px_rgba(0,0,0,0.08),0_6px_18px_rgba(0,0,0,0.06)]'
              : 'text-gray-500 hover:bg-white/60 hover:text-gray-700'
          }`}
        >
          <span className="flex items-center gap-1.5">
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 3l1.9 3.8L18 8.7l-3 2.9.7 4.1L12 13.8 8.3 15.7 9 11.6 6 8.7l4.1-.9L12 3z" />
            </svg>
            AI 해석
          </span>
        </button>

        <button
          onClick={() => setActiveTab('chart')}
          className={`rounded-xl px-4 py-2 text-sm font-medium tracking-tight transition-all duration-200 ${
            activeTab === 'chart'
              ? 'bg-white text-gray-900 shadow-[0_1px_2px_rgba(0,0,0,0.08),0_6px_18px_rgba(0,0,0,0.06)]'
              : 'text-gray-500 hover:bg-white/60 hover:text-gray-700'
          }`}
        >
          <span className="flex items-center gap-1.5">
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 19h16" />
              <path d="M7 15l3-3 3 2 4-5" />
              <circle cx="7" cy="15" r="1" fill="currentColor" stroke="none" />
              <circle cx="10" cy="12" r="1" fill="currentColor" stroke="none" />
              <circle cx="13" cy="14" r="1" fill="currentColor" stroke="none" />
              <circle cx="17" cy="9" r="1" fill="currentColor" stroke="none" />
            </svg>
            차트 해석
          </span>
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