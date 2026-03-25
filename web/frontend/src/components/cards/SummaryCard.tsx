import { Card } from '../ui/card';

interface SummaryCardProps {
  title?: string;
  summary?: string;
  loading?: boolean;
  error?: string | null;
  emptyMessage?: string;
}

export default function SummaryCard({
  title = 'AI 종합 해석',
  summary,
  loading = false,
  error = null,
  emptyMessage = '데이터가 없습니다.',
}: SummaryCardProps) {
  return (
    <Card className="min-h-[210px] px-5 py-4 bg-white border-gray-200">
      {/* 제목 */}
      <h3 className="text-base font-semibold text-gray-900 mb-1">
        {title}
      </h3>

      {/* 로딩 */}
      {loading && (
        <p className="text-sm text-gray-500 leading-6">
          해석을 불러오는 중...
        </p>
      )}

      {/* 에러 */}
      {!loading && error && (
        <p className="text-sm text-red-600 leading-6">
          {error}
        </p>
      )}

      {/* 빈 데이터 */}
      {!loading && !error && !summary && (
        <p className="text-sm text-gray-400 leading-6">
          {emptyMessage}
        </p>
      )}

      {/* 정상 데이터 */}
      {!loading && !error && !!summary && (
        <p className="text-[14px] text-gray-700 leading-6 break-keep">
          {summary}
        </p>
      )}
    </Card>
  );
}