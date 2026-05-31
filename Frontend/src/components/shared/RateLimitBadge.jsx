import useEngageStore from "../../store/useEngageStore";

/**
 * Color-coded badge showing remaining/total query quota.
 * Green (>20), Yellow (10–20), Red (<10).
 */
export default function RateLimitBadge() {
  const queriesRemaining = useEngageStore((s) => s.queriesRemaining);
  const queriesLimit = useEngageStore((s) => s.queriesLimit);

  let colorClass;
  let dotColor;

  if (queriesRemaining > 20) {
    colorClass = "bg-green-900/30 text-green-300 border-green-500/40";
    dotColor = "bg-green-400 drop-shadow-[0_0_5px_rgba(74,222,128,0.8)]";
  } else if (queriesRemaining >= 10) {
    colorClass = "bg-yellow-900/30 text-yellow-300 border-yellow-500/40";
    dotColor = "bg-yellow-400 drop-shadow-[0_0_5px_rgba(250,204,21,0.8)]";
  } else {
    colorClass = "bg-red-900/30 text-red-300 border-red-500/40";
    dotColor = "bg-red-400 drop-shadow-[0_0_5px_rgba(248,113,113,0.8)]";
  }

  const formatted = Intl.NumberFormat().format(queriesRemaining);

  return (
    <span
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold border backdrop-blur-sm ${colorClass}`}
    >
      <span className={`w-2 h-2 rounded-full ${dotColor}`} />
      {formatted}/{queriesLimit} queries left
    </span>
  );
}
