import { useMemo, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Cell, ReferenceLine, LabelList } from 'recharts';
import { Info, X } from 'lucide-react';

interface LongTermItem {
  code: string;
  name: string;
  sector: string;
  score: number;
}

interface SectorRanking {
  name: string;
  score: number;
  rank: number;
  highlighted?: boolean; 
}

interface GrowthRankingChartProps {
  title: string;
  confidence: number;
  currentSector: string;
  selectedStockName : string;
  selectedStockCode : string; 
  data?: LongTermItem[]; 
}

export default function GrowthRankingChart({ title, confidence, currentSector, selectedStockName, selectedStockCode, data }: GrowthRankingChartProps) {
  const [showInfoModal, setShowInfoModal] = useState(false);
  const normalizedConfidence = useMemo(() => {
    if (!Number.isFinite(confidence)) return 0;
    return Math.max(0, Math.min(100, Number(confidence.toFixed(1))));
  }, [confidence]);

  const sectorRankings = useMemo<SectorRanking[]>(() => {
    if (!data || data.length === 0) return [];

    const sorted = [...data].sort((a, b) => b.score - a.score);

    const top10 = sorted.slice(0, 10);
    const selected = sorted.find((item) => item.code === selectedStockCode);
    const isSelectedInTop10 = top10.some((item) => item.code === selectedStockCode);

    const finalList = !selected
      ? top10
      : isSelectedInTop10
      ? top10
      : [...top10.slice(0, 9), selected];

    return finalList.map((item) => ({
      name: item.name,
      score: item.score,
      rank: sorted.findIndex((s) => s.code === item.code) + 1,
      highlighted: item.code === selectedStockCode,
    }));
  }, [data, selectedStockCode]);

  const avgScore = useMemo(() => {
    if (!data || data.length === 0) return 0;
    return data.reduce((sum, item) => sum + item.score, 0) / data.length;
  }, [data]);

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
                    normalizedConfidence >= 80 ? 'bg-green-500' : normalizedConfidence >= 60 ? 'bg-yellow-500' : 'bg-red-500'
                  }`}
                  style={{ width: `${normalizedConfidence}%` }}
                />
              </div>
              <span className="text-sm font-semibold text-gray-900">{normalizedConfidence}%</span>
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
                value: `${currentSector} 평균 (${avgScore.toFixed(1)}점)`,
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
                  예측 신뢰도: {normalizedConfidence}%
                </h5>
                <p>
                  예측 신뢰도는 상위 종목 적중률, 순위 예측력, 전체 종목 방향성 적중률을 종합 반영한 점수입니다.
                </p>
              </div>

              <div>
                <h5 className="font-semibold text-gray-900 mb-2 flex items-center gap-2">
                  <div className="w-1 h-4 bg-purple-500 rounded-full"></div>
                  주요 분석 요소
                </h5>

                <ul className="list-disc space-y-1 pl-5">

                  <li>추세 지표: MA60·MA120 이동평균선, Golden Cross(20-60), Death Cross(20-60)</li>
                  <li>기업 성장 및 수익성: revenue, revenue_growth, operating_income, operating_margin, net_income, EBITDA</li>
                  <li>재무 안정성 및 효율성: ROE, ROA, debt_ratio</li>
                  <li>기업 가치 평가: PER, PBR, EV/EBITDA</li>
                  <li>시장 규모: price, shares, market_cap</li>
                  <li>거시 환경: CPI, GDP, PMI, 금리 등 경기 지표</li>

                </ul>
              </div>

              <div className="border-t border-gray-200 pt-4">
                <p className="text-xs text-gray-500 flex gap-2">
                  <span>💡</span>
                  <span>
                    점수가 높을수록 하늘색에 가까워지고 낮을수록 초록색으로 표시되며<br/>
                    현재 선택한 종목은 주황색으로 강조됩니다.
                  </span>
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}