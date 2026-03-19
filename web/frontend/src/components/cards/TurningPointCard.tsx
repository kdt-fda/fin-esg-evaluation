import { Zap } from 'lucide-react';
import { Card } from '../ui/card';
import type { SignalDirection, SignalStrength } from '../../types/interpretation';
import type { TurningPoint } from '../../types/turningpoint';

export type { TurningPoint };

interface TurningPointsCardProps {
  turningPoints?: TurningPoint[];
  loading?: boolean;
  error?: string | null;
}

const getTurningPointStatusConfig = (
  direction: SignalDirection,
  strength: SignalStrength
) => {
  const strengthStyle = {
    high: {
      positive: {
        bg: 'bg-orange-100',
        border: 'border-orange-400',
        text: 'text-orange-800',
        iconBg: 'bg-orange-200',
      },
      negative: {
        bg: 'bg-blue-100',
        border: 'border-blue-400',
        text: 'text-blue-800',
        iconBg: 'bg-blue-200',
      },
    },
    medium: {
      positive: {
        bg: 'bg-orange-50',
        border: 'border-orange-300',
        text: 'text-orange-700',
        iconBg: 'bg-orange-100',
      },
      negative: {
        bg: 'bg-blue-50',
        border: 'border-blue-300',
        text: 'text-blue-700',
        iconBg: 'bg-blue-100',
      },
    },
    low: {
      positive: {
        bg: 'bg-orange-50',
        border: 'border-orange-200',
        text: 'text-orange-600',
        iconBg: 'bg-orange-50',
      },
      negative: {
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        text: 'text-blue-600',
        iconBg: 'bg-blue-50',
      },
    },
  };

  return strengthStyle[strength][direction];
};

const getTurningPointSignal = (point: TurningPoint): {
  direction: SignalDirection;
  strength: SignalStrength;
} => {
  if (
    point.type === 'golden_cross' ||
    point.type === 'macd_cross_up' ||
    point.type === 'bb_upper_breakout'
  ) {
    return { direction: 'positive', strength: 'high' };
  }

  if (
    point.type === 'death_cross' ||
    point.type === 'macd_cross_down' ||
    point.type === 'bb_lower_breakout'
  ) {
    return { direction: 'negative', strength: 'high' };
  }

  if (point.type === 'msci_event') {
    return { direction: 'negative', strength: 'medium' };
  }

  return { direction: 'negative', strength: 'low' };
};

const formatDate = (dateStr: string) => {
  const date = new Date(dateStr);
  return `${date.getMonth() + 1}/${date.getDate()}`;
};

export default function TurningPointsCard({
  turningPoints = [],
  loading = false,
  error = null,
}: TurningPointsCardProps) {
  const sortedTurningPoints = [...turningPoints].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
  );

  return (
    <Card className="p-4 bg-white border-slate-200 transition-all duration-300">
      <div className="flex items-center gap-2 mb-4">
        <Zap className="h-4 w-4 text-slate-600" />
        <h4 className="text-sm font-semibold text-gray-900">최근 주요 변곡점</h4>
      </div>

      {loading && (
        <p className="text-xs text-slate-500">변곡점 데이터를 불러오는 중...</p>
      )}

      {!loading && error && (
        <p className="text-xs text-rose-600">{error}</p>
      )}

      {!loading && !error && sortedTurningPoints.length === 0 && (
        <p className="text-xs text-slate-500">
          최근 구간에서 감지된 주요 변곡점이 없습니다.
        </p>
      )}

      {!loading && !error && sortedTurningPoints.length > 0 && (
        <div className="relative">
          <div className="absolute left-[7px] top-2 bottom-2 w-0.5 bg-slate-200" />

          <div className="space-y-4">
            {sortedTurningPoints.map((point, index) => {
              const { direction, strength } = getTurningPointSignal(point);
              const config = getTurningPointStatusConfig(direction, strength);

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
  );
}