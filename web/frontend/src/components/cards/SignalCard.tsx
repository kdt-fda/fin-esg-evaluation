import { useRef, useState } from 'react';
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';
import { Card } from '../ui/card';
import { getFeatureTooltip } from './featureTooltipMap';
import type {
  InterpretationSignal,
  SignalDirection,
  SignalStrength,
} from '../../types/interpretation';

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

type TooltipAlign = 'center' | 'left' | 'right';

export default function SignalCard({
  item,
  isCompact = false,
}: SignalCardProps) {
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [tooltipAlign, setTooltipAlign] = useState<TooltipAlign>('center');

  const config = getStatusConfig(item.direction, item.strength);
  const StatusIcon = config.icon;

  const formatShapValue = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '-';
    return value.toFixed(3);
  };

  const tooltipText = getFeatureTooltip(item.feature);

  const handleMouseEnter = () => {
    if (!cardRef.current) return;

    const rect = cardRef.current.getBoundingClientRect();
    const tooltipWidth = 320;
    const margin = 16;

    const centeredLeft = rect.left + rect.width / 2 - tooltipWidth / 2;
    const centeredRight = rect.left + rect.width / 2 + tooltipWidth / 2;

    if (centeredLeft < margin) {
      setTooltipAlign('left');
      return;
    }

    if (centeredRight > window.innerWidth - margin) {
      setTooltipAlign('right');
      return;
    }

    setTooltipAlign('center');
  };

  const tooltipPositionClass =
    tooltipAlign === 'left'
      ? 'left-0'
      : tooltipAlign === 'right'
      ? 'right-0'
      : 'left-1/2 -translate-x-1/2';

  const arrowPositionClass =
    tooltipAlign === 'left'
      ? 'ml-4'
      : tooltipAlign === 'right'
      ? 'ml-auto mr-4'
      : 'mx-auto';

  return (
    <Card
      ref={cardRef}
      onMouseEnter={handleMouseEnter}
      className={`relative group p-3 border transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl ${
        isCompact ? config.bg : 'bg-white'
      } ${config.border}`}
    >
      {/* tooltip */}
      <div
        className={`
          pointer-events-none absolute top-full z-50 mt-3
          w-max max-w-[320px]
          translate-y-1 opacity-0
          transition-all duration-200 delay-100
          group-hover:translate-y-0 group-hover:opacity-100
          ${tooltipPositionClass}
        `}
      >
        {/* arrow */}
        <div
          className={`h-0 w-0 border-l-[6px] border-r-[6px] border-b-[6px] border-l-transparent border-r-transparent border-b-white ${arrowPositionClass}`}
        />

        {/* body */}
        <div className="rounded-md border border-gray-200 bg-white px-3 py-2 text-[11px] leading-relaxed text-gray-700 shadow-xl whitespace-normal text-center">
          {tooltipText}
        </div>
      </div>

      {isCompact ? (
        <>
          <div className="mb-2 flex items-start justify-between">
            <div className={`rounded p-1.5 ${config.iconBg}`}>
              <StatusIcon className={`h-4 w-4 ${config.text}`} />
            </div>

            <div className="text-right">
              <p className="mb-1 text-[9px] leading-none tracking-tight text-gray-500">
                SHAP
              </p>
              <p className={`text-[12px] font-medium leading-none ${config.text}`}>
                {formatShapValue(item.shap_value)}
              </p>
            </div>
          </div>

          <h4 className="text-[13px] font-semibold leading-snug text-gray-900">
            {item.signal}
          </h4>
        </>
      ) : (
        <div className="flex items-start gap-3">
          <div className={`shrink-0 rounded-lg p-2 ${config.iconBg}`}>
            <StatusIcon className={`h-5 w-5 ${config.text}`} />
          </div>

          <div className="min-w-0 flex-1">
            <div className="mb-2 flex items-start justify-between gap-3">
              <h4 className="text-[14px] font-semibold text-gray-900">
                {item.signal}
              </h4>

              <div className="shrink-0 text-right">
                <p className="mb-1 text-[10px] leading-none text-gray-500">
                  SHAP
                </p>
                <p className={`text-[13px] font-medium ${config.text}`}>
                  {formatShapValue(item.shap_value)}
                </p>
              </div>
            </div>

            <p className="text-[13px] leading-relaxed text-gray-600">
              {item.reason}
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}