import { useMemo, useRef, useState } from 'react';
import StockSidebarHeader from './sidebars/StockSidebarHeader';
import StockListItem from './sidebars/StockListItem';

export interface Stock {
  code: string;
  name: string;
  sector: string;
  sector_code?: string;
  is_active?: boolean;
}

interface StockSidebarProps {
  stocks: Stock[];
  selectedStock: Stock;
  onSelectStock: (stock: Stock) => void;
  selectedSector: string;
  onSelectSector: (sector: string) => void;
  showFavoritesOnly: boolean;
  onChangeShowFavoritesOnly: (value: boolean) => void;
  searchTerm: string;
  onChangeSearchTerm: (value: string) => void;
  favorites: string[];
  onChangeFavorites: React.Dispatch<React.SetStateAction<string[]>>;
}

export default function StockSidebar({
  stocks,
  selectedStock,
  onSelectStock,
  selectedSector,
  onSelectSector,
  showFavoritesOnly,
  onChangeShowFavoritesOnly,
  searchTerm,
  onChangeSearchTerm,
  favorites,
  onChangeFavorites,
}: StockSidebarProps) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const [sectorOpen, setSectorOpen] = useState(false);

  const favoriteSet = useMemo(() => new Set(favorites), [favorites]);

  const loading = false;
  const errorMsg = null;

  const toggleFavorite = (code: string, e: React.MouseEvent) => {
    e.stopPropagation();

    onChangeFavorites((prev) => {
      if (prev.includes(code)) {
        return prev.filter((item) => item !== code);
      }
      return [...prev, code];
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
      result = result.filter((stock) => favoriteSet.has(stock.code));
    }

    return result;
  }, [stocks, searchTerm, selectedSector, showFavoritesOnly, favoriteSet]);

  const showReset =
    !!searchTerm.trim() ||
    showFavoritesOnly ||
    selectedSector !== 'ALL' ||
    (stocks.length > 0 && selectedStock?.code !== stocks[0]?.code);

  const handleReset = () => {
    onChangeSearchTerm('');
    onChangeShowFavoritesOnly(false);
    onSelectSector('ALL');
    setSectorOpen(false);

    if (stocks.length > 0) onSelectStock(stocks[0]);

    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSelectSector = (sector: string) => {
    onSelectSector(sector);
    setSectorOpen(false);
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="w-80 bg-white border-r border-gray-200 h-screen flex flex-col">
      <StockSidebarHeader
        searchTerm={searchTerm}
        onSearchTermChange={onChangeSearchTerm}
        showReset={showReset}
        onReset={handleReset}
        showFavoritesOnly={showFavoritesOnly}
        onShowAll={() => onChangeShowFavoritesOnly(false)}
        onShowFavorites={() => onChangeShowFavoritesOnly(true)}
        favoritesCount={favorites.length}
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
              isFavorite={favoriteSet.has(stock.code)}
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