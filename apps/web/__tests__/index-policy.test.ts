// CID-04 — query-state routes must not multiply into indexable near-duplicates.
import { describe, expect, it } from "vitest";

import { cataloguePolicy, comparePolicy, MATCH_RESULT_ROBOTS } from "@/lib/index-policy";

const NOINDEX = { index: false, follow: true };

describe("comparePolicy", () => {
  it("indexes the bare compare page", () => {
    expect(comparePolicy(undefined)).toEqual({ pair: null, meta: { alternates: { canonical: "/compare" } } });
  });

  it("folds every ordering of a pair into one sorted canonical URL", () => {
    for (const raw of ["unitree-g1,booster-k1", "booster-k1,unitree-g1", " booster-k1 , unitree-g1 ", ["booster-k1", "unitree-g1"]]) {
      expect(comparePolicy(raw)).toEqual({
        pair: ["booster-k1", "unitree-g1"],
        meta: { alternates: { canonical: "/compare?ids=booster-k1,unitree-g1" } },
      });
    }
  });

  it("treats a duplicated slug as one robot", () => {
    expect(comparePolicy("unitree-g1,unitree-g1").meta).toEqual({ robots: NOINDEX });
  });

  it.each([["unitree-g1"], ["a,b,c"], ["a,b,c,d"]])("noindexes %s", (raw) => {
    expect(comparePolicy(raw)).toEqual({ pair: null, meta: { robots: NOINDEX } });
  });
});

describe("cataloguePolicy", () => {
  it("indexes only the unfiltered catalogue", () => {
    expect(cataloguePolicy({})).toEqual({ alternates: { canonical: "/robots" } });
  });

  it.each([{ q: "g1" }, { sort: "price" }, { compare: "a,b" }, { mobility: ["BIPEDAL", "WHEELED"] }])(
    "noindexes %o",
    (sp) => expect(cataloguePolicy(sp)).toEqual({ robots: NOINDEX }),
  );
});

it("never indexes or follows a match result", () => {
  expect(MATCH_RESULT_ROBOTS).toEqual({ index: false, follow: false });
});
