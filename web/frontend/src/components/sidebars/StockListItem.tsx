import { Star } from 'lucide-react';
import type { Stock } from '../StockSidebar';

interface StockListItemProps {
  stock: Stock;
  selected: boolean;
  isFavorite: boolean;
  onSelect: (stock: Stock) => void;
  onToggleFavorite: (code: string, e: React.MouseEvent) => void;
}

export default function StockListItem({
  stock,
  selected,
  isFavorite,
  onSelect,
  onToggleFavorite,
}: StockListItemProps) {
  return (
    <div
      className={`w-full flex items-start gap-2 px-4 py-4 hover:bg-gray-50 transition-colors border-b border-gray-100 ${
        selected ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
      }`}
    >
      <button
        onClick={(e) => onToggleFavorite(stock.code, e)}
        className="mt-0.5 hover:scale-110 transition-transform"
        title={isFavorite ? '즐겨찾기 해제' : '즐겨찾기 추가'}
        type="button"
      >
        <Star
          size={18}
          className={isFavorite ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}
        />
      </button>

      <button onClick={() => onSelect(stock)} className="flex-1 text-left" type="button">
        <div className="flex justify-between items-start">
          <div>
            <div className="font-medium text-gray-900">{stock.name}</div>
            <div className="text-sm text-gray-500">{stock.code}</div>
          </div>
          <div className="text-xs text-gray-400 mt-1">{stock.sector}</div>
        </div>
      </button>
    </div>
  );
}