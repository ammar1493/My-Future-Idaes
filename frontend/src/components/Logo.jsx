import { useState } from "react";

// NEFT ENERGIES brand mark.
// Prefers the real asset at /logo.png (drop your exact file in frontend/public/);
// if it's missing, falls back to a scalable SVG recreation of the gear-and-sun
// icon so the UI always renders.
export default function Logo({ size = 40, showText = true, variant = "row" }) {
  const [useImg, setUseImg] = useState(true);

  const icon = useImg ? (
    <img
      src="/logo.png"
      alt="NEFT ENERGIES"
      height={size}
      style={{ height: size, width: "auto", display: "block" }}
      onError={() => setUseImg(false)}
    />
  ) : (
    <GearSun size={size} />
  );

  // When the real PNG is used it already contains the wordmark, so skip the text.
  const showWordmark = showText && !useImg;

  return (
    <span className={`logo logo-${variant}`}>
      {icon}
      {showWordmark && (
        <span className="logo-text">
          NEFT <strong>ENERGIES</strong>
        </span>
      )}
    </span>
  );
}

function GearSun({ size }) {
  const navy = "#0B2545";
  const gold = "#F4B41A";
  const teeth = Array.from({ length: 12 });
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-label="NEFT ENERGIES">
      {teeth.map((_, i) => (
        <rect
          key={i}
          x="45.5"
          y="1"
          width="9"
          height="16"
          rx="2"
          fill={navy}
          transform={`rotate(${i * 30} 50 50)`}
        />
      ))}
      <circle cx="50" cy="50" r="35" fill={navy} />
      <circle cx="50" cy="50" r="27" fill="#fff" />
      {/* sun: filled left semicircle */}
      <path d="M50 27 A23 23 0 0 0 50 73 Z" fill={gold} />
    </svg>
  );
}
