// UX-02B - provider (seller) display names.
//
// Offers carry only a provider SLUG. The one authoritative slug -> name source the API
// already returns is `ManufacturerDetail.providers: {slug, name, type}[]` (the maker's own
// stores/channels). Third-party sellers (resellers) are not in that list, so they cannot be
// named from the payload - and a slug is never Title-Cased into a company name. An unnamed
// seller is shown as an identifier ("Seller ref: alza-cz", lower-case, as stored); the
// slug always rides along in `data-provider`.

export type ProviderNames = Record<string, string>;

export function providerNamesFrom(providers: { slug: string; name: string; type?: string }[] | null | undefined): ProviderNames {
  const out: ProviderNames = {};
  for (const p of providers ?? []) {
    if (p.slug && p.name) out[p.slug] = p.name;
  }
  return out;
}

export interface ProviderLabel {
  text: string;
  /** True when `text` is an authoritative name from the API; false for the identifier fallback. */
  named: boolean;
}

export function providerLabel(
  slug: string,
  names?: ProviderNames | null,
  apiName?: string | null,
): ProviderLabel {
  // Precedence: the name the API sent with the offer -> the maker's own providers list ->
  // a neutral identifier. A slug is never turned into a name.
  const name = apiName?.trim() || names?.[slug];
  return name ? { text: name, named: true } : { text: `Seller ref: ${slug}`, named: false };
}
