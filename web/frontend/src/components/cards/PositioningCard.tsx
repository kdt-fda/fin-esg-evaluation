import { useEffect, useRef, useState } from 'react';
import { Trophy } from 'lucide-react';
import { Card } from '../ui/card';

interface PositioningCardProps {
  currentSector: string;
  totalCompanies: number;
  currentRank: number;
  topPercent: number;
}

export default function PositioningCard({
  currentSector,
  totalCompanies,
  currentRank,
  topPercent,
}: PositioningCardProps) {
  const [animatedRank, setAnimatedRank] = useState(currentRank);
  const [animatedTopPercent, setAnimatedTopPercent] = useState(topPercent);

  const prevRankRef = useRef(currentRank);
  const prevTopPercentRef = useRef(topPercent);

  useEffect(() => {
    let frameId = 0;
    const duration = 700;
    const frameRate = 1000 / 60;
    const totalFrames = Math.max(1, Math.round(duration / frameRate));

    let currentFrame = 0;
    const startRank = prevRankRef.current;
    const startTopPercent = prevTopPercentRef.current;

    const animate = () => {
      currentFrame += 1;
      const progress = Math.min(currentFrame / totalFrames, 1);
      const eased = 1 - Math.pow(1 - progress, 3);

      setAnimatedRank(
        Math.round(startRank + (currentRank - startRank) * eased)
      );
      setAnimatedTopPercent(
        Math.round(startTopPercent + (topPercent - startTopPercent) * eased)
      );

      if (progress < 1) {
        frameId = requestAnimationFrame(animate);
      }
    };

    frameId = requestAnimationFrame(animate);

    prevRankRef.current = currentRank;
    prevTopPercentRef.current = topPercent;

    return () => cancelAnimationFrame(frameId);
  }, [currentRank, topPercent]);

  return (
    <Card className="p-4 border-sky-200 bg-gradient-to-br from-sky-50 to-cyan-50">
      <div className="flex items-start gap-2.5">
        <div className="p-1.5 rounded-lg bg-sky-100 shrink-0">
          <Trophy className="h-5 w-5 text-sky-600" />
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">섹터 내 포지셔닝</h3>
          <p className="text-sm text-slate-600 mb-3">
            {currentSector} {totalCompanies}개 기업 중 투자 매력도 기준 위치입니다.
          </p>

          <div className="flex items-center gap-4">
            <div>
              <p className="text-xs text-slate-500 mb-1">순위</p>
              <p className="text-xl font-bold text-sky-700">
                {currentRank > 0 ? `${animatedRank}위` : '-'}
              </p>
            </div>

            <div className="h-10 w-px bg-sky-200" />

            <div>
              <p className="text-xs text-slate-500 mb-1">상위</p>
              <p className="text-xl font-bold text-cyan-700">
                {topPercent > 0 ? `${animatedTopPercent}%` : '-'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}