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

type TooltipAlign = 'center' | 'left' | 'right';

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
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [tooltipAlign, setTooltipAlign] = useState<TooltipAlign>('center');

  const config = getStatusConfig(item.direction, item.strength);
  const StatusIcon = config.icon;

  const formatShapValue = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '-';
    return value.toFixed(3);
  };

  const tooltipText = getFeatureTooltip(item.feature);

  const handleMouseEnter = () => {
    if (!wrapperRef.current) return;

    const rect = wrapperRef.current.getBoundingClientRect();
    const boundaryEl = wrapperRef.current.parentElement;
    const boundaryRect = boundaryEl?.getBoundingClientRect();

    const tooltipWidth = 320;
    const margin = 16;

    const leftLimit = boundaryRect ? boundaryRect.left : 0;
    const rightLimit = boundaryRect ? boundaryRect.right : window.innerWidth;

    const centeredLeft = rect.left + rect.width / 2 - tooltipWidth / 2;
    const centeredRight = rect.left + rect.width / 2 + tooltipWidth / 2;

    if (centeredLeft < leftLimit + margin) {
      setTooltipAlign('left');
      return;
    }

    if (centeredRight > rightLimit - margin) {
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
    <div
      ref={wrapperRef}
      onMouseEnter={handleMouseEnter}
      className="relative group"
    >
      <Card
        className={`border p-3 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl ${
          isCompact ? `h-[160px] ${config.bg}` : 'bg-white'
        } ${config.border}`}
      >
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
          <div
            className={`h-0 w-0 border-l-[6px] border-r-[6px] border-b-[6px] border-l-transparent border-r-transparent border-b-white ${arrowPositionClass}`}
          />

          <div className="rounded-md border border-gray-200 bg-white px-3 py-2 text-[11px] leading-relaxed text-gray-700 shadow-xl whitespace-normal text-center">
            {tooltipText}
          </div>
        </div>

        {isCompact ? (
          <>
            <div className="mb-2 flex items-start justify-between">
              <div className={`rounded p-1 ${config.iconBg}`}>
                <StatusIcon className={`h-3 w-3 ${config.text}`} />
              </div>

              <div className="text-right">
                <span className="mb-0.5 block text-[7px] leading-none tracking-tight text-gray-400">
                  SHAP
                </span>
                <span
                  className={`block text-[9px] font-semibold leading-none tracking-tight ${config.text}`}
                >
                  {formatShapValue(item.shap_value)}
                </span>
              </div>
            </div>

            <h4 className="line-clamp-2 min-h-[36px] text-[12px] font-semibold leading-snug text-gray-900">
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
                  <span className="mb-1 block text-[10px] leading-none text-gray-500">
                    SHAP
                  </span>
                  <span className={`block text-[13px] font-medium ${config.text}`}>
                    {formatShapValue(item.shap_value)}
                  </span>
                </div>
              </div>

              <p className="text-[13px] leading-relaxed text-gray-600">
                {item.reason}
              </p>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}