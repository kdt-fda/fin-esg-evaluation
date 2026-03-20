import { TrendingUp, TrendingDown, Activity } from 'lucide-react';
import { Card } from '../ui/card';
import type { InterpretationSignal, SignalDirection, SignalStrength } from '../../types/interpretation';

export type SignalCardItem = InterpretationSignal;

interface SignalCardProps {
  item: SignalCardItem;
  isCompact?: boolean;
}

const getStatusConfig = (
  direction: SignalDirection,
  strength: SignalStrength
) => {
  const styles = {
    high: {
      positive: {
        bg: 'bg-orange-100',
        border: 'border-orange-400',
        text: 'text-orange-800',
        iconBg: 'bg-orange-200',
        icon: TrendingUp,
      },
      negative: {
        bg: 'bg-blue-100',
        border: 'border-blue-400',
        text: 'text-blue-800',
        iconBg: 'bg-blue-200',
        icon: TrendingDown,
      },
    },
    medium: {
      positive: {
        bg: 'bg-orange-50',
        border: 'border-orange-300',
        text: 'text-orange-700',
        iconBg: 'bg-orange-100',
        icon: TrendingUp,
      },
      negative: {
        bg: 'bg-blue-50',
        border: 'border-blue-300',
        text: 'text-blue-700',
        iconBg: 'bg-blue-100',
        icon: TrendingDown,
      },
    },
    low: {
      positive: {
        bg: 'bg-orange-50',
        border: 'border-orange-200',
        text: 'text-orange-600',
        iconBg: 'bg-orange-50',
        icon: Activity,
      },
      negative: {
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        text: 'text-blue-600',
        iconBg: 'bg-blue-50',
        icon: Activity,
      },
    },
  };

  return styles[strength][direction];
};

export default function SignalCard({
  item,
  isCompact = false,
}: SignalCardProps) {
  const config = getStatusConfig(item.direction, item.strength);
  const StatusIcon = config.icon;

  const formatShapValue = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '-';
    return value.toFixed(3);
  };

  return (
    <Card
      className={`p-3 border transition-all duration-300 hover:shadow-md ${
        isCompact ? config.bg : 'bg-white'
      } ${config.border}`}
    >
      {isCompact ? (
        <>
          <div className="flex items-start justify-between mb-3">
            <div className={`p-1.5 rounded ${config.iconBg}`}>
              <StatusIcon className={`h-4 w-4 ${config.text}`} />
            </div>

            <div className="text-right">
              <p className="text-[9px] text-gray-500 leading-none mb-1 tracking-tight">
                SHAP
              </p>
              <p className={`text-[14px] font-medium leading-none ${config.text}`}>
                {formatShapValue(item.shap_value)}
              </p>
            </div>
          </div>

          <h4 className="text-sm font-semibold mb-1.5 text-gray-900 leading-snug">
            {item.signal}
          </h4>
        </>
      ) : (
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-lg ${config.iconBg} shrink-0`}>
            <StatusIcon className={`h-5 w-5 ${config.text}`} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between mb-2 gap-3">
              <h4 className="text-[15px] font-semibold text-gray-900 leading-snug">
                {item.signal}
              </h4>

              <div className="text-right shrink-0">
                <p className="text-[9px] text-gray-500 leading-none mb-1 tracking-tight">
                  SHAP
                </p>
                <p className={`text-[14px] font-medium leading-none ${config.text}`}>
                  {formatShapValue(item.shap_value)}
                </p>
              </div>
            </div>

            <p className="text-sm text-gray-600 leading-relaxed">
              {item.reason}
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}