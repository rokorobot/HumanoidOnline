// next/font/google only works inside the Next compiler. Under vitest each font
// loader returns the same shape with inert values, so modules that import the
// root layout (e.g. social-card metadata tests) still load.
const font = () => ({
  className: "",
  variable: "",
  style: { fontFamily: "serif" },
});
export const Archivo = font;
export const Playfair_Display = font;
export const JetBrains_Mono = font;
