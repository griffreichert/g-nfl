-- #131: when a week's picks were submitted.
--
-- Nullable and starts null. Rows written before this ships have no timestamp,
-- and the app renders those as "time unknown". No backfill: nothing anywhere
-- records when a 2025 slate was entered.
--
-- Run this in the Supabase SQL editor BEFORE deploying the API that writes it.
-- PicksDatabase.save_picks includes the column on every insert, so the write
-- path fails against a table that does not have it yet.

alter table picks add column if not exists submitted_at timestamptz;

-- An earlier version of this file also added submitted_by. The room calls its
-- picks together, so who typed them in is not a thing we record.
alter table picks drop column if exists submitted_by;
