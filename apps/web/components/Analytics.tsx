import Script from "next/script";

import { siteUrl } from "@/lib/site";

/**
 * Third-party analytics (owner requests 2026-11-03): Microsoft Clarity and
 * Google Analytics 4. Both ids are bound to humanoidonline.com, so the tags load
 * only when the canonical origin is that host: preview, staging and local
 * builds never send data.
 */
export const CLARITY_PROJECT_ID = "z7slovol6r";
export const GA_MEASUREMENT_ID = "G-XNP76X06R4";
const ANALYTICS_HOSTS = ["humanoidonline.com", "www.humanoidonline.com"];

export function analyticsEnabled(origin: string = siteUrl()): boolean {
  return ANALYTICS_HOSTS.includes(new URL(origin).hostname);
}

export function Analytics() {
  if (!analyticsEnabled()) return null;
  return (
    <>
      <Script
        id="ga-gtag"
        src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
        strategy="afterInteractive"
      />
      <Script id="ga-config" strategy="afterInteractive">
        {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${GA_MEASUREMENT_ID}');`}
      </Script>
      <Script id="ms-clarity" strategy="afterInteractive">
        {`(function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i+"?ref=bwt";y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);})(window,document,"clarity","script","${CLARITY_PROJECT_ID}");`}
      </Script>
    </>
  );
}
