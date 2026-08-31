import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  cycleSlot,
  buildAttachment,
  buildConsensus,
  byContention,
  findBlocs,
  isHomer,
  partRating,
  scoreSide,
  toRating,
  spreadFor,
} from './consensus.ts'
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

test('scoreRow is driven by line size crossed with venue', () => {
  const empty = new Map<string, number>()
  const gid = '2025_12_CAR_GB'
  const both = [pick('Ben', gid, 'GB'), pick('Harry', gid, 'CAR')]
  const row = buildConsensus([game('CAR', 'GB', 5.5)], both)[0]

  // The measured term is served, so the test supplies it. A side that trips a
  // guardrail must rate below the side that does not, and the penalty is the
  // rule's own distance from the field's base rate.
  const penalise = (_gid: string, team: string) =>
    team === 'GB' ? [{ label: 'road side of a 7+ line', value: -11 }] : []

  assert.ok(
    scoreSide(row, 'GB', empty, penalise).rating < scoreSide(row, 'CAR', empty, penalise).rating,
  )

  // With nothing served, both sides sit on the field's own rate.
  assert.equal(scoreSide(row, 'GB', empty).rating, scoreSide(row, 'CAR', empty).rating)
})

test('agreement no longer moves the rating', () => {
  // It used to: unanimous scored below contested. Per game and shrunk, split
  // vs unanimous sat exactly on the base rate, so the term was removed rather
  // than kept small. The board still sorts contested first — that is ordering,
  // not a claim that disagreement covers.
  const empty = new Map<string, number>()
  const gid = '2025_12_CAR_GB'
  const split = buildConsensus([game('CAR', 'GB', 2.5)], [
    pick('Ben', gid, 'GB'),
    pick('Harry', gid, 'CAR'),
  ])[0]
  const unanimous = buildConsensus([game('CAR', 'GB', 2.5)], [
    pick('Ben', gid, 'GB'),
    pick('Harry', gid, 'GB'),
  ])[0]
  assert.equal(
    scoreSide(unanimous, 'GB', empty).rating,
    scoreSide(split, 'GB', empty).rating,
  )
})

test('scoreRow docks homer and attached votes, but never past the floor', () => {
  const gid = '2025_12_WAS_CHI'
  const row = buildConsensus([game('WAS', 'CHI', 2.5)], [
    pick('Chuck', gid, 'CHI'),
    pick('Harry', gid, 'WAS'),
  ])[0]
  // Chuck is a CHI homer, so the CHI side is docked and the WAS side is not.
  const clean = scoreSide(row, 'CHI', new Map()).rating
  assert.ok(scoreSide(row, 'CHI', new Map()).parts.some((p) => !p.measured))
  assert.ok(scoreSide(row, 'WAS', new Map()).parts.every((p) => p.measured))
  assert.ok(isHomer('Chuck', 'CHI') && !isHomer('Chuck', 'WAS'))

  // Attachment: five prior CHI picks is a habit, and it costs more than homer alone.
  const attached = buildAttachment(
    Array.from({ length: 5 }, (_, i) => ({ ...pick('Chuck', `g${i}`, 'CHI'), week: i + 1 })),
  )
  assert.ok(scoreSide(row, 'CHI', attached).rating < clean)

  // Judgement can never outweigh the spread band: -6 points is 3 rating points.
  assert.ok(clean - scoreSide(row, 'CHI', attached).rating <= 3)
})

test('buildAttachment counts a picker per team and ignores TEAM', () => {
  const counts = buildAttachment([
    pick('Harry', 'g1', 'CLE'),
    pick('Harry', 'g2', 'CLE'),
    pick('Harry', 'g3', 'PIT'),
    pick('TEAM', 'g4', 'CLE'),
    pick('Harry', 'g5', 'CLE', 'survivor'),
  ])
  assert.equal(counts.get('Harry|CLE'), 2)
  assert.equal(counts.get('Harry|PIT'), 1)
  assert.equal(counts.get('TEAM|CLE'), undefined)
})

test('toRating anchors 5 at break-even and clamps to 0-10', () => {
  assert.equal(toRating(0), 5)
  assert.equal(toRating(-4), 4)
  // A close line, contested, on the road is the best a side can look, and lands
  // at the top of the scale.
  assert.equal(toRating(57.1 - 52.4 + 3.9 + 1.6), 10)
  assert.equal(toRating(99), 10)
  assert.equal(toRating(-99), 0)

  // The reason for the two slopes: a 7+ line is -10.2 before anything else is
  // counted. On a single slope every big-line game pinned at 0.0 and the board
  // lost the ordering among the games we are actually forced to choose between.
  const bigLine = 42.2 - 52.4
  assert.ok(toRating(bigLine) > 2)
  assert.ok(toRating(bigLine - 3.3) < toRating(bigLine))
})

test('a side breakdown sums to the rating it shows', () => {
  const row = buildConsensus([game('CAR', 'GB', 2.5)], [
    pick('Ben', '2025_12_CAR_GB', 'GB'),
    pick('Harry', '2025_12_CAR_GB', 'CAR'),
  ])[0]
  const score = scoreSide(row, 'GB', new Map())
  const summed = 5 + score.parts.reduce((s, p) => s + partRating(p.value, score.slope), 0)
  assert.equal(Math.round(summed * 100) / 100, Math.round(score.rating * 100) / 100)
})

test('cycleSlot walks a side through the slots', () => {
  const g = 'g1'
  assert.deepEqual(cycleSlot({}, g, 'GB', false), { g1: { team: 'GB', type: 'regular' } })
  const asRegular = { g1: { team: 'GB', type: 'regular' as const } }
  assert.deepEqual(cycleSlot(asRegular, g, 'GB', false), { g1: { team: 'GB', type: 'best_bet' } })
  const asBest = { g1: { team: 'GB', type: 'best_bet' as const } }
  assert.deepEqual(cycleSlot(asBest, g, 'GB', false), { g1: null })
})

test('switching sides keeps the slot the game already held', () => {
  // The help page promises this. Without it, tapping across a best bet
  // silently demoted it to a regular and the 2pt slot went quiet.
  const slate = { g1: { team: 'GB', type: 'best_bet' as const } }
  assert.deepEqual(cycleSlot(slate, 'g1', 'CAR', false), {
    g1: { team: 'CAR', type: 'best_bet' },
  })
})

test('promoting a second best bet demotes the incumbent', () => {
  const slate = {
    g1: { team: 'GB', type: 'best_bet' as const },
    g2: { team: 'PHI', type: 'regular' as const },
  }
  const patch = cycleSlot(slate, 'g2', 'PHI', false)
  assert.deepEqual(patch, {
    g2: { team: 'PHI', type: 'best_bet' },
    g1: { team: 'GB', type: 'regular' },
  })
  // the swap is net-zero on the regular count, so the entry cannot overflow
  const after = { ...slate, ...patch }
  assert.equal(Object.values(after).filter((v) => v.type === 'best_bet').length, 1)
  assert.equal(Object.values(after).filter((v) => v.type === 'regular').length, 1)
})

test('the Monday game only ever holds MNF', () => {
  assert.deepEqual(cycleSlot({}, 'g1', 'LA', true), { g1: { team: 'LA', type: 'mnf' } })
  const held = { g1: { team: 'LA', type: 'mnf' as const } }
  assert.deepEqual(cycleSlot(held, 'g1', 'LA', true), { g1: null })
  assert.deepEqual(cycleSlot(held, 'g1', 'ATL', true), { g1: { team: 'ATL', type: 'mnf' } })
})

test('a full entry refuses a new game but still allows swaps', () => {
  const slate: Record<string, { team: string; type: 'regular' | 'best_bet' }> = {
    bb: { team: 'A', type: 'best_bet' },
  }
  for (let i = 0; i < 5; i++) slate[`r${i}`] = { team: 'T' + i, type: 'regular' }
  assert.deepEqual(cycleSlot(slate, 'new', 'X', false), {})
  assert.deepEqual(cycleSlot(slate, 'r0', 'OTHER', false), {
    r0: { team: 'OTHER', type: 'regular' },
  })
})
