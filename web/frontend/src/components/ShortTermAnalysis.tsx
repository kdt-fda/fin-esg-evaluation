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

export default function ShortTermAnalysis({
  stockCode,
  summary = '',
  signals = [],
  isSidebarOpen = false,
}: ShortTermAnalysisProps) {
  const interpretationLoading = false;
  const interpretationError = null;

  const {
    turningPoints,
    loading: turningLoading,
    error: turningError,
  } = useTurningPoints(stockCode);

  return (
    <div className="space-y-2 transition-all duration-300">
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

      {isSidebarOpen && (
        <TurningPointsCard
          turningPoints={turningPoints}
          loading={turningLoading}
          error={turningError}
        />
      )}
    </div>
  );
}