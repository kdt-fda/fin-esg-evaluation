import { useEffect, useState } from 'react';
import type { ChartDataPoint, LongTermItem } from '../types/chart';

type StockPricePoint = {
  date: string;
  actual?: number;
};

type PredictionResponse = {
  confidence: number;
  data: ChartDataPoint[];
  pastCount?: number;
};

type LongPredictionResponse = {
  confidence: number;
  data: LongTermItem[];
};

function mergeShortChartData(
  actualData: StockPricePoint[],
  predictedData: ChartDataPoint[]
): ChartDataPoint[] {
  const mergedMap = new Map<string, ChartDataPoint>();

  for (const item of actualData) {
    mergedMap.set(item.date, {
      date: item.date,
      actual: item.actual,
    });
  }

  for (const item of predictedData) {
    const existing = mergedMap.get(item.date);

    if (existing) {
      mergedMap.set(item.date, {
        ...existing,
        predicted: item.predicted,
        reason: item.reason,
        changeReason: item.changeReason,
      });
    } else {
      mergedMap.set(item.date, {
        date: item.date,
        predicted: item.predicted,
        reason: item.reason,
        changeReason: item.changeReason,
      });
    }
  }

  const merged = Array.from(mergedMap.values()).sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
  );

  const firstPredictedIdx = merged.findIndex(
    (item) => item.predicted !== undefined && item.predicted !== null
  );

  if (firstPredictedIdx > 0) {
    for (let i = firstPredictedIdx - 1; i >= 0; i--) {
      const prev = merged[i];

      if (prev.actual !== undefined && prev.actual !== null) {
        if (prev.predicted === undefined || prev.predicted === null) {
          merged[i] = {
            ...prev,
            predicted: prev.actual,
            isPredictionBridge: true,
          };
        }
        break;
      }
    }
  }

  return merged;
}

export default function useDashboardData(stockCode?: string) {
  const [shortTermData, setShortTermData] = useState<ChartDataPoint[]>([]);
  const [longTermData, setLongTermData] = useState<LongTermItem[]>([]);
  const [shortConfidence, setShortConfidence] = useState(0);
  const [longConfidence, setLongConfidence] = useState(0);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!stockCode) {
      setShortTermData([]);
      setLongTermData([]);
      setShortConfidence(0);
      setLongConfidence(0);
      setErrorMsg(null);
      return;
    }

    const controller = new AbortController();

    const fetchData = async () => {
      setLoading(true);
      setErrorMsg(null);

      try {
        const priceRes = await fetch(`/api/stocks/${stockCode}/prices`, {
          signal: controller.signal,
        });

        if (!priceRes.ok) {
          throw new Error(await priceRes.text());
        }

        const priceJson = (await priceRes.json()) as StockPricePoint[];

        let shortJson: PredictionResponse = {
          confidence: 0,
          data: [],
          pastCount: 0,
        };

        let longJson: LongPredictionResponse = {
          confidence: 0,
          data: [],
        };

        try {
          const shortRes = await fetch(
            `/api/predictions/short?code=${stockCode}`,
            { signal: controller.signal }
          );

          if (shortRes.ok) {
            shortJson = (await shortRes.json()) as PredictionResponse;
          } else {
            console.warn('short prediction not ready:', await shortRes.text());
          }
        } catch (err) {
          console.warn('short prediction fetch failed:', err);
        }

        try {
          const longRes = await fetch(
            `/api/predictions/long?code=${stockCode}`,
            { signal: controller.signal }
          );

          if (longRes.ok) {
            longJson = (await longRes.json()) as LongPredictionResponse;
          } else {
            console.warn('long prediction not ready:', await longRes.text());
            longJson = {
              confidence: 0,
              data: [],
            };
          }
        } catch (err) {
          console.warn('long prediction fetch failed:', err);
          longJson = {
            confidence: 0,
            data: [],
          };
        }

        const mergedShortData = mergeShortChartData(
          priceJson ?? [],
          shortJson.data ?? []
        );

        setShortTermData(mergedShortData);
        setLongTermData(longJson.data ?? []);
        setShortConfidence(shortJson.confidence ?? 0);
        setLongConfidence(longJson.confidence ?? 0);
      } catch (err: any) {
        if (err?.name === 'AbortError') return;

        console.error(err);
        setErrorMsg(err?.message ?? '데이터를 불러오지 못했습니다.');
        setShortTermData([]);
        setLongTermData([]);
        setShortConfidence(0);
        setLongConfidence(0);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    return () => controller.abort();
  }, [stockCode]);

  return {
    shortTermData,
    longTermData,
    shortConfidence,
    longConfidence,
    loading,
    errorMsg,
  };
}