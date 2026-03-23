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
import { TrendingUp, TrendingDown, Activity } from 'lucide-react';
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

  const tooltipText =
    item.reason?.trim() ||
    `${item.signal} / SHAP ${formatShapValue(item.shap_value)}`;

  return (
    <Card
      className={`relative group p-3 border transition-all duration-300 hover:shadow-xl hover:-translate-y-0.5 ${
        isCompact ? config.bg : 'bg-white'
      } ${config.border}`}
    >
      {/* 툴팁 */}
      <div
        className="
          pointer-events-none absolute left-1/2 top-full z-50 mt-3
          w-max max-w-[260px] -translate-x-1/2
          opacity-0 translate-y-1
          transition-all duration-200 delay-100
          group-hover:opacity-100 group-hover:translate-y-0
        "
      >
        {/* 화살표 */}
        <div className="mx-auto h-0 w-0 border-l-[6px] border-r-[6px] border-b-[6px] border-l-transparent border-r-transparent border-b-gray-900" />

        {/* 툴팁 본문 */}
        <div className="rounded-md bg-gray-900 px-2.5 py-1.5 text-[11px] leading-relaxed text-white shadow-xl whitespace-normal text-center">
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
  return (
    <Card
      className={`relative group p-3 border transition-all duration-300 hover:shadow-md ${
        isCompact ? config.bg : 'bg-white'
      } ${config.border}`}
    >
      {/* 툴팁 */}
      <div className="pointer-events-none absolute left-1/2 top-0 z-20 w-max max-w-[220px] -translate-x-1/2 -translate-y-[110%] rounded-md bg-gray-900 px-2 py-1 text-[11px] text-white opacity-0 shadow-lg transition-all duration-200 group-hover:opacity-100 group-hover:-translate-y-[120%]">
        {item.reason}
      </div>

      {isCompact ? (
        <>
          {/* 아이콘 + SHAP */}
          <div className="flex items-start justify-between mb-2">
            <div className={`p-1.5 rounded ${config.iconBg}`}>
              <StatusIcon className={`h-4 w-4 ${config.text}`} />
            </div>

            <div className="text-right">
              <p className="text-[9px] text-gray-500 leading-none mb-1 tracking-tight">
                SHAP
              </p>
              <p className={`text-[12px] font-medium leading-none ${config.text}`}>
                {formatShapValue(item.shap_value)}
              </p>
            </div>
          </div>

          {/* 신호명 */}
          <h4 className="text-[13px] font-semibold leading-snug text-gray-900">
            {item.signal}
          </h4>
        </>
      ) : (
        <div className="flex items-start gap-3">
          {/* 아이콘 */}
          <div className={`p-2 rounded-lg ${config.iconBg} shrink-0`}>
            <StatusIcon className={`h-5 w-5 ${config.text}`} />
          </div>

          {/* 내용 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between mb-2 gap-3">
              <h4 className="text-[14px] font-semibold text-gray-900">
                {item.signal}
              </h4>

              <div className="text-right shrink-0">
                <p className="text-[10px] text-gray-500 leading-none mb-1">
                  SHAP
                </p>
                <p className={`text-[13px] font-medium ${config.text}`}>
                  {formatShapValue(item.shap_value)}
                </p>
              </div>
            </div>

            <p className="text-[13px] text-gray-600 leading-relaxed">
              {item.reason}
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}