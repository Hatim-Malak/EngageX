/**
 * Format a number with K/M suffixes for compact display.
 *
 * @param {number} n - The number to format
 * @returns {string} Formatted string (e.g. "4.5M", "1.2K", "213")
 */
export function formatNumber(n) {
  if (n === 0) return "0";

  if (n >= 1_000_000) {
    return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M";
  }

  if (n >= 1_000) {
    return (n / 1_000).toFixed(1).replace(/\.0$/, "") + "K";
  }

  return String(n);
}

/**
 * Format a duration in seconds as MM:SS.
 *
 * @param {number} seconds - Duration in seconds
 * @returns {string} Formatted string (e.g. "3:33", "1:00", "0:05")
 */
export function formatDuration(seconds) {
  if (seconds <= 0) return "0:00";

  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);

  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}
