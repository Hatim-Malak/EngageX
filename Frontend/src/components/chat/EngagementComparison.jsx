import useEngageStore from "../../store/useEngageStore";
import { TrendingUp } from "lucide-react";

export default function EngagementComparison() {
  const engagement = useEngageStore((s) => s.engagement);

  if (!engagement) return null;

  const { winner, engagement_rate_a, engagement_rate_b } = engagement;
  const maxRate = Math.max(engagement_rate_a, engagement_rate_b);
  // Bar width as percentage of max (min 10% so even 0% shows a sliver)
  const barWidthA = Math.max((engagement_rate_a / maxRate) * 100, 10);
  const barWidthB = Math.max((engagement_rate_b / maxRate) * 100, 10);

  return (
    <div className="bg-brand-primary/20 backdrop-blur-md border border-brand-secondary/30 rounded-xl p-5 space-y-4 shadow-lg">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-brand-primary/40 pb-2">
        <TrendingUp size={18} className="text-brand-light" />
        <h3 className="text-sm font-bold text-white tracking-wide uppercase">
          Engagement Comparison
        </h3>
      </div>

      {/* Bar A */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-brand-light">
            Video A{" "}
            {winner === "A" && <span className="text-yellow-400 ml-1">👑</span>}
          </span>
          <span className="font-bold text-white drop-shadow-sm">
            {engagement_rate_a.toFixed(1)}%
          </span>
        </div>
        <div className="w-full bg-brand-dark/60 rounded-full h-3.5 shadow-inner overflow-hidden border border-brand-dark">
          <div
            className={`h-full rounded-full transition-all duration-1000 ease-out ${
              winner === "A"
                ? "bg-gradient-to-r from-brand-secondary to-brand-light"
                : "bg-brand-primary/60"
            }`}
            style={{ width: `${barWidthA}%` }}
          />
        </div>
      </div>

      {/* Bar B */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-brand-light">
            Video B{" "}
            {winner === "B" && <span className="text-yellow-400 ml-1">👑</span>}
          </span>
          <span className="font-bold text-white drop-shadow-sm">
            {engagement_rate_b.toFixed(1)}%
          </span>
        </div>
        <div className="w-full bg-brand-dark/60 rounded-full h-3.5 shadow-inner overflow-hidden border border-brand-dark">
          <div
            className={`h-full rounded-full transition-all duration-1000 ease-out ${
              winner === "B"
                ? "bg-gradient-to-r from-brand-secondary to-brand-light"
                : "bg-brand-primary/60"
            }`}
            style={{ width: `${barWidthB}%` }}
          />
        </div>
      </div>

      {/* Winner text */}
      <p className="text-[11px] text-brand-light/70 text-center pt-2 font-medium">
        {winner === "A"
          ? "Video A has a higher engagement rate"
          : "Video B has a higher engagement rate"}
      </p>
    </div>
  );
}
