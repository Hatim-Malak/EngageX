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
    colorClass = "bg-green-100 text-green-800 border-green-200";
    dotColor = "bg-green-500";
  } else if (queriesRemaining >= 10) {
    colorClass = "bg-yellow-100 text-yellow-800 border-yellow-200";
    dotColor = "bg-yellow-500";
  } else {
    colorClass = "bg-red-100 text-red-800 border-red-200";
    dotColor = "bg-red-500";
  }

  const formatted = Intl.NumberFormat().format(queriesRemaining);

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${colorClass}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      {formatted}/{queriesLimit} queries left
    </span>
  );
}
