// /contact — the public contact route, and the crawler contact mechanism that
// /crawler-policy points site owners to (docs/16 §13, Gate R). Submissions go
// to Netlify Forms; no personal email address is published anywhere.
import type { Metadata } from "next";
import Link from "next/link";

import { ContactForm } from "@/components/ContactForm";
import { SectionIndex } from "@/components/SectionIndex";
import { SiteNav } from "@/components/SiteNav";
import { SystemHeader } from "@/components/SystemHeader";
import { absoluteUrl } from "@/lib/site";

export function generateMetadata(): Metadata {
  return {
    title: "Contact",
    description:
      "Contact HumanoidOnline: general questions, data corrections, manufacturers and providers, and requests about our crawler.",
    alternates: { canonical: absoluteUrl("/contact") },
  };
}

export default function ContactPage() {
  return (
    <>
      <SystemHeader title="CONTACT / HUMANOIDONLINE" />
      <div className="wrap">
        <SiteNav active={null} />
        <div className="pagebar">
          <div>
            <SectionIndex>CONTACT</SectionIndex>
            <h1>Contact HumanoidOnline</h1>
          </div>
        </div>
        <div className="contact-layout">
          <div className="prose">
            <p>
              Use this form for general questions, to report a data error on a robot or
              manufacturer page, or if you represent a manufacturer or provider.
            </p>
            <p>
              Site owners can also use it to ask about our crawler, request a lower crawl
              frequency, report a crawler problem or ask for their site to be excluded. See
              the <Link href="/crawler-policy">crawler policy</Link> for how the crawler
              behaves and how robots.txt controls it.
            </p>
          </div>
          <ContactForm />
        </div>
      </div>
    </>
  );
}
