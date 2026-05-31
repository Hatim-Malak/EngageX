import useEngageStore from "../../store/useEngageStore"
import { TrendingUp } from "lucide-react"

export default function EngagementComparison() {
  const engagement = useEngageStore((s) => s.engagement)

  if (!engagement) return null

  const { winner, engagement_rate_a, engagement_rate_b } = engagement
  const maxRate = Math.max(engagement_rate_a, engagement_rate_b)
  // Bar width as percentage of max (min 10% so even 0% shows a sliver)
  const barWidthA = Math.max((engagement_rate_a / maxRate) * 100, 10)
  const barWidthB = Math.max((engagement_rate_b / maxRate) * 100, 10)

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <TrendingUp size={16} className="text-blue-600" />
        <h3 className="text-sm font-semibold text-gray-900">Engagement Rate Comparison</h3>
      </div>

      {/* Bar A */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-gray-700">
            Video A {winner === "A" && <span className="text-yellow-600 ml-1">👑</span>}
          </span>
          <span className="font-semibold text-gray-900">{engagement_rate_a.toFixed(1)}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-3">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              winner === "A" ? "bg-blue-600" : "bg-gray-400"
            }`}
            style={{ width: `${barWidthA}%` }}
          />
        </div>
      </div>

      {/* Bar B */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-gray-700">
            Video B {winner === "B" && <span className="text-yellow-600 ml-1">👑</span>}
          </span>
          <span className="font-semibold text-gray-900">{engagement_rate_b.toFixed(1)}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-3">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              winner === "B" ? "bg-blue-600" : "bg-gray-400"
            }`}
            style={{ width: `${barWidthB}%` }}
          />
        </div>
      </div>

      {/* Winner text */}
      <p className="text-xs text-gray-500 text-center pt-1">
        {winner === "A"
          ? "Video A has higher engagement rate"
          : "Video B has higher engagement rate"}
      </p>
    </div>
  )
}
