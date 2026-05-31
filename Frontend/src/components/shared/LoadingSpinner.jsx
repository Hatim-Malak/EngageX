/**
 * Animated loading spinner with configurable size and color.
 *
 * @param {{ size?: number, color?: string }} props
 */
export default function LoadingSpinner({ size = 24, color = "text-blue-500" }) {
  return (
    <div
      className={`animate-spin rounded-full border-2 border-gray-300 border-t-current ${color}`}
      style={{ width: size, height: size }}
      role="status"
      aria-label="Loading"
    />
  );
}
