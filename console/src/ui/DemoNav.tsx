/**
 * Scaffolding, not product: a way to reach the other surfaces.
 *
 * The family's phone and the hospital's screen are separate applications meant
 * to be opened on separate devices by separate people — there is no link
 * between them in the real thing, and there should not be. But a judge handed
 * one URL needs a way to find the other two, so this sits above everything,
 * deliberately drawn as scaffolding: dark, small, and labelled "demo" so it
 * reads as the ladder rather than the building.
 *
 * Hidden inside the recording stage, which already shows both screens, and
 * hidden from the recorded demo for the same reason.
 */

const SURFACES: { href: string; label: string }[] = [
  { href: "/index.html", label: "Hospital" },
  { href: "/family.html?patient=P-SHAMBHU", label: "Phone · Shambhu" },
  { href: "/family.html?patient=P-ANITA", label: "Phone · Anita" },
  { href: "/stage.html?phones=P-SHAMBHU", label: "Both screens" },
];

/** True when this document is inside the stage's frames. */
const framed = () => {
  try {
    return window.top !== window.self;
  } catch {
    return true; // cross-origin parent: treat as framed and stay out of the way
  }
};

export function DemoNav() {
  if (framed()) return null;

  const here = window.location.pathname.replace(/^\/$/, "/index.html");
  const patient = new URLSearchParams(window.location.search).get("patient");

  const current = (href: string) => {
    const [path, query] = href.split("?");
    if (path !== here) return false;
    if (!query) return true;
    return new URLSearchParams(query).get("patient") === patient;
  };

  return (
    <nav className="demo-nav" aria-label="Demo surfaces">
      <span className="demo-nav-tag">demo</span>
      {SURFACES.map((surface) => (
        <a
          key={surface.href}
          href={surface.href}
          aria-current={current(surface.href) ? "page" : undefined}
        >
          {surface.label}
        </a>
      ))}
    </nav>
  );
}
