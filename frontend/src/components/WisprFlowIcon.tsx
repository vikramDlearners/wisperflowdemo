/** The Wispr Flow mark: five bars. */
export default function WisprFlowIcon({ className, size = 26 }: { className?: string; size?: number }) {
  return (
    <svg className={className} viewBox="0 0 344 337" width={size} height={size} aria-hidden="true">
      <path
        d="M24.5 24.5v288M98.5 176v102M172.5 81v175M246 179v99M319.5 24.5v288"
        fill="none"
        stroke="currentColor"
        strokeWidth="49"
        strokeLinecap="round"
      />
    </svg>
  );
}
