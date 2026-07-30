-- 0005 — horizontal extent: arm span and reach.
--
-- The catalogue could record how TALL a robot is and how HEAVY it is, but had
-- nowhere to put how WIDE it works. Manufacturers publish that figure and we
-- were discarding it: Astribot states "Arm span: 194cm" and Robotera states
-- "Arm Span 2.1 m", and both were dropped on entry for want of a column.
--
-- Two columns, not one, because they are different measurements:
--
--   arm_span_cm  fingertip to fingertip, arms outstretched. A whole-robot
--                dimension, and the figure humanoid makers actually publish.
--   reach_cm     how far ONE arm extends from its shoulder. The figure that
--                answers "can it work across this bench", and the one arm and
--                cobot datasheets publish.
--
-- Roughly, span ~ 2 x reach. That relationship is NOT a licence to derive one
-- from the other: a derived number would be an inference presented as a
-- manufacturer's figure, which is the failure this catalogue exists to avoid.
-- Each column is filled only from a source that states that measurement.
--
-- Units are centimetres, matching height_cm, so nothing in the physical block
-- needs a conversion to compare. NUMERIC(6,1) matches height_cm exactly.
--
-- Additive and idempotent: no column is altered or dropped, and re-running is
-- safe.

ALTER TABLE robot
    ADD COLUMN IF NOT EXISTS arm_span_cm NUMERIC(6,1),
    ADD COLUMN IF NOT EXISTS reach_cm    NUMERIC(6,1);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'robot_arm_span_cm_check'
    ) THEN
        ALTER TABLE robot ADD CONSTRAINT robot_arm_span_cm_check
            CHECK (arm_span_cm > 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'robot_reach_cm_check'
    ) THEN
        ALTER TABLE robot ADD CONSTRAINT robot_reach_cm_check
            CHECK (reach_cm > 0);
    END IF;
END $$;

COMMENT ON COLUMN robot.arm_span_cm IS
    'Fingertip-to-fingertip with arms outstretched, in cm. A whole-robot '
    'horizontal dimension. Never derived from reach_cm.';
COMMENT ON COLUMN robot.reach_cm IS
    'How far one arm extends from its shoulder, in cm. Never derived from '
    'arm_span_cm.';
