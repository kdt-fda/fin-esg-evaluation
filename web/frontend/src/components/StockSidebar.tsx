import { useMemo, useRef, useState } from 'react';
import StockSidebarHeader from './sidebars/StockSidebarHeader';
import StockListItem from './sidebars/StockListItem';
import useStocks from '../hooks/useStocks';

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

export default function StockSidebar({
  selectedStock,
  onSelectStock,
}: StockSidebarProps) {
  const listRef = useRef<HTMLDivElement | null>(null);

  const [searchTerm, setSearchTerm] = useState('');
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [showFavoritesOnly, setShowFavoritesOnly] = useState(false);
  const [selectedSector, setSelectedSector] = useState<string>('ALL');
  const [sectorOpen, setSectorOpen] = useState(false);

  const {
    stocks,
    loading,
    errorMsg,
  } = useStocks(selectedStock?.code, onSelectStock);

  const toggleFavorite = (code: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  };

  const sectorOptions = useMemo(() => {
    const set = new Set<string>();
    for (const s of stocks) {
      const sec = (s.sector ?? '').trim();
      if (sec) set.add(sec);
    }
    const arr = Array.from(set).sort((a, b) => a.localeCompare(b, 'ko'));
    return ['ALL', ...arr];
  }, [stocks]);

  const filteredStocks = useMemo(() => {
    const q = searchTerm.trim().toLowerCase();
    let result = stocks;

    if (q) {
      result = result.filter(
        (stock) => stock.name.toLowerCase().includes(q) || stock.code.includes(q)
      );
    }

    if (selectedSector !== 'ALL') {
      result = result.filter((stock) => stock.sector === selectedSector);
    }

    if (showFavoritesOnly) {
      result = result.filter((stock) => favorites.has(stock.code));
    }

    return result;
  }, [stocks, searchTerm, selectedSector, showFavoritesOnly, favorites]);

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

  const handleSelectSector = (sector: string) => {
    setSelectedSector(sector);
    setSectorOpen(false);
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="w-80 bg-white border-r border-gray-200 h-screen flex flex-col">
      <StockSidebarHeader
        searchTerm={searchTerm}
        onSearchTermChange={setSearchTerm}
        showReset={showReset}
        onReset={handleReset}
        showFavoritesOnly={showFavoritesOnly}
        onShowAll={() => setShowFavoritesOnly(false)}
        onShowFavorites={() => setShowFavoritesOnly(true)}
        favoritesCount={favorites.size}
        selectedSector={selectedSector}
        sectorOptions={sectorOptions}
        sectorOpen={sectorOpen}
        onToggleSectorOpen={() => setSectorOpen((v) => !v)}
        onSelectSector={handleSelectSector}
        loading={loading}
        errorMsg={errorMsg}
      />

      <div ref={listRef} className="flex-1 overflow-y-auto">
        {filteredStocks.length === 0 ? (
          <div className="text-center py-8 text-gray-400 text-sm">
            {showFavoritesOnly ? '즐겨찾기한 기업이 없습니다' : '검색 결과가 없습니다'}
          </div>
        ) : (
          filteredStocks.map((stock) => (
            <StockListItem
              key={stock.code}
              stock={stock}
              selected={selectedStock?.code === stock.code}
              isFavorite={favorites.has(stock.code)}
              onSelect={onSelectStock}
              onToggleFavorite={toggleFavorite}
            />
          ))
        )}

        {!loading && !errorMsg && stocks.length > 0 && filteredStocks.length === 0 && (
          <div className="p-6 text-sm text-gray-500">검색 결과가 없습니다.</div>
        )}
      </div>
    </div>
  );
}