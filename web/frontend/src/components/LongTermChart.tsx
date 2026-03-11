import { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Cell, ReferenceLine, LabelList } from 'recharts';
import { Info, X } from 'lucide-react';

interface SectorRanking {
  name: string;
  score: number;
  rank: number;
  highlighted?: boolean; // 현재 선택된 종목의 섹터
}

interface GrowthRankingChartProps {
  title: string;
  confidence: number;
  currentSector: string;
  selectedStockName : string; //선택
}

export default function GrowthRankingChart({ title, confidence, currentSector }: GrowthRankingChartProps) {
  const [showInfoModal, setShowInfoModal] = useState(false);

  // Mock 섹터별 랭킹 데이터 (고려신용정보 예시 기준)
  const sectorRankings: SectorRanking[] = [
    { name: 'NICE평가정보', score: 92.3, rank: 1, highlighted: false },
    { name: '미래에셋증권', score: 87.6, rank: 2, highlighted: false },
    { name: '한국기업평가', score: 80.3, rank: 3, highlighted: false },
    { name: '삼성증권', score: 78.9, rank: 4, highlighted:  true },
    { name: 'NH투자증권', score: 73.1, rank: 5, highlighted: false },
    { name: '나이스디앤비', score: 72.9, rank: 6,highlighted: false },
    { name: '고려신용정보', score: 60.6, rank: 7, highlighted: false },
    { name: 'SCI평가정보', score: 48.6, rank: 8, highlighted: false },
    { name: '한국금융지주', score: 48.6, rank: 9, highlighted: false },
    { name: '키움증권', score: 43.2, rank: 10, highlighted: false },
  ];

  // 기준점 계산 (평균 점수)
  const avgScore = sectorRankings.reduce((sum, item) => sum + item.score, 0) / sectorRankings.length;

  // 점수에 따른 그라데이션 색상 계산 (하늘색 -> 초록색)
  const getBarColor = (score: number, highlighted: boolean) => {
    if (highlighted) {
      return 'rgba(251, 189, 91, 0.8)';
    }

    const ratio = 1 - score / 100;
    const r = Math.round(147 + (45 - 147) * ratio);
    const g = Math.round(197 + (212 - 197) * ratio);
    const b = Math.round(253 + (191 - 253) * ratio);

    return `rgba(${r}, ${g}, ${b}, 0.72)`;
  };

  const CustomYAxisTick = ({ x, y, payload }: any) => {
    const data = sectorRankings.find(item => item.name === payload.value);
    const isHighlighted = data?.highlighted;

    return (
      <g transform={`translate(${x},${y})`}>
        <text
          x={0}
          y={0}
          dy={4}
          textAnchor="end"
          fill={isHighlighted ? '#f59e0b' : '#374151'}
          fontSize={11}
          fontWeight={isHighlighted ? 700 : 400}
        >
          {payload.value}
        </text>
      </g>
    );
  };

  return (
    <div className="bg-white rounded-xl shadow-sm p-6 flex-1">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h3 className="text-xl font-semibold text-gray-900 mb-2">{title}</h3>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">예측 신뢰도</span>
            <div className="flex items-center gap-2">
              <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    confidence >= 80 ? 'bg-green-500' : confidence >= 60 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${confidence}%` }}
                />
              </div>
              <span className="text-sm font-semibold text-gray-900">{confidence}%</span>
            </div>
          </div>
        </div>

        <Info
          className="text-gray-400 cursor-pointer hover:text-blue-600 transition-colors"
          size={20}
          onClick={() => setShowInfoModal(true)}
        />
      </div>

      {/* 차트 */}
      <div className="relative">
        <ResponsiveContainer width="100%" height={430}>
          <BarChart
            data={sectorRankings}
            layout="vertical"
            margin={{ top: 16, right: 36, left: 80, bottom: 16 }}
            barCategoryGap="3%"
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#f0f0f0"
              horizontal={true}
              vertical={false}
            />

            <XAxis
              type="number"
              domain={[0, 100]}
              tick={{ fill: '#6b7280', fontSize: 11 }}
              tickLine={{ stroke: '#e5e7eb' }}
              axisLine={{ stroke: '#e5e7eb' }}
              label={{
                value: '투자 점수 (점)',
                position: 'insideBottom',
                offset: -2,
                style: { fontSize: 11, fill: '#6b7280' },
              }}
            />

            <YAxis
              type="category"
              dataKey="name"
              tick={<CustomYAxisTick />}
              tickLine={false}
              axisLine={false}
              width={80}
            />

            <ReferenceLine
              x={avgScore}
              stroke="#9ca3af"
              strokeDasharray="5 5"
              label={{
                value: `평균 (${avgScore.toFixed(1)}점)`,
                position: 'top',
                fill: '#6b7280',
                fontSize: 10,
              }}
            />

            <Bar dataKey="score" radius={[0, 8, 8, 0]} barSize={28}>
              {sectorRankings.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={getBarColor(entry.score, entry.highlighted || false)}
                  stroke= 'none'
                  strokeWidth={0}
                />
              ))}

              <LabelList
                dataKey="score"
                position="right"
                offset={10}
                formatter={(value: number) => `${value}점`}
                style={{
                  fill: '#374151',
                  fontSize: 12,
                  fontWeight: 500,
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* 하단 범례 */}
      <div className="mt-4 pt-4 border-t border-gray-200">
        <div className="flex items-center justify-center gap-6 text-xs">
          <div className="flex items-center gap-2">
            <div
              className="w-4 h-3 rounded"
              style={{ background: 'linear-gradient(to right, rgba(59,130,246,0.65), rgba(20,184,166,0.65))' }}
            ></div>
            <span className="text-gray-600">점수별 그라데이션</span>
          </div>
          <div className="flex items-center gap-2">
            <div
              className="w-4 h-3 rounded"
              style={{
                background: 'rgba(251, 189, 91, 0.8)',
              }}
            ></div>
            <span className="text-gray-600">현재 선택 종목</span>
          </div>
        </div>
      </div>

      {/* 정보 모달 */}
      {showInfoModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          onClick={() => setShowInfoModal(false)}
        >
          <div
            className="mx-4 w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-5 flex items-center justify-between">
              <h4 className="text-lg font-bold text-gray-900">
                중장기 투자 매력도 랭킹 정보
              </h4>
              <button
                type="button"
                onClick={() => setShowInfoModal(false)}
                className="text-gray-400 transition-colors hover:text-gray-600"
                aria-label="닫기"
              >
                <X size={22} />
              </button>
            </div>

            <div className="space-y-4 text-sm leading-6 text-gray-700">
              <div>
                <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <div className="w-1 h-4 bg-blue-500 rounded-full"></div>
                  랭킹 개요
                </h5>
                <p>
                  중장기 성장 예측은 동종 업계 기업들의
                  성장 가능성을 점수화하여 순위를 매깁니다.
                  선택한 종목이 속한 산업 섹터 내에서 상대적 투자 매력도를 평가합니다.
                </p>
              </div>

              <div>
                <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <div className="w-1 h-4 bg-green-500 rounded-full"></div>
                  예측 신뢰도: {confidence}%
                </h5>
                <p>
                  예측 신뢰도는 상위 종목 적중률, 순위 예측력, 전체 종목 방향성 적중률을 종합 반영한 점수입니다.
                </p>
              </div>

              <div>
                <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <div className="w-1 h-4 bg-purple-500 rounded-full"></div>
                  활용 방법
                </h5>
                <p>
                  점수가 높을수록 하늘색에 가까워지며, 낮을수록 초록색으로 표시됩니다.
                  현재 선택한 종목은 주황색으로 표시되어
                  경쟁사 대비 상대적 위치를 한눈에 파악할 수 있습니다.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}