// WS8.4 / R21 — a real lint gate with an intentionally-configured jsx-a11y set.
//
// `eslint-config-next` already runs jsx-a11y at "warn"; this promotes the
// accessibility rules to ERROR and turns on the recommended set Next omits, so
// the gate actually blocks. `npm run lint` runs with `--max-warnings=0`, so a
// warning fails CI too.
//
// Discipline (WS8.4): difficult rules are NOT globally disabled to get green.
// Any genuine exception is a narrow, documented `eslint-disable-next-line` at
// the call site — never a blanket rule-off here.
module.exports = {
  root: true,
  extends: ["next/core-web-vitals", "plugin:jsx-a11y/recommended"],
  plugins: ["jsx-a11y"],
  rules: {
    "jsx-a11y/alt-text": "error",
    "jsx-a11y/anchor-has-content": "error",
    "jsx-a11y/anchor-is-valid": "error",
    "jsx-a11y/aria-props": "error",
    "jsx-a11y/aria-proptypes": "error",
    "jsx-a11y/aria-role": "error",
    "jsx-a11y/aria-unsupported-elements": "error",
    "jsx-a11y/heading-has-content": "error",
    "jsx-a11y/html-has-lang": "error",
    "jsx-a11y/label-has-associated-control": "error",
    "jsx-a11y/no-redundant-roles": "error",
    "jsx-a11y/role-has-required-aria-props": "error",
    "jsx-a11y/role-supports-aria-props": "error",
    // Kept ON (a stray tabIndex on a plain div still errors), but the
    // scrollable-region pattern is allowed: a horizontally-scrolling table
    // needs tabIndex for keyboard access (WCAG 2.1.1, which axe *requires*),
    // and the static rule cannot see that a div scrolls. Only labelled group
    // regions are exempted — the narrowest intentional config, not a rule-off.
    "jsx-a11y/no-noninteractive-tabindex": [
      "error",
      { tags: [], roles: ["tabpanel", "group"], allowExpressionValues: true },
    ],
  },
  ignorePatterns: [
    "node_modules/",
    ".next/",
    "playwright-report/",
    "test-results/",
    "next-env.d.ts",
  ],
};
