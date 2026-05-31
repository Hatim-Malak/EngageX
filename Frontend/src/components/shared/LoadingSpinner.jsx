/**
 * Animated loading spinner with configurable size and color.
 *
 * @param {{ size?: number, color?: string }} props
 */
export default function LoadingSpinner({ size = 24, className = "", color = "text-brand-light" }) {
  return (
    <div 
      className={`relative inline-flex items-center justify-center ${color} ${className}`} 
      style={{ width: size, height: size }}
    >
      {/* Soft pulsating glow behind the spinner */}
      <div className="absolute inset-0 rounded-full animate-pulse blur-md bg-current opacity-40"></div>
      
      {/* Crisp spinning SVG */}
      <svg
        className="relative animate-spin drop-shadow-[0_0_8px_currentColor] z-10"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ width: size, height: size }}
      >
        <circle
          className="opacity-20"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="3"
        />
        <path
          className="opacity-90"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
    </div>
  );
}
