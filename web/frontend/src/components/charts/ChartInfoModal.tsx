import type { ReactNode } from 'react';
import { X } from 'lucide-react';

interface ChartInfoModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}

export default function ChartInfoModal({
  open,
  title,
  onClose,
  children,
}: ChartInfoModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
      onClick={onClose}
    >
      <div
        className="mx-4 w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between">
          <h4 className="text-lg font-bold text-gray-900">{title}</h4>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 transition-colors hover:text-gray-600"
            aria-label="닫기"
          >
            <X size={22} />
          </button>
        </div>

        <div className="space-y-4 text-sm leading-6 text-gray-700">
          {children}
        </div>
      </div>
    </div>
  );
}