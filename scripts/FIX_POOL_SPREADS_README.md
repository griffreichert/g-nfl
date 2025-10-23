# Fix Pool Spreads Game ID Format

## Problem

Pool spreads were being saved with inconsistent game_id formats:
- **Wrong format**: `2025_1_ARI_NO` (single-digit week)
- **Correct format**: `2025_01_ARI_NO` (zero-padded week)

This caused mismatches when trying to join pool spreads with picks, as picks use the zero-padded format from `nfl_data_py`.

Example mismatch:
```python
# Pool spreads game_id
'2025_1_ARI_NO'

# Picks game_id
'2025_01_ARI_NO'

# These don't match, so pool spreads don't show up!
```

## Solution

This migration fixes the issue in three parts:

### 1. Fix Existing Data (SQL Migration)

Run the SQL migration to update all existing pool_spreads rows:

```bash
# File: scripts/fix_pool_spreads_game_ids.sql
```

**Steps:**
1. Go to your Supabase SQL Editor
2. Copy the contents of `fix_pool_spreads_game_ids.sql`
3. Run the migration
4. Verify the update worked

**What it does:**
- Adds temporary column `game_id_new`
- Updates all game_ids to use zero-padded week format (`2025_1_X_Y` → `2025_01_X_Y`)
- Replaces old column with new one
- Recreates constraints and indexes

### 2. Fix App Code (Already Done)

Updated code to always create game_ids with zero-padded weeks:

**File: `app/pages/manage_spreads.py`**
```python
# OLD (wrong)
games_df.index = [
    f"{season}_{week}_{row['away_team']}_{row['home_team']}"
    for _, row in games_df.iterrows()
]

# NEW (correct)
games_df.index = [
    f"{season}_{week:02d}_{row['away_team']}_{row['home_team']}"
    for _, row in games_df.iterrows()
]
```

**File: `src/g_nfl/utils/database.py`**
- Added normalization to `save_pool_spreads()` method
- All game_ids are now normalized before saving using `normalize_game_id()`

### 3. Utility Functions

**Creating game_ids** - Use the `create_game_id()` function to generate new game_ids:

```python
from g_nfl.utils.web_app import create_game_id

# Always use this function to create game_ids
game_id = create_game_id(season=2025, week=1, away_team='KC', home_team='LAC')
# Returns: '2025_01_KC_LAC'
```

**Normalizing existing game_ids** - Use `normalize_game_id()` to fix existing game_ids:

```python
from g_nfl.utils.web_app import normalize_game_id

# Use this to normalize game_ids from external sources
normalized = normalize_game_id('2025_1_KC_LAC')
# Returns: '2025_01_KC_LAC'
```

## Verification

After running the migration, verify the fix:

```sql
-- Check that all game_ids now use zero-padded format
SELECT game_id, season, week
FROM pool_spreads
WHERE week < 10
LIMIT 10;

-- Should see: 2025_01_X_Y, 2025_02_X_Y, etc.
-- NOT: 2025_1_X_Y, 2025_2_X_Y
```

## Future Prevention

Going forward, all new pool spreads will automatically use the correct format because:

1. ✅ **Utility Function**: `create_game_id()` in `web_app.py` provides a single source of truth for creating game_ids
2. ✅ **App Code**: `manage_spreads.py` uses `create_game_id()` utility instead of manual formatting
3. ✅ **Database Layer**: `database.py` normalizes all game_ids before saving
4. ✅ **Normalization**: `normalize_game_id()` function catches any edge cases from external sources

**Best Practice**: Always use `create_game_id()` when generating new game_ids, and `normalize_game_id()` when receiving game_ids from external sources.

## Files Changed

- ✅ `scripts/fix_pool_spreads_game_ids.sql` - Database migration
- ✅ `src/g_nfl/utils/web_app.py` - Added `create_game_id()` utility function
- ✅ `app/pages/manage_spreads.py` - Uses `create_game_id()` utility
- ✅ `src/g_nfl/utils/database.py` - Added normalization to save function
- ✅ `scripts/FIX_POOL_SPREADS_README.md` - This documentation

## Migration Checklist

- [ ] Run SQL migration in Supabase SQL Editor
- [ ] Verify all game_ids are now zero-padded
- [ ] Test pool spreads display in app
- [ ] Test saving new pool spreads
- [ ] Confirm picks can join with pool spreads

## Questions?

The game_id format should now be consistent across the entire application:
- ✅ Picks: `2025_01_KC_LAC`
- ✅ Pool spreads: `2025_01_KC_LAC`
- ✅ Market lines: `2025_01_KC_LAC`

All using zero-padded weeks (01-18) for consistency with `nfl_data_py`.
