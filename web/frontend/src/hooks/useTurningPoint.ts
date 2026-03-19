import { useEffect, useState } from 'react';
import type { TurningPoint, TurningPointsResponse } from '../types/turningpoint';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000';

export default function useTurningPoints(stockCode: string) {
  const [turningPoints, setTurningPoints] = useState<TurningPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stockCode || stockCode === '-') {
      setTurningPoints([]);
      setError(null);
      return;
    }

    const controller = new AbortController();

    const fetchTurningPoints = async () => {
      setLoading(true);
      setError(null);

      try {
        const res = await fetch(
          `${API_BASE}/api/stocks/${encodeURIComponent(stockCode)}/turning-points`,
          { signal: controller.signal }
        );

        if (!res.ok) {
          throw new Error(await res.text());
        }

        const json = (await res.json()) as TurningPointsResponse;
        setTurningPoints(json.turning_points ?? []);
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
        console.error(err);
        setError(err?.message ?? '변곡점 데이터를 불러오지 못했습니다.');
        setTurningPoints([]);
      } finally {
        setLoading(false);
      }
    };

    fetchTurningPoints();

    return () => controller.abort();
  }, [stockCode]);

  return {
    turningPoints,
    loading,
    error,
  };
}