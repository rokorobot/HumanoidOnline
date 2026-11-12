// DR-UI2 — ecosystem rail. Names the four Humanoid.Company platforms with their
// REAL status (all four are live; the other three are outbound links). Rendered once by the root layout as a <header> (banner),
// deliberately NOT a <nav>: the frozen landmark structure is Primary + Footer
// only, and robot detail carries no Primary nav (e2e/semantics.spec.ts).
const PLATFORMS: { name: string; href?: string; current?: boolean; tone: string }[] = [
  { name: "HumanoidOnline", current: true, tone: "ho" },
  { name: "RentHumanoid", href: "https://renthumanoid.com/", tone: "rh" },
  { name: "HumanoidMart", href: "https://humanoidmart.com/", tone: "hm" },
  { name: "HumanoidLease", href: "https://humanoidlease.com/", tone: "hl" },
];

export function EcosystemRail() {
  return (
    <header className="eco-rail" aria-label="Humanoid.Company platforms">
      <div className="eco-rail__in">
        <ul className="eco-rail__list">
          {PLATFORMS.map((p) => (
            <li key={p.name} className={`eco-rail__item eco-rail__item--${p.tone}`}>
              <span className="eco-rail__dot" aria-hidden="true" />
              {p.href ? (
                <a href={p.href}>{p.name} ↗</a>
              ) : (
                <span aria-current={p.current ? "true" : undefined}>{p.name}</span>
              )}
            </li>
          ))}
        </ul>
        <span className="eco-rail__owner">
          A{" "}
          <a className="eco-rail__hc" href="https://humanoid.company/">
            Humanoid.Company
          </a>{" "}
          platform
        </span>
      </div>
    </header>
  );
}
