import { useNavigate } from "react-router-dom"
import { Plus } from "lucide-react"
import useEngageStore from "../../store/useEngageStore"
import RateLimitBadge from "../shared/RateLimitBadge"

export default function Header() {
  const navigate = useNavigate()
  const resetStore = useEngageStore((s) => s.resetStore)

  const handleNewSession = () => {
    resetStore()
    localStorage.removeItem("engagex_session_id")
    navigate("/")
  }

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white">
      {/* Logo / wordmark */}
      <div className="flex items-center gap-2">
        <span className="text-xl font-bold text-gray-900 tracking-tight">
          EngageX
        </span>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        <RateLimitBadge />
        <button
          onClick={handleNewSession}
          className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 bg-gray-100 hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors"
        >
          <Plus size={16} />
          New Session
        </button>
      </div>
    </header>
  )
}
