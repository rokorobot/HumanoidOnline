# HumanoidOnline — Rough Wireframes (structure only)

**Status:** Deliberately low fidelity. These fix *what appears and in what order*, nothing about appearance. Padding, colors, fonts, cards, breakpoints, icons, imagery, motion: all decided later in the UI/UX stage. Do not spend cycles on visual polish while implementing against these.

---

## Global header (every page)

```
-------------------------------------------------------------
LOGO | Robots  Compare  Manufacturers  Use Cases |  [FIND A HUMANOID]
-------------------------------------------------------------
```

## `/` Home

```
-------------------------------------------------------------
            Find the right humanoid robot

     Compare capabilities, commercial availability,
     pricing and deployment options across the market.

        [ Search robots.......................... ]

        [ Explore Robots ]   [ Find a Humanoid ]
-------------------------------------------------------------
 Commercially accessible
 [RobotCard] [RobotCard] [RobotCard] [RobotCard]
-------------------------------------------------------------
 Explore by application
 [Manufacturing] [Logistics] [Research] [Hospitality] [Events] [...]
-------------------------------------------------------------
 Manufacturers
 [MfrCard] [MfrCard] [MfrCard] [MfrCard]
-------------------------------------------------------------
 Market snapshot
 N humanoids tracked · N commercially accessible ·
 N in pilot/deployment · N manufacturers
-------------------------------------------------------------
```

## `/robots` Catalogue

```
-------------------------------------------------------------
 FILTERS                |  Results (N)          sort: [v]
                        |
 Commercial             |  [RobotCard] [RobotCard] [RobotCard]
  [ ] status …          |  [RobotCard] [RobotCard] [RobotCard]
  [ ] purchase          |
  [ ] rental            |  RobotCard =
  [ ] lease/RaaS        |   image / name / manufacturer
  region [v]            |   CommercialStatusBadge
  price [----o----]     |   payload · height · mobility
 Physical               |   PricingSummary ("$16,000" | "From $X"
  payload [___] kg      |     | "$X–$Y" | "Estimated $X"
                        |     | "Price on request" ← QUOTE_ONLY
                        |     | "No confirmed pricing" ← no data)
  height  [___] cm      |   AvailabilityBadge
 Intelligence           |   [ Compare + ]
  [ ] autonomy …        |
 Developer              |
  [ ] SDK  [ ] ROS      |
-------------------------------------------------------------
```

## `/robots/[slug]` Robot Detail

```
-------------------------------------------------------------
 NAME            Manufacturer        CommercialStatusBadge
 Hero summary sentence.
                          [ Compare + ]  [ Request Availability ]
-------------------------------------------------------------
 Overview | Specifications | Capabilities | Availability | Evidence
-------------------------------------------------------------
 Specifications      Capabilities        Commercial Availability
 (table)             (badges + detail)    mode | region | status
                                          RAAS | US     | Available
 Pricing                                  (absence → "No confirmed
  type + amount + EvidenceBadge            commercial availability")
-------------------------------------------------------------
 Deployments / Evidence
  customer · region · use case · EvidenceBadge("Verified 2026-06-15")
-------------------------------------------------------------
 COMMERCIAL ACTION PANEL  (v0.1: one generic CTA)
        [ Request Availability ]
  (Phase 3+: Rent | Buy | Lease-RaaS buttons appear here,
   driven by availability_offer rows — same panel, no redesign)
-------------------------------------------------------------
```

## `/compare`

```
-------------------------------------------------------------
 [Robot A v] [Robot B v] [+ add]                 [share link]
-------------------------------------------------------------
                A            B
 COMMERCIAL
  price        $16,000      Quote only
  status       COMMERCIAL   RAAS_DEPLOYMENT
  purchase     Available    —
  rental       —            —
  lease/RaaS   —            Available (US)
 PHYSICAL
  payload      3 kg         16 kg
  …
 DEPLOYMENT
  deployments  Unknown      GXO (Verified)
-------------------------------------------------------------
```

## `/find-a-humanoid` Wizard → `/matches/[id]`

```
 Step 1..N (one question per step, progress indicator)
  What do you need the robot to do? → industry → task → country
  → environment → payload → hours → manipulation? → autonomy?
  → budget → when? → transaction preference
     (Unknown / Rent / Buy / Lease / Robots-as-a-Service / Flexible)
                    [ See matches ]
-------------------------------------------------------------
 /matches/[id]
 4 humanoids match your requirements        [adjust requirements]

 BEST COMMERCIAL FIT                          82%
 [MatchCard: Robot · manufacturer · score
   ✓ commercial deployment available
   ✓ suitable payload
   ⚠ pricing is quote-only
   [ Request commercial help ]  [ details ] ]

 BEST LOWER-COST OPTION …
 BEST DEVELOPER PLATFORM …

 (empty state: "No robot currently matches — the payload
  requirement of 40 kg eliminated all candidates."
  [ Tell us anyway — we track the market ] → lead form)
-------------------------------------------------------------
```

## `/manufacturers/[slug]`, `/use-cases/[slug]`

```
 MANUFACTURER: overview → humanoids (RobotCards) → applications
  → commercial model → deployment geography → customers/deployments
  → [ Request Information ]

 USE CASE: description → typical tasks → suitable robots
  (ranked, with readiness + limitations) → typical requirements
  → key limitations → [ Find a robot for this application ]
```
