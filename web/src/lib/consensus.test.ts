import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bandFor, buildConsensus, byContention, findBlocs, spreadFor } from './consensus.ts'
import type { GameLine, PickRecord, PickType } from '../types.ts'

const game = (away: string, home: string, pool: number | null = -3): GameLine => ({
  game_id: `2025_12_${away}_${home}`,
  away_team: away,
  home_team: home,
  pool_spread: pool,
  market_spread: pool,
  market_total: 44.5,
  is_mnf: false,
})

const pick = (picker: string, gid: string, team: string, type: PickType = 'regular'): PickRecord => ({
  picker,
  game_id: gid,
  team_picked: team,
  pick_type: type,
  spread: null,
  season: 2025,
  week: 12,
})

test('spreadFor reads pool_spread as home-perspective', () => {
  // CAR at GB with GB favoured by 13.5 is stored +13.5 (verified against
  // nflverse spread_line, corr +0.99). Getting this backwards inverts every
  // number on the board.
  const g = game('CAR', 'GB', 13.5)
  assert.equal(spreadFor(g, 'GB'), 13.5)
  assert.equal(spreadFor(g, 'CAR'), -13.5)
  assert.equal(spreadFor(game('CAR', 'GB', null), 'GB'), null)
})

test('bandFor buckets on absolute spread, either sign', () => {
  assert.equal(bandFor(2.5)?.label, '0-3')
  assert.equal(bandFor(-2.5)?.label, '0-3')
  assert.equal(bandFor(3)?.label, '3-7')
  assert.equal(bandFor(-6.5)?.label, '3-7')
  assert.equal(bandFor(7)?.label, '7+')
  assert.equal(bandFor(14)?.label, '7+')
  assert.equal(bandFor(null), null)
})

test('findBlocs collapses pickers who always agree', () => {
  const picks = [
    ...Array.from({ length: 12 }, (_, i) => pick('Ben', `g${i}`, 'AAA')),
    ...Array.from({ length: 12 }, (_, i) => pick('bModel', `g${i}`, 'AAA')),
    ...Array.from({ length: 12 }, (_, i) => pick('Harry', `g${i}`, i < 6 ? 'AAA' : 'BBB')),
  ]
  const blocs = findBlocs(picks)
  assert.deepEqual(blocs, [['Ben', 'bModel']])
})

test('findBlocs ignores pairs with too few shared games', () => {
  const picks = [
    ...Array.from({ length: 5 }, (_, i) => pick('Ben', `g${i}`, 'AAA')),
    ...Array.from({ length: 5 }, (_, i) => pick('bModel', `g${i}`, 'AAA')),
  ]
  assert.deepEqual(findBlocs(picks), [])
})

test('findBlocs never counts TEAM, which is an output not a vote', () => {
  const picks = [
    ...Array.from({ length: 12 }, (_, i) => pick('TEAM', `g${i}`, 'AAA')),
    ...Array.from({ length: 12 }, (_, i) => pick('Ben', `g${i}`, 'AAA')),
  ]
  assert.deepEqual(findBlocs(picks), [])
})

test('a bloc counts once, so it cannot manufacture a majority', () => {
  const g = game('NYJ', 'BUF')
  const picks = [
    pick('Ben', g.game_id, 'BUF'),
    pick('bModel', g.game_id, 'BUF'),
    pick('Harry', g.game_id, 'NYJ'),
  ]
  const plain = buildConsensus([g], picks)[0]
  assert.equal(plain.blocSide, 2)
  assert.equal(plain.blocOther, 1)

  const withBlocs = buildConsensus([g], picks, [['Ben', 'bModel']])[0]
  assert.equal(withBlocs.blocSide, 1, 'Ben and bModel are one opinion')
  assert.equal(withBlocs.blocOther, 1)
  assert.equal(withBlocs.contention, 1, 'that makes it a dead split, not a 2-1')
})

test('best bets weigh double in net, and TEAM is excluded from it', () => {
  const g = game('NYJ', 'BUF')
  const rows = buildConsensus(
    [g],
    [
      pick('Ben', g.game_id, 'BUF', 'best_bet'),
      pick('Harry', g.game_id, 'NYJ'),
      pick('TEAM', g.game_id, 'NYJ'),
    ],
  )
  assert.equal(rows[0].side, 'BUF')
  assert.equal(rows[0].net, 1, 'BB 2 minus regular 1')
  assert.equal(rows[0].bb, 1)
  assert.equal(rows[0].teamPick, 'NYJ')
  assert.equal(rows[0].teamAgrees, false)
})

test('survivor and underdog never enter the spread consensus', () => {
  const g = game('NYJ', 'BUF')
  const rows = buildConsensus(
    [g],
    [pick('Ben', g.game_id, 'BUF', 'survivor'), pick('Harry', g.game_id, 'BUF', 'underdog')],
  )
  assert.deepEqual(rows, [], 'no ATS picks means no row at all')
})

test('a game only TEAM picked still shows up', () => {
  const g = game('NYJ', 'BUF')
  const rows = buildConsensus([g], [pick('TEAM', g.game_id, 'BUF')])
  assert.equal(rows.length, 1)
  assert.equal(rows[0].teamPick, 'BUF')
  assert.equal(rows[0].teamAgrees, false, 'no field to agree with')
  assert.equal(rows[0].net, 0)
})

test('byContention puts dead splits first and unanimity last', () => {
  const split = game('NYJ', 'BUF')
  const unanimous = game('PIT', 'CHI')
  const rows = buildConsensus(
    [split, unanimous],
    [
      pick('Ben', split.game_id, 'BUF'),
      pick('Harry', split.game_id, 'NYJ'),
      pick('Ben', unanimous.game_id, 'CHI'),
      pick('Harry', unanimous.game_id, 'CHI'),
    ],
  ).sort(byContention)
  assert.equal(rows[0].game.game_id, split.game_id)
  assert.equal(rows[1].game.game_id, unanimous.game_id)
})

test('no picks at all yields no rows, not a crash', () => {
  assert.deepEqual(buildConsensus([game('NYJ', 'BUF')], []), [])
  assert.deepEqual(findBlocs([]), [])
})
