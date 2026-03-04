import { useEffect, useMemo, useState } from 'react';
import { Search } from 'lucide-react';

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

  // DB에서 코스피200 종목 로드
  useEffect(() => {
    const controller = new AbortController();

    const fetchStocks = async () => {
      setLoading(true);
      setErrorMsg(null);

      try {
        const res = await fetch(
          `${API_BASE}/api/stocks?active_only=true&limit=500`,
          { signal: controller.signal }
        );

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
    // selectedStock을 deps에 넣으면 매번 다시 불러오니 제외
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 검색 필터
  const filteredStocks = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    if (!q) return stocks;

    return stocks.filter(
      (stock) =>
        stock.name.toLowerCase().includes(q) ||
        stock.code.includes(q)
    );
  }, [stocks, searchTerm]);

  return (
    <div className="w-80 bg-white border-r border-gray-200 h-screen flex flex-col">
      <div className="p-6 border-b border-gray-200">
        <h2 className="font-semibold text-lg mb-4">코스피 200 기업</h2>

        <div className="relative">
          <Search
            className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400"
            size={20}
          />
          <input
            type="text"
            placeholder="기업명 또는 코드 검색"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {loading && <div className="mt-3 text-sm text-gray-500">불러오는 중...</div>}
        {errorMsg && <div className="mt-3 text-sm text-red-500">{errorMsg}</div>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {filteredStocks.map((stock) => (
          <button
            key={stock.code}
            onClick={() => onSelectStock(stock)}
            className={`w-full px-6 py-4 text-left hover:bg-gray-50 transition-colors border-b border-gray-100 ${
              selectedStock?.code === stock.code ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
            }`}
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium text-gray-900">{stock.name}</div>
                <div className="text-sm text-gray-500">{stock.code}</div>
              </div>
              <div className="text-xs text-gray-400 mt-1">{stock.sector}</div>
            </div>
          </button>
        ))}

        {!loading && !errorMsg && filteredStocks.length === 0 && (
          <div className="p-6 text-sm text-gray-500">검색 결과가 없습니다.</div>
        )}
      </div>
    </div>
  );
}