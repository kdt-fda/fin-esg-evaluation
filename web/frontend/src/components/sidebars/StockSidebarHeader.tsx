import { Search, RotateCcw, Star, ChevronDown } from 'lucide-react';

interface StockSidebarHeaderProps {
  searchTerm: string;
  onSearchTermChange: (value: string) => void;
  showReset: boolean;
  onReset: () => void;
  showFavoritesOnly: boolean;
  onShowAll: () => void;
  onShowFavorites: () => void;
  favoritesCount: number;
  selectedSector: string;
  sectorOptions: string[];
  sectorOpen: boolean;
  onToggleSectorOpen: () => void;
  onSelectSector: (sector: string) => void;
  loading: boolean;
  errorMsg: string | null;
}

export default function StockSidebarHeader({
  searchTerm,
  onSearchTermChange,
  showReset,
  onReset,
  showFavoritesOnly,
  onShowAll,
  onShowFavorites,
  favoritesCount,
  selectedSector,
  sectorOptions,
  sectorOpen,
  onToggleSectorOpen,
  onSelectSector,
  loading,
  errorMsg,
}: StockSidebarHeaderProps) {
  return (
    <div className="px-6 pt-6 pb-3 border-b border-gray-200">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-lg">코스피 200 기업</h2>

        {showReset && (
          <button
            onClick={onReset}
            className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 transition-colors"
            title="초기화"
            type="button"
          >
            <RotateCcw size={14} />
            <span>초기화</span>
          </button>
        )}
      </div>

      <div className="flex gap-2 mb-3">
        <button
          onClick={onShowAll}
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
          onClick={onShowFavorites}
          className={`flex-1 px-3 py-1.5 rounded-md text-sm flex items-center justify-center gap-1 transition-colors ${
            showFavoritesOnly
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
          type="button"
        >
          <Star size={14} fill={showFavoritesOnly ? 'white' : 'none'} />
          즐겨찾기 ({favoritesCount})
        </button>
      </div>

      <div className="relative">
        <Search
          className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400"
          size={20}
        />
        <input
          type="text"
          placeholder="기업명 또는 코드 검색"
          value={searchTerm}
          onChange={(e) => onSearchTermChange(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div className="mt-1.5 flex justify-end relative">
        <button
          type="button"
          onClick={onToggleSectorOpen}
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
                onClick={() => onSelectSector('ALL')}
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
                    onClick={() => onSelectSector(sec)}
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
  );
}