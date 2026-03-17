import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, RotateCcw, Star, ChevronDown } from 'lucide-react';

export interface Stock {
  code: string;
  name: string;
  sector: string;
  sector_code?: string;
  is_active?: boolean;
}

interface StockSidebarProps {
  selectedStock: Stock;
  onSelectStock: (stock: Stock) => void;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

export default function StockSidebar({ selectedStock, onSelectStock }: StockSidebarProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const listRef = useRef<HTMLDivElement | null>(null);

  // 즐겨찾기 state
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);

  // 섹터(산업) 필터 state
  const [selectedSector, setSelectedSector] = useState<string>('ALL');
  const [sectorOpen, setSectorOpen] = useState(false);

  const toggleFavorite = (code: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  // DB에서 코스피200 종목 로드
  useEffect(() => {
    const controller = new AbortController();

    const fetchStocks = async () => {
      setLoading(true);
      setErrorMsg(null);

      try {
        const res = await fetch(`${API_BASE}/api/stocks?active_only=true&limit=500`, {
          signal: controller.signal,
        });

        if (!res.ok) throw new Error(await res.text());

        const json = (await res.json()) as Stock[];
        setStocks(json ?? []);

        if ((!selectedStock?.code || selectedStock.code === '') && json?.length) {
          onSelectStock(json[0]);
        }
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
        console.error(err);
        setErrorMsg(err?.message ?? '종목 목록을 불러오지 못했습니다.');
        setStocks([]);
      } finally {
        setLoading(false);
      }
    };

    fetchStocks();
    return () => controller.abort();
  }, []);

  // DB에서 받은 stocks로 섹터 옵션 만들기
  const sectorOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of stocks) {
      const sec = (s.sector ?? '').trim();
      if (sec) set.add(sec);
    }
    const arr = Array.from(set).sort((a, b) => a.localeCompare(b, 'ko'));
    return ['ALL', ...arr];
  }, [stocks]);

  // 검색 + 섹터 + 즐겨찾기 필터
  const filteredStocks = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    let result = stocks;

    // 검색
    if (q) {
      result = result.filter(
        (stock) => stock.name.toLowerCase().includes(q) || stock.code.includes(q)
      );
    }

    // 섹터 필터 (ALL이면 전체 나열)
    if (selectedSector !== 'ALL') {
      result = result.filter((stock) => stock.sector === selectedSector);
    }

    // 즐겨찾기
    if (showFavoritesOnly) {
      result = result.filter((stock) => favorites.has(stock.code));
    }

    return result;
  }, [stocks, searchTerm, selectedSector, showFavoritesOnly, favorites]);

  // 초기화 버튼 표시 조건에 섹터/즐겨찾기필터도 포함
  const showReset =
    !!searchTerm.trim() ||
    showFavoritesOnly ||
    selectedSector !== 'ALL' ||
    (stocks.length > 0 && selectedStock?.code !== stocks[0]?.code);

  const handleReset = () => {
    setSearchTerm('');
    setShowFavoritesOnly(false);
    setSelectedSector('ALL');
    setSectorOpen(false);
    if (stocks.length > 0) onSelectStock(stocks[0]);
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  };



  
  return (
    <div className="w-80 bg-white border-r border-gray-200 h-screen flex flex-col">
      <div className="px-6 pt-6 pb-3 border-b border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-lg">코스피 200 기업</h2>

          {showReset && (
            <button
              onClick={handleReset}
              className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 transition-colors"
              title="초기화"
              type="button"
            >
              <RotateCcw size={14} />
              <span>초기화</span>
            </button>
          )}
        </div>

        {/* 즐겨찾기 필터 */}
        <div className="flex gap-2 mb-3">
          <button
            onClick={() => setShowFavoritesOnly(false)}
            className={`flex-1 px-3 py-1.5 rounded-md text-sm transition-colors ${
              !showFavoritesOnly
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            type="button"
          >
            전체
          </button>

          <button
            onClick={() => setShowFavoritesOnly(true)}
            className={`flex-1 px-3 py-1.5 rounded-md text-sm flex items-center justify-center gap-1 transition-colors ${
              showFavoritesOnly
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            type="button"
          >
            <Star size={14} fill={showFavoritesOnly ? 'white' : 'none'} />
            즐겨찾기 ({favorites.size})
          </button>
        </div>

        {/* 검색 */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" size={20} />
          <input
            type="text"
            placeholder="기업명 또는 코드 검색"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* 작은 섹터 드롭다운 (오른쪽 정렬) */}
        <div className="mt-1.5 flex justify-end relative">
          <button
            type="button"
            onClick={() => setSectorOpen((v) => !v)}
            className="h-6 text-xs px-2 py-0 inline-flex items-center gap-1 text-gray-600 hover:text-gray-800"
            aria-expanded={sectorOpen}
            title="산업별 필터"
          >
            {selectedSector === 'ALL' ? '산업별' : selectedSector}
            <ChevronDown className={`h-3 w-3 transition-transform ${sectorOpen ? 'rotate-180' : ''}`} />
          </button>

          {sectorOpen && (
            <div className="absolute right-0 top-7 bg-white border border-gray-200 rounded-md shadow-lg z-10 min-w-[120px] max-h-56 overflow-y-auto">
              <div className="py-0.5">
                <button
                  type="button"
                  className="w-full text-left text-xs h-7 px-2 hover:bg-gray-100"
                  onClick={() => {
                    setSelectedSector('ALL');
                    setSectorOpen(false);
                    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                >
                  전체
                </button>

                {sectorOptions
                  .filter((s) => s !== 'ALL')
                  .map((sec) => (
                    <button
                      key={sec}
                      type="button"
                      className="w-full text-left text-xs h-7 px-2 hover:bg-gray-100"
                      onClick={() => {
                        setSelectedSector(sec);
                        setSectorOpen(false);
                        listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
                      }}
                    >
                      {sec}
                    </button>
                  ))}
              </div>
            </div>
          )}
        </div>

        {loading && <div className="mt-3 text-sm text-gray-500">불러오는 중...</div>}
        {errorMsg && <div className="mt-3 text-sm text-red-500">{errorMsg}</div>}
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto">
        {filteredStocks.length === 0 ? (
          <div className="text-center py-8 text-gray-400 text-sm">
            {showFavoritesOnly ? '즐겨찾기한 기업이 없습니다' : '검색 결과가 없습니다'}
          </div>
        ) : (
          filteredStocks.map((stock) => (
            <div
              key={stock.code}
              className={`w-full flex items-start gap-2 px-4 py-4 hover:bg-gray-50 transition-colors border-b border-gray-100 ${
                selectedStock?.code === stock.code ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
              }`}
            >
              {/* 즐겨찾기 별 */}
              <button
                onClick={(e) => toggleFavorite(stock.code, e)}
                className="mt-0.5 hover:scale-110 transition-transform"
                title={favorites.has(stock.code) ? '즐겨찾기 해제' : '즐겨찾기 추가'}
                type="button"
              >
                <Star
                  size={18}
                  className={favorites.has(stock.code) ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}
                />
              </button>

              {/* 기업 정보 클릭 영역 */}
              <button onClick={() => onSelectStock(stock)} className="flex-1 text-left" type="button">
                <div className="flex justify-between items-start">
                  <div>
                    <div className="font-medium text-gray-900">{stock.name}</div>
                    <div className="text-sm text-gray-500">{stock.code}</div>
                  </div>
                  <div className="text-xs text-gray-400 mt-1">{stock.sector}</div>
                </div>
              </button>
            </div>
          ))
        )}

        {!loading && !errorMsg && stocks.length > 0 && filteredStocks.length === 0 && (
          <div className="p-6 text-sm text-gray-500">검색 결과가 없습니다.</div>
        )}
      </div>
    </div>
  );
}