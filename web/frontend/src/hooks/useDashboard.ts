import { useEffect, useState } from 'react';
import type { ChartDataPoint, LongTermItem } from '../types/chart';
import type {
  InterpretationPayload,
  InterpretationSignal,
} from '../types/interpretation';

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

type ShortFullResponse = {
  ticker: string;
  pred_date: string | null;
  short: PredictionResponse;
  interpretation: InterpretationPayload | null;
};

type LongFullResponse = {
  ticker: string;
  pred_date: string | null;
  long: LongPredictionResponse;
  interpretation: InterpretationPayload | null;
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

  const [shortSummary, setShortSummary] = useState('');
  const [longSummary, setLongSummary] = useState('');
  const [shortSignals, setShortSignals] = useState<InterpretationSignal[]>([]);
  const [longSignals, setLongSignals] = useState<InterpretationSignal[]>([]);

  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!stockCode) {
      setShortTermData([]);
      setLongTermData([]);
      setShortConfidence(0);
      setLongConfidence(0);
      setShortSummary('');
      setLongSummary('');
      setShortSignals([]);
      setLongSignals([]);
      setErrorMsg(null);
      return;
    }

    const controller = new AbortController();

    const fetchData = async () => {
      setLoading(true);
      setErrorMsg(null);

      try {
        const [priceRes, shortFullRes, longFullRes] = await Promise.all([
          fetch(`/api/stocks/${stockCode}/prices`, {
            signal: controller.signal,
          }),
          fetch(`/api/predictions/short/full?code=${stockCode}`, {
            signal: controller.signal,
          }),
          fetch(`/api/predictions/long/full?code=${stockCode}`, {
            signal: controller.signal,
          }),
        ]);

        if (!priceRes.ok) {
          throw new Error(await priceRes.text());
        }

        const priceJson = (await priceRes.json()) as StockPricePoint[];

        let shortFullJson: ShortFullResponse = {
          ticker: stockCode,
          pred_date: null,
          short: {
            confidence: 0,
            data: [],
            pastCount: 0,
          },
          interpretation: null,
        };

        let longFullJson: LongFullResponse = {
          ticker: stockCode,
          pred_date: null,
          long: {
            confidence: 0,
            data: [],
          },
          interpretation: null,
        };

        if (shortFullRes.ok) {
          shortFullJson = (await shortFullRes.json()) as ShortFullResponse;
        }

        if (longFullRes.ok) {
          longFullJson = (await longFullRes.json()) as LongFullResponse;
        }

        const mergedShortData = mergeShortChartData(
          priceJson ?? [],
          shortFullJson.short?.data ?? []
        );

        setShortTermData(mergedShortData);
        setLongTermData(longFullJson.long?.data ?? []);
        setShortConfidence(shortFullJson.short?.confidence ?? 0);
        setLongConfidence(longFullJson.long?.confidence ?? 0);

        setShortSummary(shortFullJson.interpretation?.ai_summary ?? '');
        setLongSummary(longFullJson.interpretation?.ai_summary ?? '');
        setShortSignals(shortFullJson.interpretation?.main_signals ?? []);
        setLongSignals(longFullJson.interpretation?.main_signals ?? []);
      } catch (err: any) {
        if (err?.name === 'AbortError') return;

        console.error(err);
        setErrorMsg(err?.message ?? '데이터를 불러오지 못했습니다.');
        setShortTermData([]);
        setLongTermData([]);
        setShortConfidence(0);
        setLongConfidence(0);
        setShortSummary('');
        setLongSummary('');
        setShortSignals([]);
        setLongSignals([]);
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
    shortSummary,
    longSummary,
    shortSignals,
    longSignals,
    loading,
    errorMsg,
  };
}