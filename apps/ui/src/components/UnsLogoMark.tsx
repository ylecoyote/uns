/**
 * UNS Brand Mark (Variant 4a)
 *
 * Grid construction:
 * - Unit u = 24 (half a square on a 72x72 canvas, 3u x 3u)
 * - Filled machine-delivery square: 2u x 2u (48x48) at (0,0) in signal vermilion (#ec3013)
 * - Outlined human-response square: 2u x 2u (48x48 outer bounds) offset by 1u at (24,24)
 *   with stroke u/3 (8px) in charcoal ink (#201e1d)
 */

interface UnsLogoMarkProps {
  readonly size?: number;
  readonly className?: string;
}

export function UnsLogoMark({ size = 24, className = 'nav-brand-mark' }: UnsLogoMarkProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 72 72"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
      focusable="false"
      data-testid="uns-logo-mark"
    >
      <rect x="0" y="0" width="48" height="48" fill="var(--color-accent, #ec3013)" />
      <rect
        x="28"
        y="28"
        width="40"
        height="40"
        fill="none"
        stroke="var(--color-text, #201e1d)"
        strokeWidth="8"
      />
    </svg>
  );
}
