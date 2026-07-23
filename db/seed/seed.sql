-- =============================================================================
-- HumanoidOnline — Seed Dataset (schema stress test)
-- =============================================================================
-- PURPOSE: force the schema, API and UI to handle real-world variation:
--   public price / quote-only / estimated / range / UNKNOWN price
--   purchasable / RaaS-only / rental-only / research / prototype / discontinued
--   variants, multiple regions, multiple billing periods,
--   robots with NO confirmed commercial availability at all.
--
-- DATA QUALITY NOTE: commercial figures here are INDICATIVE seed values for
-- development ("no commercial fact without evidence" — evidence rows carry
-- confidence levels, most deliberately unverified). Before any public launch,
-- every price/availability/deployment claim must be re-verified through the
-- evidence workflow. Entries marked VERIFIED exist to exercise the UI, not as
-- editorial truth.
--
-- Load order: db/schema.sql first, then this file. Idempotent on a fresh DB.
-- =============================================================================

SET search_path TO humanoid, public;
BEGIN;

-- ---------------------------------------------------------------------------
-- REGIONS
-- ---------------------------------------------------------------------------
INSERT INTO region (type, code, name, iso_country) VALUES
 ('GLOBAL','GLOBAL','Global',NULL),
 ('ECONOMIC_ZONE','EU','European Union',NULL),
 ('ECONOMIC_ZONE','APAC','Asia-Pacific',NULL),
 ('COUNTRY','US','United States','US'),
 ('COUNTRY','CN','China','CN'),
 ('COUNTRY','UK','United Kingdom','GB'),
 ('COUNTRY','NO','Norway','NO'),
 ('COUNTRY','CA','Canada','CA');

INSERT INTO region (parent_id, type, code, name, iso_country) VALUES
 ((SELECT id FROM region WHERE code='EU'),'COUNTRY','DE','Germany','DE'),
 ((SELECT id FROM region WHERE code='EU'),'COUNTRY','CZ','Czech Republic','CZ'),
 ((SELECT id FROM region WHERE code='EU'),'COUNTRY','ES','Spain','ES');

-- ---------------------------------------------------------------------------
-- MANUFACTURERS (15)
-- ---------------------------------------------------------------------------
INSERT INTO manufacturer (slug, name, country_region_id, website_url, founded_year, description, target_markets, commercial_model, deployment_status) VALUES
 ('unitree','Unitree Robotics',(SELECT id FROM region WHERE code='CN'),'https://www.unitree.com',2016,'Consumer-priced legged and humanoid robots sold directly online.','{research,education,industry}','Direct online sale','COMMERCIAL'),
 ('agility-robotics','Agility Robotics',(SELECT id FROM region WHERE code='US'),'https://www.agilityrobotics.com',2015,'Digit humanoid for logistics, delivered primarily as RaaS.','{logistics,warehouse}','RaaS / partner deployment','RAAS_DEPLOYMENT'),
 ('tesla','Tesla',(SELECT id FROM region WHERE code='US'),'https://www.tesla.com',2003,'Optimus general-purpose humanoid program.','{manufacturing}','Internal deployment first','PROTOTYPE'),
 ('figure-ai','Figure',(SELECT id FROM region WHERE code='US'),'https://www.figure.ai',2022,'General-purpose humanoids piloted in automotive manufacturing.','{manufacturing,logistics}','Commercial pilots','PILOT'),
 ('boston-dynamics','Boston Dynamics',(SELECT id FROM region WHERE code='US'),'https://www.bostondynamics.com',1992,'Electric Atlas humanoid in development with automotive partners.','{manufacturing,research}','Partner development','DEVELOPMENT'),
 ('apptronik','Apptronik',(SELECT id FROM region WHERE code='US'),'https://www.apptronik.com',2016,'Apollo humanoid for industrial work.','{manufacturing,logistics}','Commercial pilots','PILOT'),
 ('sanctuary-ai','Sanctuary AI',(SELECT id FROM region WHERE code='CA'),'https://www.sanctuary.ai',2018,'Phoenix general-purpose humanoid with teleoperation-first training.','{retail,industry}','Pilots','PROTOTYPE'),
 ('1x-technologies','1X Technologies',(SELECT id FROM region WHERE code='NO'),'https://www.1x.tech',2014,'EVE wheeled humanoid and NEO home humanoid.','{home,security,logistics}','Direct + subscription','EARLY_ACCESS'),
 ('fourier','Fourier Intelligence',(SELECT id FROM region WHERE code='CN'),'https://www.fftai.com',2015,'GR-series humanoids for research and rehabilitation.','{research,healthcare}','Direct sale','COMMERCIAL'),
 ('ubtech','UBTech Robotics',(SELECT id FROM region WHERE code='CN'),'https://www.ubtrobot.com',2012,'Walker S industrial humanoids piloted in Chinese EV factories.','{manufacturing}','Factory pilots','PILOT'),
 ('pal-robotics','PAL Robotics',(SELECT id FROM region WHERE code='ES'),'https://pal-robotics.com',2004,'European research humanoid platforms (TALOS, REEM-C).','{research,education}','Direct sale to institutions','COMMERCIAL'),
 ('engineered-arts','Engineered Arts',(SELECT id FROM region WHERE code='UK'),'https://www.engineeredarts.co.uk',2005,'Ameca expressive humanoid for events and attractions.','{events,entertainment,research}','Sale and rental','COMMERCIAL'),
 ('kepler','Kepler Robotics',(SELECT id FROM region WHERE code='CN'),'https://www.gotokepler.com',2023,'Forerunner-series humanoids targeting aggressive price points.','{industry,research}','Direct sale','EARLY_ACCESS'),
 ('booster-robotics','Booster Robotics',(SELECT id FROM region WHERE code='CN'),'https://www.boosterobotics.com',2023,'Developer-oriented humanoid platforms.','{research,education}','Direct sale','COMMERCIAL'),
 ('honda','Honda',(SELECT id FROM region WHERE code='APAC'),'https://global.honda',1948,'ASIMO pioneer humanoid program (retired).','{research}','Research program','DISCONTINUED');

-- ---------------------------------------------------------------------------
-- PROVIDERS
-- ---------------------------------------------------------------------------
INSERT INTO provider (slug, type, name, manufacturer_id, country_region_id, accepts_leads, lead_fee_model, description) VALUES
 ('unitree-store','OEM','Unitree Online Store',(SELECT id FROM manufacturer WHERE slug='unitree'),(SELECT id FROM region WHERE code='CN'),false,NULL,'Direct OEM web store.'),
 ('agility-raas','RAAS_PROVIDER','Agility Robotics (RaaS)',(SELECT id FROM manufacturer WHERE slug='agility-robotics'),(SELECT id FROM region WHERE code='US'),true,'per_lead','OEM-operated RaaS deployments.'),
 ('engineered-arts-oem','OEM','Engineered Arts',(SELECT id FROM manufacturer WHERE slug='engineered-arts'),(SELECT id FROM region WHERE code='UK'),true,'per_lead','OEM sale and event rental.'),
 ('event-robots-eu','RENTAL_PROVIDER','EventRobots EU',NULL,(SELECT id FROM region WHERE code='DE'),true,'referral_commission','Independent European event-rental provider.'),
 ('humanoid-integrators','INTEGRATOR','Humanoid Integrators GmbH',NULL,(SELECT id FROM region WHERE code='DE'),true,'referral_commission','Industrial integration partner (seed example).');

-- ---------------------------------------------------------------------------
-- USE CASES (7)
-- ---------------------------------------------------------------------------
INSERT INTO use_case (slug, name, category, description, typical_tasks, typical_requirements, key_limitations) VALUES
 ('warehouse-logistics','Warehouse & Logistics','logistics','Humanoids for material movement in warehouses and distribution centers.','{tote handling,material movement,unloading,loading,line feeding,repetitive handling}','Sustained duty cycles, 10-16 kg payloads, integration with WMS, safety compliance around workers.','Runtime/charging strategy; navigation in dynamic aisles; per-unit economics vs conveyors.'),
 ('manufacturing','Manufacturing','industry','Humanoids on production lines and intralogistics in factories.','{parts sequencing,machine tending,kitting,quality inspection support}','Repeatability, payload, uptime, integration with MES, functional safety.','Mostly pilot maturity; cycle-time competitiveness vs fixed automation.'),
 ('research-education','Research & Education','research','Humanoid platforms for labs and universities.','{locomotion research,manipulation research,HRI studies,teaching}','SDK/API access, ROS support, documentation, spare parts.','Cost; developer support quality varies widely.'),
 ('hospitality','Hospitality','service','Front-of-house service and guest interaction.','{greeting,guidance,information,light delivery}','Expressive interaction, speech, safe navigation among guests.','Manipulation typically limited; novelty-driven ROI.'),
 ('events-entertainment','Events & Entertainment','service','Humanoids as attractions, presenters and brand activations.','{presenting,interaction,photo engagement}','Expressiveness, reliability over show hours, transportability.','Often rented, not owned; limited autonomy needed.'),
 ('home','Home','consumer','Domestic assistance and companionship.','{tidying,fetching,companionship}','Safety around family, quiet operation, subscription economics.','Earliest commercial stage of all; expectations management.'),
 ('inspection','Inspection','industry','Walking inspection of industrial facilities.','{gauge reading,leak detection,patrol}','Environmental resistance, autonomy, sensor payloads.','Quadrupeds currently dominate this niche.');

-- ---------------------------------------------------------------------------
-- CAPABILITY CATALOGUE
-- ---------------------------------------------------------------------------
INSERT INTO capability (slug, name, category, description) VALUES
 ('bimanual-manipulation','Bimanual manipulation','MANIPULATION','Coordinated two-handed object handling.'),
 ('dexterous-hands','Dexterous multi-finger hands','MANIPULATION','Articulated fingers beyond parallel grippers.'),
 ('stair-climbing','Stair climbing','MOBILITY','Ascends/descends stairs.'),
 ('dynamic-walking','Dynamic walking','MOBILITY','Robust dynamic bipedal locomotion.'),
 ('autonomous-navigation','Autonomous navigation','AI_AUTONOMY','Self-directed navigation in mapped spaces.'),
 ('teleoperation','Teleoperation','AI_AUTONOMY','Remote human piloting.'),
 ('voice-interaction','Voice interaction','INTERACTION','Spoken-language interaction.'),
 ('expressive-face','Expressive face','INTERACTION','Human-like facial expression.'),
 ('object-recognition','Object recognition','PERCEPTION','Vision-based object identification.'),
 ('force-control','Force-controlled joints','MANIPULATION','Compliant, force-aware actuation.');

-- ---------------------------------------------------------------------------
-- SPEC DEFINITIONS (long-tail examples)
-- ---------------------------------------------------------------------------
INSERT INTO spec_definition (key, label, category, value_type, unit, is_filterable) VALUES
 ('reach_cm','Arm reach','MANIPULATION','NUMBER','cm',false),
 ('charge_time_min','Charge time','OTHER','NUMBER','min',false),
 ('ip_rating','IP rating','SAFETY','TEXT',NULL,false),
 ('swappable_battery','Swappable battery','OTHER','BOOLEAN',NULL,true);

-- ---------------------------------------------------------------------------
-- ROBOTS (20) — the variation matrix
-- ---------------------------------------------------------------------------

-- 1. Unitree G1 — COMMERCIAL, PUBLIC price, variants, developer-friendly
INSERT INTO robot (slug, manufacturer_id, name, model_code, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, walk_speed_ms, runtime_minutes, mobility, degrees_of_freedom,
                   hand_type, autonomy, has_manipulation, has_teleoperation, has_vision, has_language_ui,
                   has_sdk, has_api, ros_support, developer_edition, simulation_support,
                   lowest_purchase_price, lowest_price_currency, is_published)
VALUES ('unitree-g1',(SELECT id FROM manufacturer WHERE slug='unitree'),'G1','G1',
 'Compact, affordably priced humanoid that made research platforms accessible.','COMMERCIAL',2024,
 130,35,3,1.8,120,'BIPEDAL',23,'optional dexterous hands','TELEOPERATED',true,true,true,false,
 true,true,true,true,true,16000,'USD',true);

-- 2. Unitree H1 — COMMERCIAL, PUBLIC price, larger platform
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, walk_speed_ms, mobility,
                   autonomy, has_manipulation, has_teleoperation, has_vision, has_sdk, ros_support, developer_edition,
                   lowest_purchase_price, lowest_price_currency, is_published)
VALUES ('unitree-h1',(SELECT id FROM manufacturer WHERE slug='unitree'),'H1',
 'Full-size high-performance research humanoid.','COMMERCIAL',2023,
 180,47,30,3.3,'BIPEDAL','TELEOPERATED',true,true,true,true,true,true,90000,'USD',true);

-- 3. Unitree R1 — LIMITED_COMMERCIAL, FROM price
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, mobility, autonomy, has_sdk, developer_edition,
                   lowest_purchase_price, lowest_price_currency, is_published)
VALUES ('unitree-r1',(SELECT id FROM manufacturer WHERE slug='unitree'),'R1',
 'Ultra-low-cost entry humanoid.','LIMITED_COMMERCIAL',2025,
 121,25,'BIPEDAL','TELEOPERATED',true,true,5900,'USD',true);

-- 4. Agility Digit — RAAS_DEPLOYMENT, quote-only, NOT purchasable, heavy evidence
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, mobility, autonomy,
                   has_manipulation, has_vision, has_api, is_published)
VALUES ('digit',(SELECT id FROM manufacturer WHERE slug='agility-robotics'),'Digit',
 'Logistics humanoid in formal commercial RaaS deployments.','RAAS_DEPLOYMENT',2019,
 175,65,16,'BIPEDAL','TASK_AUTONOMOUS',true,true,true,true);
 -- runtime deliberately NULL: unknown stays unknown

-- 5. Tesla Optimus — PROTOTYPE, NO pricing, NO availability (fully unknown)
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, mobility, has_manipulation, has_vision, is_published)
VALUES ('optimus',(SELECT id FROM manufacturer WHERE slug='tesla'),'Optimus',
 'General-purpose humanoid program; internal factory use first.','PROTOTYPE',2022,
 173,57,'BIPEDAL',true,true,true);

-- 6. Figure 02 — PILOT with automotive deployment evidence, quote-only
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, mobility, autonomy, has_manipulation, has_vision, has_language_ui, is_published)
VALUES ('figure-02',(SELECT id FROM manufacturer WHERE slug='figure-ai'),'Figure 02',
 'General-purpose humanoid piloted on automotive production lines.','PILOT',2024,
 168,70,20,'BIPEDAL','SUPERVISED_AUTONOMY',true,true,true,true);

-- 7. Figure 03 — ANNOUNCED only (nothing else known)
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year, mobility, is_published)
VALUES ('figure-03',(SELECT id FROM manufacturer WHERE slug='figure-ai'),'Figure 03',
 'Next-generation platform, announced.','ANNOUNCED',2025,'BIPEDAL',true);

-- 8. Atlas (electric) — DEVELOPMENT, no offers
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, mobility, has_manipulation, is_published)
VALUES ('atlas-electric',(SELECT id FROM manufacturer WHERE slug='boston-dynamics'),'Atlas (electric)',
 'All-electric Atlas developed with automotive partners.','DEVELOPMENT',2024,150,'BIPEDAL',true,true);

-- 9. Apptronik Apollo — PILOT, quote-only
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, runtime_minutes, mobility, autonomy, has_manipulation, is_published)
VALUES ('apollo',(SELECT id FROM manufacturer WHERE slug='apptronik'),'Apollo',
 'Industrial humanoid with swappable batteries, in manufacturing pilots.','PILOT',2023,
 172,73,25,240,'BIPEDAL','SUPERVISED_AUTONOMY',true,true);

-- 10. Sanctuary Phoenix — PROTOTYPE, teleop-first
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, mobility, autonomy, has_manipulation, has_teleoperation, is_published)
VALUES ('phoenix',(SELECT id FROM manufacturer WHERE slug='sanctuary-ai'),'Phoenix',
 'Dexterity-focused humanoid trained through teleoperation.','PROTOTYPE',2023,
 170,70,25,'BIPEDAL','TELEOPERATED',true,true,true);

-- 11. 1X NEO — EARLY_ACCESS home robot, ESTIMATED purchase + ESTIMATED subscription
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, mobility, autonomy, has_manipulation, has_language_ui, is_published)
VALUES ('neo',(SELECT id FROM manufacturer WHERE slug='1x-technologies'),'NEO',
 'Soft-bodied home humanoid offered in early access.','EARLY_ACCESS',2024,
 165,30,'BIPEDAL','ASSISTED',true,true,true);

-- 12. 1X EVE — LIMITED_COMMERCIAL, wheeled
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, mobility, autonomy, has_manipulation, is_published)
VALUES ('eve',(SELECT id FROM manufacturer WHERE slug='1x-technologies'),'EVE',
 'Wheeled humanoid for security and logistics tasks.','LIMITED_COMMERCIAL',2019,
 186,87,'WHEELED','SUPERVISED_AUTONOMY',true,true);

-- 13. Fourier GR-2 — COMMERCIAL in CN, RANGE estimated price
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, mobility, has_sdk, ros_support, is_published)
VALUES ('gr-2',(SELECT id FROM manufacturer WHERE slug='fourier'),'GR-2',
 'Research/rehabilitation humanoid sold to institutions.','COMMERCIAL',2024,
 175,63,10,'BIPEDAL',true,true,true);

-- 14. UBTech Walker S1 — PILOT, EV-factory deployments
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, mobility, autonomy, has_manipulation, is_published)
VALUES ('walker-s1',(SELECT id FROM manufacturer WHERE slug='ubtech'),'Walker S1',
 'Industrial humanoid piloted in Chinese EV factories.','PILOT',2024,
 172,76,15,'BIPEDAL','SUPERVISED_AUTONOMY',true,true);

-- 15. PAL TALOS — COMMERCIAL research platform, quote-only (EUR)
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, mobility, has_sdk, ros_support, developer_edition, is_published)
VALUES ('talos',(SELECT id FROM manufacturer WHERE slug='pal-robotics'),'TALOS',
 'High-performance torque-controlled research humanoid.','COMMERCIAL',2017,
 175,95,6,'BIPEDAL',true,true,true,true);

-- 16. PAL REEM-C — COMMERCIAL research platform, quote-only
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, mobility, has_sdk, ros_support, is_published)
VALUES ('reem-c',(SELECT id FROM manufacturer WHERE slug='pal-robotics'),'REEM-C',
 'Full-size biped research platform.','COMMERCIAL',2013,165,80,'BIPEDAL',true,true,true);

-- 17. Ameca — COMMERCIAL, RENTAL offers active today (events) + quote-only purchase
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, mobility, autonomy, has_language_ui, is_published)
VALUES ('ameca',(SELECT id FROM manufacturer WHERE slug='engineered-arts'),'Ameca',
 'Expressive humanoid for events, attractions and HRI research.','COMMERCIAL',2021,
 187,'STATIONARY','ASSISTED',true,true);

-- 18. Kepler K2 — EARLY_ACCESS, ESTIMATED price, WAITLIST in CN
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, payload_kg, mobility, is_published)
VALUES ('kepler-k2',(SELECT id FROM manufacturer WHERE slug='kepler'),'Forerunner K2',
 'Aggressively priced industrial humanoid.','EARLY_ACCESS',2024,178,85,15,'BIPEDAL',true);

-- 19. Booster T1 — COMMERCIAL developer platform, FROM estimated price
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, mobility, has_sdk, ros_support, developer_edition, is_published)
VALUES ('booster-t1',(SELECT id FROM manufacturer WHERE slug='booster-robotics'),'Booster T1',
 'Compact developer humanoid popular in robot competitions.','COMMERCIAL',2024,
 118,30,'BIPEDAL',true,true,true,true);

-- 20. Honda ASIMO — DISCONTINUED (exclusion-rule test)
INSERT INTO robot (slug, manufacturer_id, name, summary, commercial_status, announced_year,
                   height_cm, weight_kg, mobility, is_published)
VALUES ('asimo',(SELECT id FROM manufacturer WHERE slug='honda'),'ASIMO',
 'Pioneering research humanoid; program retired.','DISCONTINUED',2000,130,54,'BIPEDAL',true);

-- ---------------------------------------------------------------------------
-- VARIANTS
-- ---------------------------------------------------------------------------
INSERT INTO robot_variant (robot_id, slug, name, is_developer, description) VALUES
 ((SELECT id FROM robot WHERE slug='unitree-g1'),'g1','G1 (base)',false,'Base configuration.'),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),'g1-edu','G1 EDU',true,'Education/developer configuration with dexterous hands option.'),
 ((SELECT id FROM robot WHERE slug='digit'),'digit-v5','Digit v5',false,'Fifth-generation deployment model.'),
 ((SELECT id FROM robot WHERE slug='neo'),'neo-early','NEO Early Access',false,'Early-access home configuration.');

-- ---------------------------------------------------------------------------
-- STATUS HISTORY (example timeline for Digit)
-- ---------------------------------------------------------------------------
INSERT INTO robot_status_history (robot_id, status, effective_at, note) VALUES
 ((SELECT id FROM robot WHERE slug='digit'),'PILOT','2023-06-01','Warehouse pilots.'),
 ((SELECT id FROM robot WHERE slug='digit'),'RAAS_DEPLOYMENT','2025-09-01','Formal commercial RaaS deployments; multi-year contracted orders.');

-- ---------------------------------------------------------------------------
-- PRICING OFFERS — every price_type exercised; Optimus/Atlas/Phoenix have NONE
-- ---------------------------------------------------------------------------
INSERT INTO pricing_offer (robot_id, variant_id, provider_id, region_id, transaction_type, price_type, currency, price, price_min, price_max, billing_period, note) VALUES
 -- PUBLIC one-time
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM robot_variant WHERE slug='g1'),(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','PUBLIC','USD',16000,NULL,NULL,'ONE_TIME','Base configuration list price.'),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM robot_variant WHERE slug='g1-edu'),(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'DEVELOPER','FROM','USD',40000,NULL,NULL,'ONE_TIME','EDU configuration, from-price depending on hands/compute.'),
 ((SELECT id FROM robot WHERE slug='unitree-h1'),NULL,(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','PUBLIC','USD',90000,NULL,NULL,'ONE_TIME',NULL),
 ((SELECT id FROM robot WHERE slug='unitree-r1'),NULL,(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','FROM','USD',5900,NULL,NULL,'ONE_TIME','Entry configuration.'),
 -- QUOTE_ONLY (no number)
 ((SELECT id FROM robot WHERE slug='digit'),NULL,(SELECT id FROM provider WHERE slug='agility-raas'),(SELECT id FROM region WHERE code='US'),'RAAS','QUOTE_ONLY','USD',NULL,NULL,NULL,'ANNUAL','Priced per deployment contract.'),
 ((SELECT id FROM robot WHERE slug='figure-02'),NULL,NULL,(SELECT id FROM region WHERE code='US'),'PILOT','QUOTE_ONLY','USD',NULL,NULL,NULL,'ONE_TIME',NULL),
 ((SELECT id FROM robot WHERE slug='apollo'),NULL,NULL,(SELECT id FROM region WHERE code='US'),'PILOT','QUOTE_ONLY','USD',NULL,NULL,NULL,'ONE_TIME',NULL),
 ((SELECT id FROM robot WHERE slug='talos'),NULL,NULL,(SELECT id FROM region WHERE code='EU'),'PURCHASE','QUOTE_ONLY','EUR',NULL,NULL,NULL,'ONE_TIME','Institutional sale.'),
 ((SELECT id FROM robot WHERE slug='reem-c'),NULL,NULL,(SELECT id FROM region WHERE code='EU'),'PURCHASE','QUOTE_ONLY','EUR',NULL,NULL,NULL,'ONE_TIME',NULL),
 ((SELECT id FROM robot WHERE slug='eve'),NULL,NULL,(SELECT id FROM region WHERE code='US'),'SUBSCRIPTION','QUOTE_ONLY','USD',NULL,NULL,NULL,'MONTHLY',NULL),
 ((SELECT id FROM robot WHERE slug='ameca'),NULL,(SELECT id FROM provider WHERE slug='engineered-arts-oem'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','QUOTE_ONLY','GBP',NULL,NULL,NULL,'ONE_TIME',NULL),
 ((SELECT id FROM robot WHERE slug='walker-s1'),NULL,NULL,(SELECT id FROM region WHERE code='CN'),'PILOT','QUOTE_ONLY','CNY',NULL,NULL,NULL,'ONE_TIME',NULL),
 -- ESTIMATED point + subscription (two billing periods for one robot)
 ((SELECT id FROM robot WHERE slug='neo'),(SELECT id FROM robot_variant WHERE slug='neo-early'),NULL,(SELECT id FROM region WHERE code='US'),'PURCHASE','ESTIMATED','USD',20000,NULL,NULL,'ONE_TIME','Reported early-access price; unverified.'),
 ((SELECT id FROM robot WHERE slug='neo'),(SELECT id FROM robot_variant WHERE slug='neo-early'),NULL,(SELECT id FROM region WHERE code='US'),'SUBSCRIPTION','ESTIMATED','USD',499,NULL,NULL,'MONTHLY','Reported subscription alternative; unverified.'),
 -- RANGE
 ((SELECT id FROM robot WHERE slug='gr-2'),NULL,NULL,(SELECT id FROM region WHERE code='CN'),'PURCHASE','RANGE','USD',NULL,120000,200000,'ONE_TIME','Institutional pricing band, estimated.'),
 -- ESTIMATED
 ((SELECT id FROM robot WHERE slug='kepler-k2'),NULL,NULL,(SELECT id FROM region WHERE code='CN'),'PURCHASE','ESTIMATED','USD',30000,NULL,NULL,'ONE_TIME','Target price communicated by manufacturer.'),
 ((SELECT id FROM robot WHERE slug='booster-t1'),NULL,NULL,(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','FROM','USD',35000,NULL,NULL,'ONE_TIME','Estimated from-price.'),
 -- RENTAL (daily + weekly) — Phase 3 data existing TODAY
 ((SELECT id FROM robot WHERE slug='ameca'),NULL,(SELECT id FROM provider WHERE slug='event-robots-eu'),(SELECT id FROM region WHERE code='EU'),'RENTAL','ESTIMATED','EUR',2500,NULL,NULL,'DAILY','Event rental day rate, estimated.'),
 ((SELECT id FROM robot WHERE slug='ameca'),NULL,(SELECT id FROM provider WHERE slug='event-robots-eu'),(SELECT id FROM region WHERE code='EU'),'RENTAL','ESTIMATED','EUR',9000,NULL,NULL,'WEEKLY','Event rental week rate, estimated.');

-- ---------------------------------------------------------------------------
-- AVAILABILITY OFFERS — modes × regions × statuses.
-- Optimus, Atlas, Phoenix, Figure 03, ASIMO have NO rows: availability UNKNOWN.
-- ---------------------------------------------------------------------------
INSERT INTO availability_offer (robot_id, variant_id, provider_id, region_id, transaction_type, availability_status, lead_time_days, note) VALUES
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM robot_variant WHERE slug='g1'),(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','AVAILABLE',30,'Ships from OEM store.'),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM robot_variant WHERE slug='g1-edu'),(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'DEVELOPER','AVAILABLE',45,NULL),
 ((SELECT id FROM robot WHERE slug='unitree-h1'),NULL,(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','AVAILABLE',60,NULL),
 ((SELECT id FROM robot WHERE slug='unitree-r1'),NULL,(SELECT id FROM provider WHERE slug='unitree-store'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','LIMITED',NULL,'Batch availability.'),
 ((SELECT id FROM robot WHERE slug='digit'),NULL,(SELECT id FROM provider WHERE slug='agility-raas'),(SELECT id FROM region WHERE code='US'),'RAAS','AVAILABLE',NULL,'Deployment contracts; no unit sale.'),
 ((SELECT id FROM robot WHERE slug='figure-02'),NULL,NULL,(SELECT id FROM region WHERE code='US'),'PILOT','ON_REQUEST',NULL,'Qualified commercial pilots.'),
 ((SELECT id FROM robot WHERE slug='apollo'),NULL,NULL,(SELECT id FROM region WHERE code='US'),'PILOT','ON_REQUEST',NULL,NULL),
 ((SELECT id FROM robot WHERE slug='neo'),(SELECT id FROM robot_variant WHERE slug='neo-early'),NULL,(SELECT id FROM region WHERE code='US'),'PURCHASE','PREORDER',NULL,'Early-access queue, US first.'),
 ((SELECT id FROM robot WHERE slug='eve'),NULL,NULL,(SELECT id FROM region WHERE code='US'),'SUBSCRIPTION','ON_REQUEST',NULL,NULL),
 ((SELECT id FROM robot WHERE slug='gr-2'),NULL,NULL,(SELECT id FROM region WHERE code='CN'),'PURCHASE','AVAILABLE',NULL,'Institutional buyers.'),
 ((SELECT id FROM robot WHERE slug='gr-2'),NULL,NULL,(SELECT id FROM region WHERE code='EU'),'PURCHASE','ON_REQUEST',NULL,'Via distributors.'),
 ((SELECT id FROM robot WHERE slug='walker-s1'),NULL,NULL,(SELECT id FROM region WHERE code='CN'),'PILOT','ON_REQUEST',NULL,NULL),
 ((SELECT id FROM robot WHERE slug='talos'),NULL,NULL,(SELECT id FROM region WHERE code='EU'),'PURCHASE','ON_REQUEST',180,'Built to order.'),
 ((SELECT id FROM robot WHERE slug='reem-c'),NULL,NULL,(SELECT id FROM region WHERE code='EU'),'PURCHASE','ON_REQUEST',NULL,NULL),
 ((SELECT id FROM robot WHERE slug='ameca'),NULL,(SELECT id FROM provider WHERE slug='engineered-arts-oem'),(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','ON_REQUEST',NULL,NULL),
 ((SELECT id FROM robot WHERE slug='ameca'),NULL,(SELECT id FROM provider WHERE slug='event-robots-eu'),(SELECT id FROM region WHERE code='EU'),'RENTAL','AVAILABLE',14,'Event bookings.'),
 ((SELECT id FROM robot WHERE slug='ameca'),NULL,(SELECT id FROM provider WHERE slug='engineered-arts-oem'),(SELECT id FROM region WHERE code='UK'),'RENTAL','AVAILABLE',21,NULL),
 ((SELECT id FROM robot WHERE slug='kepler-k2'),NULL,NULL,(SELECT id FROM region WHERE code='CN'),'PURCHASE','WAITLIST',NULL,NULL),
 ((SELECT id FROM robot WHERE slug='booster-t1'),NULL,NULL,(SELECT id FROM region WHERE code='GLOBAL'),'PURCHASE','AVAILABLE',30,NULL);

-- ---------------------------------------------------------------------------
-- DEPLOYMENTS — the evidence dimension
-- ---------------------------------------------------------------------------
INSERT INTO deployment (robot_id, provider_id, customer_name, region_id, use_case_id, transaction_type, unit_count, contract_value, contract_currency, started_on, status, summary) VALUES
 ((SELECT id FROM robot WHERE slug='digit'),(SELECT id FROM provider WHERE slug='agility-raas'),'GXO Logistics',(SELECT id FROM region WHERE code='US'),(SELECT id FROM use_case WHERE slug='warehouse-logistics'),'RAAS',NULL,NULL,'USD','2024-06-01','production','Multi-site RaaS deployment moving totes in distribution centers.'),
 ((SELECT id FROM robot WHERE slug='digit'),(SELECT id FROM provider WHERE slug='agility-raas'),NULL,(SELECT id FROM region WHERE code='US'),(SELECT id FROM use_case WHERE slug='warehouse-logistics'),'RAAS',NULL,300000000,'USD','2026-01-01','scaling','Reported >$300M multi-year contracted Digit v5 orders across customers.'),
 ((SELECT id FROM robot WHERE slug='figure-02'),NULL,'BMW Group',(SELECT id FROM region WHERE code='US'),(SELECT id FROM use_case WHERE slug='manufacturing'),'PILOT',NULL,NULL,'USD','2024-08-01','pilot','Production-line pilot, Spartanburg plant.'),
 ((SELECT id FROM robot WHERE slug='apollo'),NULL,'Mercedes-Benz',(SELECT id FROM region WHERE code='DE'),(SELECT id FROM use_case WHERE slug='manufacturing'),'PILOT',NULL,NULL,'EUR','2024-03-01','pilot','Intralogistics pilot in automotive manufacturing.'),
 ((SELECT id FROM robot WHERE slug='walker-s1'),NULL,'NIO',(SELECT id FROM region WHERE code='CN'),(SELECT id FROM use_case WHERE slug='manufacturing'),'PILOT',NULL,NULL,'CNY','2024-05-01','pilot','Quality-inspection support in EV assembly.'),
 ((SELECT id FROM robot WHERE slug='ameca'),(SELECT id FROM provider WHERE slug='engineered-arts-oem'),'Museum of the Future',(SELECT id FROM region WHERE code='APAC'),(SELECT id FROM use_case WHERE slug='events-entertainment'),'PURCHASE',1,NULL,'USD','2022-10-01','production','Permanent public exhibit.');

-- ---------------------------------------------------------------------------
-- EVIDENCE — mixed confidence; some VERIFIED (to exercise UI), most not
-- ---------------------------------------------------------------------------
INSERT INTO evidence_source (subject_type, subject_id, source_url, source_type, source_title, published_at, verified_at, confidence, note) VALUES
 ('PRICING_OFFER',(SELECT id FROM pricing_offer WHERE robot_id=(SELECT id FROM robot WHERE slug='unitree-g1') AND price=16000),'https://shop.unitree.com','MANUFACTURER_STORE','Unitree online store listing','2025-01-15','2026-07-01','VERIFIED','Store price observed directly.'),
 ('PRICING_OFFER',(SELECT id FROM pricing_offer WHERE robot_id=(SELECT id FROM robot WHERE slug='unitree-h1') AND price=90000),'https://shop.unitree.com','MANUFACTURER_STORE','Unitree online store listing','2024-05-01',NULL,'HIGH','Observed; re-verification pending.'),
 ('DEPLOYMENT',(SELECT id FROM deployment WHERE contract_value=300000000),'https://www.agilityrobotics.com/news','PRESS_RELEASE','Agility Robotics contracted-orders announcement','2026-05-01','2026-07-10','VERIFIED','Company-reported figure.'),
 ('DEPLOYMENT',(SELECT id FROM deployment WHERE customer_name='GXO Logistics'),'https://www.agilityrobotics.com/news','PRESS_RELEASE','GXO multi-site deployment','2024-06-15','2026-06-15','HIGH',NULL),
 ('DEPLOYMENT',(SELECT id FROM deployment WHERE customer_name='BMW Group'),NULL,'NEWS_ARTICLE','Figure–BMW pilot coverage','2024-08-10',NULL,'MEDIUM',NULL),
 ('DEPLOYMENT',(SELECT id FROM deployment WHERE customer_name='Mercedes-Benz'),NULL,'PRESS_RELEASE','Apptronik–Mercedes pilot announcement','2024-03-15',NULL,'MEDIUM',NULL),
 ('PRICING_OFFER',(SELECT id FROM pricing_offer WHERE robot_id=(SELECT id FROM robot WHERE slug='neo') AND price=20000),NULL,'NEWS_ARTICLE','Reported NEO early-access pricing','2025-10-01',NULL,'LOW','Unverified press figure; display as Estimated.'),
 ('PRICING_OFFER',(SELECT id FROM pricing_offer WHERE robot_id=(SELECT id FROM robot WHERE slug='ameca') AND billing_period='DAILY'),NULL,'DIRECT_QUOTE','Event-rental quotation (seed example)','2026-04-01',NULL,'LOW','Indicative rate from rental provider.'),
 ('AVAILABILITY_OFFER',(SELECT id FROM availability_offer WHERE robot_id=(SELECT id FROM robot WHERE slug='digit')),'https://www.agilityrobotics.com','MANUFACTURER_SITE','Agility deployment model','2026-01-01','2026-07-01','VERIFIED','RaaS-only engagement confirmed.'),
 ('COMMERCIAL_STATUS',(SELECT id FROM robot WHERE slug='asimo'),NULL,'PRESS_RELEASE','Honda ASIMO program retirement','2018-06-28','2026-07-01','VERIFIED','Program formally ended.');

-- ---------------------------------------------------------------------------
-- BLANKET PROVENANCE (G2): every published commercial fact must carry at least
-- one evidence row — "no commercial fact without evidence". The curated rows
-- above stay authoritative; these baseline rows cover the remainder at honest
-- LOW/MEDIUM confidence with verified_at NULL, so the UI can demonstrate the
-- full epistemic spectrum (LOW → MEDIUM → HIGH → VERIFIED).
-- ---------------------------------------------------------------------------

-- Commercial status of every published robot
INSERT INTO evidence_source (subject_type, subject_id, source_type, source_title, confidence, note)
SELECT 'COMMERCIAL_STATUS', r.id, 'MANUFACTURER_SITE',
       m.name || ' — product page (status assessment)',
       'MEDIUM', 'Seed baseline provenance; re-verify before launch.'
FROM robot r JOIN manufacturer m ON m.id = r.manufacturer_id
WHERE r.is_published
  AND NOT EXISTS (SELECT 1 FROM evidence_source e
                  WHERE e.subject_type='COMMERCIAL_STATUS' AND e.subject_id=r.id);

-- Every pricing offer (ESTIMATED prices get LOW confidence; the rest MEDIUM)
INSERT INTO evidence_source (subject_type, subject_id, source_type, source_title, confidence, note)
SELECT 'PRICING_OFFER', p.id,
       CASE WHEN p.price_type='ESTIMATED' THEN 'NEWS_ARTICLE'::source_type
            ELSE 'MANUFACTURER_SITE'::source_type END,
       m.name || ' ' || r.name || ' — ' || p.transaction_type || ' pricing (' || p.price_type || ')',
       CASE WHEN p.price_type='ESTIMATED' THEN 'LOW'::confidence_level
            ELSE 'MEDIUM'::confidence_level END,
       'Seed baseline provenance; re-verify before launch.'
FROM pricing_offer p
JOIN robot r ON r.id = p.robot_id JOIN manufacturer m ON m.id = r.manufacturer_id
WHERE r.is_published
  AND NOT EXISTS (SELECT 1 FROM evidence_source e
                  WHERE e.subject_type='PRICING_OFFER' AND e.subject_id=p.id);

-- Every availability offer
INSERT INTO evidence_source (subject_type, subject_id, source_type, source_title, confidence, note)
SELECT 'AVAILABILITY_OFFER', a.id, 'MANUFACTURER_SITE',
       m.name || ' ' || r.name || ' — ' || a.transaction_type || ' availability',
       'MEDIUM', 'Seed baseline provenance; re-verify before launch.'
FROM availability_offer a
JOIN robot r ON r.id = a.robot_id JOIN manufacturer m ON m.id = r.manufacturer_id
WHERE r.is_published
  AND NOT EXISTS (SELECT 1 FROM evidence_source e
                  WHERE e.subject_type='AVAILABILITY_OFFER' AND e.subject_id=a.id);

-- Every deployment
INSERT INTO evidence_source (subject_type, subject_id, source_type, source_title, confidence, note)
SELECT 'DEPLOYMENT', d.id, 'NEWS_ARTICLE',
       r.name || ' deployment — ' || COALESCE(d.customer_name,'undisclosed customer'),
       'MEDIUM', 'Seed baseline provenance; re-verify before launch.'
FROM deployment d JOIN robot r ON r.id = d.robot_id
WHERE r.is_published
  AND NOT EXISTS (SELECT 1 FROM evidence_source e
                  WHERE e.subject_type='DEPLOYMENT' AND e.subject_id=d.id);

-- ---------------------------------------------------------------------------
-- G2 SELF-CHECK: abort the load if any published commercial fact lacks evidence.
-- (Seed must satisfy acceptance criterion G2 by construction.)
-- ---------------------------------------------------------------------------
DO $$
DECLARE missing INT;
BEGIN
    SELECT
      (SELECT count(*) FROM robot r WHERE r.is_published AND NOT EXISTS
        (SELECT 1 FROM evidence_source e WHERE e.subject_type='COMMERCIAL_STATUS' AND e.subject_id=r.id))
    + (SELECT count(*) FROM pricing_offer p JOIN robot r ON r.id=p.robot_id
       WHERE r.is_published AND NOT EXISTS
        (SELECT 1 FROM evidence_source e WHERE e.subject_type='PRICING_OFFER' AND e.subject_id=p.id))
    + (SELECT count(*) FROM availability_offer a JOIN robot r ON r.id=a.robot_id
       WHERE r.is_published AND NOT EXISTS
        (SELECT 1 FROM evidence_source e WHERE e.subject_type='AVAILABILITY_OFFER' AND e.subject_id=a.id))
    + (SELECT count(*) FROM deployment d JOIN robot r ON r.id=d.robot_id
       WHERE r.is_published AND NOT EXISTS
        (SELECT 1 FROM evidence_source e WHERE e.subject_type='DEPLOYMENT' AND e.subject_id=d.id))
    INTO missing;
    IF missing > 0 THEN
        RAISE EXCEPTION 'G2 violation: % published commercial fact(s) lack evidence', missing;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- USE-CASE FITS
-- ---------------------------------------------------------------------------
INSERT INTO use_case_fit (robot_id, use_case_id, fit_score, is_primary, commercial_readiness, notes, limitations) VALUES
 ((SELECT id FROM robot WHERE slug='digit'),(SELECT id FROM use_case WHERE slug='warehouse-logistics'),0.92,true,'RAAS_DEPLOYMENT','Purpose-built for tote handling; production deployments.','Engagement is RaaS-only; no unit purchase.'),
 ((SELECT id FROM robot WHERE slug='apollo'),(SELECT id FROM use_case WHERE slug='warehouse-logistics'),0.75,false,'PILOT','Swappable batteries suit long shifts.','Pilot maturity.'),
 ((SELECT id FROM robot WHERE slug='apollo'),(SELECT id FROM use_case WHERE slug='manufacturing'),0.80,true,'PILOT','Active automotive pilots.',NULL),
 ((SELECT id FROM robot WHERE slug='figure-02'),(SELECT id FROM use_case WHERE slug='manufacturing'),0.78,true,'PILOT','Automotive line pilots.','Pilot maturity; quote-only.'),
 ((SELECT id FROM robot WHERE slug='walker-s1'),(SELECT id FROM use_case WHERE slug='manufacturing'),0.70,true,'PILOT','EV-factory pilots in CN.','Availability outside CN unclear.'),
 ((SELECT id FROM robot WHERE slug='optimus'),(SELECT id FROM use_case WHERE slug='manufacturing'),0.50,true,'PROTOTYPE','Internal factory focus.','Not externally obtainable.'),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM use_case WHERE slug='research-education'),0.90,true,'COMMERCIAL','De-facto standard affordable research platform.','Small payload.'),
 ((SELECT id FROM robot WHERE slug='unitree-h1'),(SELECT id FROM use_case WHERE slug='research-education'),0.85,true,'COMMERCIAL','High-performance locomotion research.',NULL),
 ((SELECT id FROM robot WHERE slug='booster-t1'),(SELECT id FROM use_case WHERE slug='research-education'),0.80,true,'COMMERCIAL','Competition-proven developer platform.',NULL),
 ((SELECT id FROM robot WHERE slug='talos'),(SELECT id FROM use_case WHERE slug='research-education'),0.85,true,'COMMERCIAL','Torque-controlled full-size research.','High cost; built to order.'),
 ((SELECT id FROM robot WHERE slug='reem-c'),(SELECT id FROM use_case WHERE slug='research-education'),0.70,true,'COMMERCIAL',NULL,NULL),
 ((SELECT id FROM robot WHERE slug='gr-2'),(SELECT id FROM use_case WHERE slug='research-education'),0.75,true,'COMMERCIAL',NULL,'Distribution outside CN via partners.'),
 ((SELECT id FROM robot WHERE slug='ameca'),(SELECT id FROM use_case WHERE slug='events-entertainment'),0.95,true,'COMMERCIAL','Leading expressive event humanoid; rentable today.','Stationary; no mobile manipulation.'),
 ((SELECT id FROM robot WHERE slug='ameca'),(SELECT id FROM use_case WHERE slug='hospitality'),0.65,false,'COMMERCIAL','Greeting/information roles.','Stationary.'),
 ((SELECT id FROM robot WHERE slug='neo'),(SELECT id FROM use_case WHERE slug='home'),0.70,true,'EARLY_ACCESS','First credible home humanoid offer.','Early access; expectations management.'),
 ((SELECT id FROM robot WHERE slug='eve'),(SELECT id FROM use_case WHERE slug='inspection'),0.55,false,'LIMITED_COMMERCIAL','Patrol/monitoring tasks.','Wheeled; flat floors only.'),
 ((SELECT id FROM robot WHERE slug='phoenix'),(SELECT id FROM use_case WHERE slug='research-education'),0.60,false,'PROTOTYPE','Dexterity research interest.','Not generally obtainable.');

-- ---------------------------------------------------------------------------
-- CAPABILITIES per robot (sample)
-- ---------------------------------------------------------------------------
INSERT INTO robot_capability (robot_id, capability_id, supported, detail) VALUES
 ((SELECT id FROM robot WHERE slug='digit'),(SELECT id FROM capability WHERE slug='autonomous-navigation'),true,'Warehouse-mapped navigation.'),
 ((SELECT id FROM robot WHERE slug='digit'),(SELECT id FROM capability WHERE slug='bimanual-manipulation'),true,'Tote-optimized end effectors.'),
 ((SELECT id FROM robot WHERE slug='digit'),(SELECT id FROM capability WHERE slug='dexterous-hands'),false,'Tote grippers, not fingers.'),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM capability WHERE slug='dynamic-walking'),true,NULL),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM capability WHERE slug='dexterous-hands'),true,'Optional three-finger hands (EDU).'),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM capability WHERE slug='teleoperation'),true,NULL),
 ((SELECT id FROM robot WHERE slug='figure-02'),(SELECT id FROM capability WHERE slug='voice-interaction'),true,'LLM-based speech.'),
 ((SELECT id FROM robot WHERE slug='figure-02'),(SELECT id FROM capability WHERE slug='bimanual-manipulation'),true,NULL),
 ((SELECT id FROM robot WHERE slug='ameca'),(SELECT id FROM capability WHERE slug='expressive-face'),true,'Industry-leading facial expression.'),
 ((SELECT id FROM robot WHERE slug='ameca'),(SELECT id FROM capability WHERE slug='voice-interaction'),true,NULL),
 ((SELECT id FROM robot WHERE slug='phoenix'),(SELECT id FROM capability WHERE slug='dexterous-hands'),true,'20-DOF hands.'),
 ((SELECT id FROM robot WHERE slug='phoenix'),(SELECT id FROM capability WHERE slug='teleoperation'),true,'Teleop-first training approach.'),
 ((SELECT id FROM robot WHERE slug='talos'),(SELECT id FROM capability WHERE slug='force-control'),true,'Full torque control.'),
 ((SELECT id FROM robot WHERE slug='apollo'),(SELECT id FROM capability WHERE slug='bimanual-manipulation'),true,NULL),
 ((SELECT id FROM robot WHERE slug='eve'),(SELECT id FROM capability WHERE slug='autonomous-navigation'),true,'Flat indoor environments.');

-- ---------------------------------------------------------------------------
-- LONG-TAIL SPECIFICATIONS (sample)
-- ---------------------------------------------------------------------------
INSERT INTO specification (robot_id, definition_id, value_number, value_bool, value_text) VALUES
 ((SELECT id FROM robot WHERE slug='apollo'),(SELECT id FROM spec_definition WHERE key='swappable_battery'),NULL,true,NULL),
 ((SELECT id FROM robot WHERE slug='unitree-g1'),(SELECT id FROM spec_definition WHERE key='charge_time_min'),90,NULL,NULL),
 ((SELECT id FROM robot WHERE slug='digit'),(SELECT id FROM spec_definition WHERE key='reach_cm'),90,NULL,NULL);

COMMIT;

-- ---------------------------------------------------------------------------
-- POST-LOAD SANITY (informational)
-- ---------------------------------------------------------------------------
-- SELECT slug, maturity, is_obtainable, deployment_count, available_modes
--   FROM robot_commercial_snapshot ORDER BY slug;
