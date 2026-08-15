import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  epaSeries,
  fmtKickoff,
  groupInjuries,
  hasContext,
  marginLabel,
  sideSpread,
} from './game.ts'
import type { GameDetail, InjuryReport, TeamWeekStat } from '../types.ts'

const injury = (team: string, name: string, status: string | null): InjuryReport => ({
  team,
  name,
  position: 'WR',
  status,
  practice: null,
})

const stat = (team: string, week: number, off: number, def: number): TeamWeekStat => ({
  week,
  team,
  plays: 60,
  off_epa_play: off,
  def_epa_play: def,
  off_success_rate: null,
  def_success_rate: null,
  off_explosive_rate: null,
  def_explosive_rate: null,
  off_pass_epa: null,
  off_rush_epa: null,
})

const game = (over: Partial<GameDetail> = {}): GameDetail => ({
  game_id: '2025_12_PIT_CHI',
  season: 2025,
  week: 12,
  away_team: 'PIT',
  home_team: 'CHI',
  gameday: null,
  gametime: null,
  roof: null,
  surface: null,
  temp: null,
  wind: null,
  stadium: null,
  div_game: null,
  away_rest: null,
  home_rest: null,
  away_qb: null,
  home_qb: null,
  away_coach: null,
  home_coach: null,
  referee: null,
  injuries: [],
  pool_spread: null,
  market_spread: null,
  market_total: null,
  away_score: null,
  home_score: null,
  result: null,
  graded_line: null,
  graded_line_source: null,
  team_weeks: [],
  picks: [],
  ...over,
})

test('injuries group away then home, worst status first', () => {
  const groups = groupInjuries(
    [
      injury('CHI', 'Moore', 'Questionable'),
      injury('PIT', 'Pickens', 'Out'),
      injury('CHI', 'Odunze', 'Out'),
      injury('PIT', 'Freiermuth', null),
    ],
    'PIT',
    'CHI',
  )
  assert.deepEqual(
    groups.map((g) => g.team),
    ['PIT', 'CHI'],
  )
  assert.deepEqual(
    groups[0].players.map((p) => p.name),
    ['Pickens', 'Freiermuth'],
  )
  assert.deepEqual(
    groups[1].players.map((p) => p.name),
    ['Odunze', 'Moore'],
  )
})

test('a team the feed did not expect is kept, not dropped', () => {
  const groups = groupInjuries([injury('GB', 'Love', 'Out')], 'PIT', 'CHI')
  assert.deepEqual(
    groups.map((g) => g.team),
    ['GB'],
  )
})

test('epaSeries puts both teams on one week axis and nulls a bye', () => {
  const series = epaSeries(
    [stat('PIT', 11, 0.1, -0.05), stat('CHI', 11, 0.2, 0.01), stat('PIT', 12, -0.3, 0.04)],
    'PIT',
    'CHI',
  )
  assert.deepEqual(series, [
    { week: 11, awayOff: 0.1, awayDef: -0.05, homeOff: 0.2, homeDef: 0.01 },
    { week: 12, awayOff: -0.3, awayDef: 0.04, homeOff: null, homeDef: null },
  ])
})

test('margin reads off the home margin, both signs', () => {
  assert.equal(marginLabel(game({ result: 3 })), 'CHI by 3')
  assert.equal(marginLabel(game({ result: -7 })), 'PIT by 7')
  assert.equal(marginLabel(game({ result: 0 })), 'Tie')
  assert.equal(marginLabel(game()), null)
})

test('spread flips for the away side', () => {
  assert.equal(sideSpread(-2.5, 'CHI', 'CHI'), -2.5)
  assert.equal(sideSpread(-2.5, 'PIT', 'CHI'), 2.5)
  assert.equal(sideSpread(null, 'PIT', 'CHI'), null)
})

test('context is absent until a field lands', () => {
  assert.equal(hasContext(game()), false)
  // score and lines are not context — they come from other tables
  assert.equal(hasContext(game({ away_score: 28, pool_spread: -2.5 })), false)
  assert.equal(hasContext(game({ wind: 0 })), true)
  assert.equal(hasContext(game({ div_game: false })), true)
})

test('kickoff date is local, not UTC midnight rolled back a day', () => {
  const s = fmtKickoff('2025-11-23', '13:00')!
  assert.match(s, /23/)
  assert.doesNotMatch(s, /22/)
  assert.match(s, /13:00/)
  assert.equal(fmtKickoff(null, '13:00'), '13:00')
  assert.equal(fmtKickoff(null, null), null)
})
