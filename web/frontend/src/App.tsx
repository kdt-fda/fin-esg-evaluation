import { useState, useEffect } from 'react';
import StockSidebar from './components/StockSidebar';
import type { Stock } from './components/StockSidebar';

import PredictionChart from './components/PredictionChart';
import type { ChartDataPoint } from './components/PredictionChart';

import PredictionDetailPage from './components/PredictionDetailPage';
import { Activity, Clock, Menu, X } from 'lucide-react';

type PredictionResponse = {
  confidence: number;
  data: ChartDataPoint[];
};

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

function formatYYYYMMDD(d: Date) {
  return `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`;
}

export default function App() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);

  const [shortTermData, setShortTermData] = useState<ChartDataPoint[]>([]);
  const [longTermData, setLongTermData] = useState<ChartDataPoint[]>([]);
  const [shortConfidence, setShortConfidence] = useState<number>(0);
  const [longConfidence, setLongConfidence] = useState<number>(0);

  const [timeUntilUpdate, setTimeUntilUpdate] = useState('');
  const [detailData, setDetailData] = useState<{ data: ChartDataPoint; stock: Stock } | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [currentDate, setCurrentDate] = useState('');

  // 사이드바 토글 state
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  // 종목 리스트 로드
  useEffect(() => {
    const controller = new AbortController();

    const fetchStocks = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/stocks?active_only=true&limit=500`, {
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
        setErrorMsg(err?.message ?? '종목 목록을 불러오지 못했습니다.');
        setStocks([]);
        setSelectedStock(null);
      }
    };

    fetchStocks();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    setCurrentDate(formatYYYYMMDD(new Date()));
  }, []);

  // 다음날 0시까지 남은 시간
  useEffect(() => {
    const updateTimer = () => {
      const now = new Date();

      const tomorrow = new Date(now);
      tomorrow.setDate(tomorrow.getDate() + 1);
      tomorrow.setHours(0, 0, 0, 0);

      const diff = tomorrow.getTime() - now.getTime();
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));

      setTimeUntilUpdate(`${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`);
    };

    updateTimer();
    const interval = setInterval(updateTimer, 60000);

    return () => clearInterval(interval);
  }, []);

  // 예측 데이터 불러오기
  useEffect(() => {
    if (!selectedStock) return;

    const controller = new AbortController();

    const fetchPredictions = async () => {
      setLoading(true);
      setErrorMsg(null);

      try {
        const code = selectedStock.code;

        const [shortRes, longRes] = await Promise.all([
          fetch(`${API_BASE}/api/predictions/short?code=${code}`, { signal: controller.signal }),
          fetch(`${API_BASE}/api/predictions/long?code=${code}`, { signal: controller.signal }),
        ]);

        if (!shortRes.ok) throw new Error(await shortRes.text());
        if (!longRes.ok) throw new Error(await longRes.text());

        const shortJson = (await shortRes.json()) as PredictionResponse;
        const longJson = (await longRes.json()) as PredictionResponse;

        setShortTermData(shortJson.data ?? []);
        setLongTermData(longJson.data ?? []);
        setShortConfidence(shortJson.confidence ?? 0);
        setLongConfidence(longJson.confidence ?? 0);
      } catch (err: any) {
        if (err?.name === 'AbortError') return;

        console.error(err);
        setErrorMsg(err?.message ?? '예측 데이터를 불러오지 못했습니다.');
        setShortTermData([]);
        setLongTermData([]);
      } finally {
        setLoading(false);
      }
    };

    fetchPredictions();
    return () => controller.abort();
  }, [selectedStock?.code]);

  const handleReasonClick = (data: ChartDataPoint) => {
    if (!selectedStock) return;
    setDetailData({ data, stock: selectedStock });
  };

  return (
    <div className="flex h-screen bg-gray-50">

      {/* Sidebar */}
      <div className={`transition-all duration-300 ${isSidebarOpen ? 'w-80' : 'w-0'}`}>
        {isSidebarOpen && (
          selectedStock ? (
            <StockSidebar selectedStock={selectedStock} onSelectStock={setSelectedStock} />
          ) : (
            <div className="w-80 bg-white border-r border-gray-200 h-screen flex flex-col">
              <div className="p-6 border-b border-gray-200">
                <h2 className="font-semibold text-lg mb-2">코스피 200 기업</h2>
                <p className="text-sm text-gray-500">종목 불러오는 중...</p>
              </div>
            </div>
          )
        )}
      </div>

      {/* Main 영역 */}
      <div className="flex-1 flex flex-col overflow-hidden relative">

        {/* Sidebar Toggle Button */}
        <button
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="absolute left-4 top-6 z-10 p-2 bg-white rounded-lg shadow-md hover:bg-gray-50 transition-colors border border-gray-200"
          title={isSidebarOpen ? "사이드바 접기" : "사이드바 펼치기"}
        >
          {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
        </button>

        {/* Header */}
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
              <span className="font-semibold">
                {selectedStock?.name ?? '-'}
              </span>

              <span className="text-xs opacity-90 bg-white/20 px-2 py-0.5 rounded-full">
                {selectedStock?.code ?? '-'}
              </span>

              <span className="text-xs opacity-75 border-l border-white/30 pl-2">
                {selectedStock?.sector ?? '-'}
              </span>
            </div>
          </div>
        </header>

        {/* Main */}
        <main className="flex-1 overflow-y-auto px-8 py-6">
          <div className="flex gap-6 mb-6">
            <PredictionChart
              title="단기 예측 차트"
              data={shortTermData}
              confidence={shortConfidence}
              isShortTerm={true}
              onReasonClick={handleReasonClick}
            />

            <PredictionChart
              title="중장기 성장 예측 차트"
              data={longTermData}
              confidence={longConfidence}
              isShortTerm={false}
              onReasonClick={handleReasonClick}
            />
          </div>

          <div className="bg-white rounded-xl shadow-sm p-6">
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2 text-gray-700">
                <div className="w-3 h-3 bg-blue-500 rounded-full"></div>
                <span className="text-sm">실제 주가</span>
              </div>

              <div className="flex items-center gap-2 text-gray-700">
                <div className="w-3 h-3 bg-green-500 rounded-full"></div>
                <span className="text-sm">예측 주가</span>
              </div>

              <div className="text-sm text-gray-500 italic">
                * 차트의 예측 구간에 마우스를 올려 예측 근거를 확인하세요
              </div>
            </div>
          </div>

          {loading && <p className="mt-4 text-sm text-gray-500">불러오는 중...</p>}
          {errorMsg && <p className="mt-4 text-sm text-red-600">{errorMsg}</p>}
        </main>

        {/* Footer */}
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

      {/* Detail Modal */}
      {detailData && (
        <PredictionDetailPage
          stock={detailData.stock}
          date={detailData.data.date}
          actualPrice={detailData.data.actual}
          predictedPrice={detailData.data.predicted}
          reasons={detailData.data.reason || []}
          changeReason={detailData.data.changeReason || ''}
          onClose={() => setDetailData(null)}
        />
      )}
    </div>
  );
}