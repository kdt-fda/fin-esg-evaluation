import { TrendingUp, TrendingDown, ArrowLeft, BarChart3, Calendar, Target, FileText } from 'lucide-react';
import type { Stock } from './StockSidebar';

interface PredictionReason {
  factor: string;
  impact: string;
  contribution: number;
}

interface DetailPageProps {
  stock: Stock;
  date: string;
  actualPrice?: number;
  predictedPrice?: number;
  reasons: PredictionReason[];
  changeReason: string;
  onClose: () => void;
}

export default function PredictionDetailPage({
  stock,
  date,
  actualPrice,
  predictedPrice,
  reasons,
  changeReason,
  onClose,
}: DetailPageProps) {
  const trend = predictedPrice && actualPrice ? predictedPrice > actualPrice : true;
  const changePercent = actualPrice && predictedPrice 
    ? (((predictedPrice - actualPrice) / actualPrice) * 100).toFixed(2)
    : '0.00';

  return (
    <div className="fixed inset-0 bg-gray-900 bg-opacity-50 z-50 flex items-center justify-center p-8">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-gradient-to-r from-blue-600 to-blue-700 text-white p-6 rounded-t-2xl">
          <button
            onClick={onClose}
            className="flex items-center gap-2 text-white hover:text-blue-100 transition-colors mb-4"
          >
            <ArrowLeft size={20} />
            <span>돌아가기</span>
          </button>
          
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-3xl font-bold mb-2">예측 상세 분석</h1>
              <div className="flex items-center gap-4 text-blue-100">
                <span className="text-lg">{stock.name} ({stock.code})</span>
                <span>•</span>
                <span>{date}</span>
              </div>
            </div>
            
            <div className={`flex items-center gap-2 px-4 py-2 rounded-lg ${
              trend ? 'bg-green-500' : 'bg-red-500'
            }`}>
              {trend ? <TrendingUp size={24} /> : <TrendingDown size={24} />}
              <span className="text-xl font-bold">
                {changePercent > '0' ? '+' : ''}{changePercent}%
              </span>
            </div>
          </div>
        </div>

        {/* Price Info */}
        <div className="p-6 border-b border-gray-200 bg-gray-50">
          <div className="grid grid-cols-2 gap-6">
            {actualPrice && (
              <div className="bg-white rounded-lg p-4 shadow-sm">
                <div className="flex items-center gap-2 text-gray-600 mb-2">
                  <BarChart3 size={18} />
                  <span className="text-sm font-medium">현재 주가</span>
                </div>
                <p className="text-2xl font-bold text-gray-900">
                  {actualPrice.toLocaleString()}원
                </p>
              </div>
            )}
            
            {predictedPrice && (
              <div className="bg-white rounded-lg p-4 shadow-sm">
                <div className="flex items-center gap-2 text-gray-600 mb-2">
                  <Target size={18} />
                  <span className="text-sm font-medium">예측 주가</span>
                </div>
                <p className={`text-2xl font-bold ${trend ? 'text-green-600' : 'text-red-600'}`}>
                  {predictedPrice.toLocaleString()}원
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Analysis Summary */}
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-start gap-3 bg-blue-50 rounded-lg p-4">
            <FileText className="text-blue-600 mt-1" size={20} />
            <div>
              <h3 className="font-semibold text-gray-900 mb-2">종합 분석</h3>
              <p className="text-gray-700 leading-relaxed">{changeReason}</p>
            </div>
          </div>
        </div>

        {/* Detailed Reasons */}
        <div className="p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Calendar size={20} className="text-blue-600" />
            주요 영향 요인 분석
          </h2>
          
          <div className="space-y-4">
            {reasons.map((reason, idx) => (
              <div
                key={idx}
                className="bg-white border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0">
                    <div
                      className={`w-12 h-12 rounded-full flex items-center justify-center ${
                        reason.contribution > 0
                          ? 'bg-green-100 text-green-600'
                          : 'bg-red-100 text-red-600'
                      }`}
                    >
                      <span className="font-bold text-lg">
                        {reason.contribution > 0 ? '+' : ''}
                        {Math.abs(reason.contribution)}%
                      </span>
                    </div>
                  </div>
                  
                  <div className="flex-1">
                    <h4 className="text-lg font-semibold text-gray-900 mb-2">
                      {reason.factor}
                    </h4>
                    <p className="text-gray-700 leading-relaxed mb-3">
                      {reason.impact}
                    </p>
                    
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-600">영향도:</span>
                      <div className="flex-1 max-w-xs h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            reason.contribution > 0 ? 'bg-green-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${Math.min(Math.abs(reason.contribution) * 10, 100)}%` }}
                        />
                      </div>
                      <span
                        className={`text-sm font-semibold ${
                          reason.contribution > 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {reason.contribution > 0 ? '상승 요인' : '하락 요인'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer Notice */}
        <div className="p-6 bg-gray-50 rounded-b-2xl">
          <div className="text-sm text-gray-600 text-center">
            <p>본 예측은 AI 분석을 통한 참고 자료이며, 투자의 책임은 투자자 본인에게 있습니다.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export type { PredictionReason };
