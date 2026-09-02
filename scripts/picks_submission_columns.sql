-- #131: who submitted a week's picks, and when.
--
-- Both nullable and both start null. Rows written before this ships have no
-- timestamp, and the app renders those as "time unknown" rather than as the
-- epoch. No backfill: nothing anywhere records when a 2025 slate was entered.
--
-- Run this in the Supabase SQL editor BEFORE deploying the API that writes
-- them. PicksDatabase.save_picks includes both columns on every insert, so the
-- write path fails against a table that does not have them yet.

alter table picks add column if not exists submitted_at timestamptz;
alter table picks add column if not exists submitted_by text;

-- submitted_by is the signed-in picker who wrote the row. It equals `picker`
-- for a personal slate and carries information only on TEAM rows, and on a
-- slate one of us typed in for somebody who sent theirs to the group chat.
comment on column picks.submitted_by is 'signed-in picker who wrote the row (#131)';
