import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  cutHasSignal,
  fmtPct,
  fmtUnits,
  isFlat,
  isHabit,
  isInflated,
  sortTeams,
} from './analytics.ts'
import type { CutRow, TeamAppetite } from '../types.ts'

const BASE = 0.4735555555555557

const row = (key: string, shrunk: number | null, pct = 0.5): CutRow => ({
  key,
  picks: 100,
  games: 40,
  pick_pct: 0.6,
  pct,
  shrunk_pct: shrunk,
  units: -3,
  z: -1,
})

const team = (t: string, appetite: number | null, pct: number | null, units = 0): TeamAppetite => ({
  team: t,
  available: 17,
  picked_games: 10,
  picks: 20,
  appetite,
  votes_per_pick: 2,
  pct,
  units,
})

test('isFlat catches the base rate through a JSON round-trip', () => {
  // shrink() hands back `base` byte-identical when a cut has no signal, but the
  // number arrives over the wire, so exact equality is not safe to rely on.
  const roundTripped = JSON.parse(JSON.stringify({ b: BASE })).b as number
  assert.equal(isFlat(row('venue', roundTripped), BASE), true)
  assert.equal(isFlat(row('0-3', 0.5198198734355699), BASE), false)
  assert.equal(isFlat(row('empty', null), BASE), false)
})

test('cutHasSignal is false only when every cell collapsed', () => {
  assert.equal(cutHasSignal([row('home', BASE), row('road', BASE)], BASE), false)
  assert.equal(cutHasSignal([row('home', BASE), row('road', 0.52)], BASE), true)
  assert.equal(cutHasSignal([], BASE), false)
})

test('isHabit needs both appetite and daylight under the base rate', () => {
  assert.equal(isHabit(team('DET', 0.81, 0.385), BASE), true)
  // picked often, but above the field's own rate: not a habit worth flagging
  assert.equal(isHabit(team('CHI', 0.88, 0.571), BASE), false)
  // bad rate on a team we barely touch is noise, not a habit
  assert.equal(isHabit(team('WAS', 0.2, 0.25), BASE), false)
  // half the room sits just under the base rate by construction — a hair
  // below it is not a habit
  assert.equal(isHabit(team('DAL', 0.81, 0.462), BASE), false)
  assert.equal(isHabit(team('BYE', null, null), BASE), false)
})

test('isInflated only fires where votes were doubled up', () => {
  // one pick per game (the picker cut): nothing to inflate
  assert.equal(isInflated({ ...row('Ben', BASE), pick_pct: 0.5172, pct: 0.5172 }), false)
  assert.equal(isInflated({ ...row('3-7 home', 0.41), pick_pct: 0.303, pct: 0.366 }), true)
  assert.equal(isInflated({ ...row('empty', null), pick_pct: null, pct: null }), false)
})

test('sortTeams keeps nulls last in both directions', () => {
  const teams = [team('AAA', 0.3, 0.6), team('ZZZ', null, null), team('MMM', 0.9, 0.4)]
  assert.deepEqual(
    sortTeams(teams, 'appetite', true).map((t) => t.team),
    ['MMM', 'AAA', 'ZZZ'],
  )
  assert.deepEqual(
    sortTeams(teams, 'appetite', false).map((t) => t.team),
    ['AAA', 'MMM', 'ZZZ'],
  )
})

test('sortTeams breaks ties on team code and does not mutate', () => {
  const teams = [team('ZZZ', 0.5, 0.5), team('AAA', 0.5, 0.5)]
  assert.deepEqual(
    sortTeams(teams, 'appetite', true).map((t) => t.team),
    ['AAA', 'ZZZ'],
  )
  assert.deepEqual(
    sortTeams(teams, 'team', true).map((t) => t.team),
    ['ZZZ', 'AAA'],
  )
  assert.equal(teams[0].team, 'ZZZ')
})

test('formatters', () => {
  assert.equal(fmtPct(0.4735555555555557), '47.4%')
  assert.equal(fmtPct(null), '—')
  assert.equal(fmtUnits(-55.18), '-55.18')
  assert.equal(fmtUnits(28.27), '+28.27')
  assert.equal(fmtUnits(0), '0.00')
})
