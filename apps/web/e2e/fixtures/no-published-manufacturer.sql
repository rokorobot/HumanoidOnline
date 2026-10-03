-- E2E-ONLY fixture (applied by .github/workflows/ci.yml to the EPHEMERAL CI database,
-- never to any real database): a manufacturer whose single model is unpublished, so the
-- "a maker with no published models says NONE PUBLISHED, not UNKNOWN" test does not depend
-- on which real manufacturers the catalogue happens to have published today.
SET search_path TO humanoid, public;

INSERT INTO manufacturer (slug, name)
VALUES ('e2e-fixture-maker', 'E2E Fixture Maker (test only)')
ON CONFLICT (slug) DO NOTHING;

INSERT INTO robot (slug, manufacturer_id, name, is_published)
SELECT 'e2e-fixture-unpublished-model', m.id, 'E2E Fixture Unpublished Model', false
FROM manufacturer m
WHERE m.slug = 'e2e-fixture-maker'
ON CONFLICT (slug) DO NOTHING;
