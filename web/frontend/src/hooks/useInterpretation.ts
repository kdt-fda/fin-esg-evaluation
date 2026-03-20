import { useEffect, useState } from 'react';
import type { InterpretationResponse, InterpretationSignal } from '../types/interpretation';

type InterpretationType = 'short' | 'long';


export default function useInterpretation(
  stockCode: string,
  type: InterpretationType
) {
  const [summary, setSummary] = useState('');
  const [signals, setSignals] = useState<InterpretationSignal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stockCode || stockCode === '-') {
      setSummary('');
      setSignals([]);
      setError(null);
      return;
    }

    const controller = new AbortController();

    const fetchInterpretation = async () => {
      setLoading(true);
      setError(null);

      try {
        const endpoint =
          type === 'short'
            ? '/api/predictions/short/interpretation'
            : '/api/predictions/long/interpretation';

        const res = await fetch(
          `${endpoint}?code=${encodeURIComponent(stockCode)}`,
          { signal: controller.signal }
        );

        if (!res.ok) {
          throw new Error(await res.text());
        }

        const json = (await res.json()) as InterpretationResponse;
        const interpretation = json.interpretation;

        setSummary(interpretation?.ai_summary ?? '');
        setSignals(interpretation?.main_signals ?? []);
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
        console.error(err);
        setError(
          err?.message ??
            `${type === 'short' ? '단기' : '중장기'} AI 해석을 불러오지 못했습니다.`
        );
        setSummary('');
        setSignals([]);
      } finally {
        setLoading(false);
      }
    };

    fetchInterpretation();
    return () => controller.abort();
  }, [stockCode, type]);

  return {
    summary,
    signals,
    loading,
    error,
  };
}