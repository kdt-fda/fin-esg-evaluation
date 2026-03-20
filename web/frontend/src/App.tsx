import { useState, useEffect, useMemo } from 'react';
import StockSidebar from './components/StockSidebar';
import type { Stock } from './components/StockSidebar';

import ShortTermPredictionChart from './components/ShortTermChart';
import LongTermChart from './components/LongTermChart';
import ShortTermAnalysis from './components/ShortTermAnalysis';
import LongTermAnalysis from './components/LongTermAnalysis';

import type { ChartDataPoint } from './types/chart';
import useDashboardData from './hooks/useDashboard';

import { Activity, Clock, Menu, X, ChevronDown, ChevronUp, AlertCircle } from 'lucide-react';

function formatYYYYMMDD(d: Date) {
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
}

function calcPastCount(points: ChartDataPoint[]) {
  if (!points || points.length === 0) return 0;
  const firstPredIdx = points.findIndex(
    (p) => p.predicted !== undefined && p.predicted !== null
  );
  return firstPredIdx === -1 ? points.length : firstPredIdx;
}

export default function App() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);

  const [timeUntilUpdate, setTimeUntilUpdate] = useState('');
  const [stockLoadingError, setStockLoadingError] = useState<string | null>(null);

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isModelInfoExpanded, setIsModelInfoExpanded] = useState(false);

  // 사이드바 상태를 App으로 올림
  const [selectedSector, setSelectedSector] = useState('ALL');
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [favorites, setFavorites] = useState<string[]>(() => {
    const saved = localStorage.getItem('favoriteStocks');
    return saved ? JSON.parse(saved) : [];
  });

  const {
    shortTermData,
    longTermData,
    shortConfidence,
    longConfidence,
    loading,
    errorMsg,
  } = useDashboardData(selectedStock?.code);

  const shortPastCount = useMemo(
    () => calcPastCount(shortTermData),
    [shortTermData]
  );

  useEffect(() => {
    localStorage.setItem('favoriteStocks', JSON.stringify(favorites));
  }, [favorites]);

  useEffect(() => {
    const controller = new AbortController();

    const fetchStocks = async () => {
      try {
        const res = await fetch(`/api/stocks?active_only=true&limit=500`, {
          signal: controller.signal,
        });

        if (!res.ok) throw new Error(await res.text());

        const json = (await res.json()) as Stock[];
        const list = json ?? [];

        setStocks(list);

        if (!selectedStock && list.length > 0) {
          setSelectedStock(list[0]);
        }
      } catch (err: any) {
        if (err?.name === 'AbortError') return;

        console.error(err);
        setStockLoadingError(err?.message ?? '종목 목록을 불러오지 못했습니다.');
        setStocks([]);
        setSelectedStock(null);
      }
    };

    fetchStocks();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const updateTimer = () => {
      const now = new Date();

      const tomorrow = new Date(now);
      tomorrow.setDate(tomorrow.getDate() + 1);
      tomorrow.setHours(0, 0, 0, 0);

      const diff = tomorrow.getTime() - now.getTime();
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

      setTimeUntilUpdate(
        `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
      );
    };

    updateTimer();
    const interval = setInterval(updateTimer, 60000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen bg-gray-50">
      <div className={`transition-all duration-300 ${isSidebarOpen ? 'w-80' : 'w-0'}`}>
        {isSidebarOpen &&
          (selectedStock ? (
            <StockSidebar
              stocks={stocks}
              selectedStock={selectedStock}
              onSelectStock={setSelectedStock}
              selectedSector={selectedSector}
              onSelectSector={setSelectedSector}
              showFavoritesOnly={showFavoritesOnly}
              onChangeShowFavoritesOnly={setShowFavoritesOnly}
              searchTerm={searchTerm}
              onChangeSearchTerm={setSearchTerm}
              favorites={favorites}
              onChangeFavorites={setFavorites}
            />
          ) : (
            <div className="w-80 bg-white border-r border-gray-200 h-screen flex flex-col">
              <div className="p-6 border-b border-gray-200">
                <h2 className="font-semibold text-lg mb-2">코스피 200 기업</h2>
                <p className="text-sm text-gray-500">종목 불러오는 중...</p>
              </div>
            </div>
          ))}
      </div>

      <div className="flex-1 flex flex-col overflow-hidden relative">
        <button
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="absolute left-4 top-6 z-10 p-2 bg-white rounded-lg shadow-md hover:bg-gray-50 transition-colors border border-gray-200"
          title={isSidebarOpen ? '사이드바 접기' : '사이드바 펼치기'}
        >
          {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
        </button>

        <header className="bg-white border-b border-gray-200 px-8 py-6">
          <div className="flex items-center justify-center gap-3 mb-2">
            <Activity className="text-blue-600" size={28} />
            <h1 className="text-3xl font-bold text-gray-900">
              설명 가능한 주가 예측 기반 투자 참고 플랫폼
            </h1>
          </div>

          <div className="flex items-center justify-center gap-2">
            <span className="text-sm text-gray-500">현재 종목:</span>

            <div className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-blue-400 to-blue-500 text-white rounded-full shadow-md">
              <span className="font-semibold">{selectedStock?.name ?? '-'}</span>

              <span className="text-xs opacity-90 bg-white/20 px-2 py-0.5 rounded-full">
                {selectedStock?.code ?? '-'}
              </span>

              <span className="text-xs opacity-75 border-l border-white/30 pl-2">
                {selectedStock?.sector ?? '-'}
              </span>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-8 py-6">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
            <ShortTermPredictionChart
              title="단기 예측 차트"
              data={shortTermData}
              confidence={shortConfidence}
              pastCount={shortPastCount}
            />

            <LongTermChart
              title="중장기 투자 매력도 랭킹"
              confidence={longConfidence}
              currentSector={selectedStock?.sector ?? '-'}
              selectedStockCode={selectedStock?.code ?? '-'}
              data={longTermData}
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 mb-6 items-start">
            <div>
              <div className="mb-4">
                <h2 className="text-xl font-semibold text-gray-900">단기 예측 근거</h2>
              </div>

              <ShortTermAnalysis
                stockName={selectedStock?.name ?? '-'}
                stockCode={selectedStock?.code ?? '-'}
                isSidebarOpen={isSidebarOpen}
              />
            </div>

            <div>
              <div className="mb-4">
                <h2 className="text-xl font-semibold text-gray-900">중장기 매력도 근거</h2>
              </div>

              <LongTermAnalysis
                stockName={selectedStock?.name ?? '-'}
                stockCode={selectedStock?.code ?? '-'}
                currentSector={selectedStock?.sector ?? '-'}
                data={longTermData}
                isSidebarOpen={isSidebarOpen}
              />
            </div>
          </div>

          <div className="mb-6 flex items-center justify-center gap-2 text-xs text-gray-500">
            <AlertCircle className="h-4 w-4 text-gray-400" />
            <span>
              {isSidebarOpen
                ? '사이드바를 닫으면 각 기술적 지표의 설명을 더 자세히 확인할 수 있습니다.'
                : '사이드바가 열려 있을 때는 핵심 카드와 최근 주요 변곡점을 요약해 보여줍니다.'}
            </span>
          </div>

          <div className="bg-white rounded-xl shadow-sm p-6">
            <button
              onClick={() => setIsModelInfoExpanded(!isModelInfoExpanded)}
              className="w-full flex items-center justify-between hover:bg-gray-50 transition-colors rounded-lg p-3 -m-3"
            >
              <span className="text-xs text-gray-500">모델 및 예측근거 설명</span>
              {isModelInfoExpanded ? (
                <ChevronUp size={16} className="text-gray-500" />
              ) : (
                <ChevronDown size={16} className="text-gray-500" />
              )}
            </button>

            {isModelInfoExpanded && (
              <div className="mt-4 pt-4 border-t border-gray-200">
                <div className="space-y-3 text-xs text-gray-600 leading-relaxed">
                  <p>
                    <span className="font-semibold text-gray-800">■ 예측 모델 개요:</span>{' '}
                    본 플랫폼은 설명 가능한 AI 기반 예측 구조를 활용하여 주가 흐름을 시각화합니다.
                    실제 주가 데이터, 예측 결과, 주요 영향 요인, 설명 문장을 함께 제공하여
                    사용자가 예측 흐름을 직관적으로 이해할 수 있도록 구성했습니다.
                  </p>

                  <p>
                    <span className="font-semibold text-gray-800">■ 단기 예측:</span>{' '}
                    향후 단기 구간의 예측값을 기준으로 차트를 표시합니다.
                    예측 구간에서는 예측 가격과 함께 근거 요인 및 설명 문장을 확인할 수 있으며,
                    슬라이더로 과거 구간 범위를 조절할 수 있습니다.
                  </p>

                  <p>
                    <span className="font-semibold text-gray-800">■ 중장기 예측:</span>{' '}
                    중장기 구간은 월 단위 흐름을 기준으로 요약해 보여줍니다.
                    장기적인 실적, 거시 지표, 산업 성장성 같은 요소를 중심으로
                    방향성을 해석할 수 있도록 구성됩니다.
                  </p>

                  <p>
                    <span className="font-semibold text-gray-800">■ 예측 근거:</span>{' '}
                    차트의 예측 구간에 마우스를 올리면 해당 시점의 예측값을 확인할 수 있고,
                    클릭하면 예측에 영향을 준 주요 요인과 설명을 상세 페이지에서 볼 수 있습니다.
                  </p>

                  <p className="text-red-600 font-semibold">
                    ※ 본 화면은 투자 참고용 정보이며, 실제 투자 판단과 책임은 사용자 본인에게 있습니다.
                  </p>
                </div>
              </div>
            )}
          </div>

          {loading && <p className="mt-4 text-sm text-gray-500">불러오는 중...</p>}
          {(errorMsg || stockLoadingError) && (
            <p className="mt-4 text-sm text-red-600">
              {errorMsg ?? stockLoadingError}
            </p>
          )}
        </main>

        <footer className="relative bg-white border-t border-gray-200 px-8 py-4">
          <div className="text-center">
            <p className="text-gray-700 mb-1">
              {formatYYYYMMDD(new Date(Date.now() - 86400000))} 일까지의 데이터 반영했습니다.
            </p>

            <div className="flex items-center justify-center gap-2 text-sm text-gray-500">
              <Clock size={14} />
              <span>업데이트까지 {timeUntilUpdate} 남았습니다.</span>
            </div>
          </div>

          <div className="absolute right-4 bottom-3 text-sm text-gray-400">
            © Team MER-M
          </div>
        </footer>
      </div>
    </div>
  );
}