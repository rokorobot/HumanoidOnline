import Script from "next/script";

import { siteUrl } from "@/lib/site";

/**
 * Microsoft Clarity analytics (owner request 2026-11-03). The project id is
 * bound to humanoidonline.com, so the tag loads only when the canonical origin
 * is that host: preview, staging and local builds never send sessions.
 */
export const CLARITY_PROJECT_ID = "z7slovol6r";
const CLARITY_HOSTS = ["humanoidonline.com", "www.humanoidonline.com"];

export function clarityEnabled(origin: string = siteUrl()): boolean {
  return CLARITY_HOSTS.includes(new URL(origin).hostname);
}

export function ClarityScript() {
  if (!clarityEnabled()) return null;
  return (
    <Script id="ms-clarity" strategy="afterInteractive">
      {`(function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i+"?ref=bwt";y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);})(window,document,"clarity","script","${CLARITY_PROJECT_ID}");`}
    </Script>
  );
}
