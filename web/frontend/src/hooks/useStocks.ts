import { useEffect, useState } from 'react';
import type { Stock } from '../components/StockSidebar';

export default function useStocks(
  selectedStockCode?: string,
  onInitialSelect?: (stock: Stock) => void
) {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchStocks = async () => {
      setLoading(true);
      setErrorMsg(null);

      try {
        const res = await fetch(`/api/stocks?active_only=true&limit=500`, {
          signal: controller.signal,
        });

        if (!res.ok) {
          throw new Error(await res.text());
        }

        const json = (await res.json()) as Stock[];
        const list = json ?? [];

        setStocks(list);

        if ((!selectedStockCode || selectedStockCode === '') && list.length > 0) {
          onInitialSelect?.(list[0]);
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

  return {
    stocks,
    loading,
    errorMsg,
  };
}