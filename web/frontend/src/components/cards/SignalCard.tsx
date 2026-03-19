import {
  TrendingUp,
  TrendingDown,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-react';
import { Card } from '../ui/card';
import type {
  InterpretationSignal,
  SignalDirection,
  SignalStrength,
} from '../../types/interpretation';

export type SignalCardItem = InterpretationSignal;

interface SignalCardProps {
  item: SignalCardItem;
  isCompact?: boolean;
  featureValue?: number | string | null;
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
        arrow: ArrowUpRight,
      },
      negative: {
        bg: 'bg-blue-100',
        border: 'border-blue-400',
        text: 'text-blue-800',
        iconBg: 'bg-blue-200',
        icon: TrendingDown,
        arrow: ArrowDownRight,
      },
    },
    medium: {
      positive: {
        bg: 'bg-orange-50',
        border: 'border-orange-300',
        text: 'text-orange-700',
        iconBg: 'bg-orange-100',
        icon: TrendingUp,
        arrow: ArrowUpRight,
      },
      negative: {
        bg: 'bg-blue-50',
        border: 'border-blue-300',
        text: 'text-blue-700',
        iconBg: 'bg-blue-100',
        icon: TrendingDown,
        arrow: ArrowDownRight,
      },
    },
    low: {
      positive: {
        bg: 'bg-orange-50',
        border: 'border-orange-200',
        text: 'text-orange-600',
        iconBg: 'bg-orange-50',
        icon: Activity,
        arrow: Minus,
      },
      negative: {
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        text: 'text-blue-600',
        iconBg: 'bg-blue-50',
        icon: Activity,
        arrow: Minus,
      },
    },
  };

  return styles[strength][direction];
};

export default function SignalCard({
  item,
  isCompact = false,
  featureValue,
}: SignalCardProps) {
  const config = getStatusConfig(item.direction, item.strength);
  const StatusIcon = config.icon;
  const ArrowIcon = config.arrow;

  const formatFeatureValue = (value: number | string | null | undefined) => {
    if (value === null || value === undefined) return '-';

    if (typeof value === 'number') {
      if (Number.isInteger(value)) return value.toLocaleString();

      return value.toLocaleString(undefined, {
        maximumFractionDigits: 2,
      });
    }

    return String(value);
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
            <ArrowIcon className={`h-4 w-4 ${config.text}`} />
          </div>

          <h4 className="text-sm font-semibold mb-2 text-gray-900">
            {item.signal}
          </h4>
        </>
      ) : (
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-lg ${config.iconBg} shrink-0`}>
            <StatusIcon className={`h-5 w-5 ${config.text}`} />
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between mb-2 gap-3">
              <h4 className="font-semibold text-gray-900">{item.signal}</h4>
            </div>

            <p className="text-sm text-gray-600 leading-relaxed">
              {item.reason}
            </p>

            {featureValue !== undefined && featureValue !== null && (
              <div className="mt-2 pt-2 border-t border-gray-100">
                <p className="text-xs text-gray-500">
                  {item.feature}:{' '}
                  <span className="font-medium text-gray-700">
                    {formatFeatureValue(featureValue)}
                  </span>
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}