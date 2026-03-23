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