import { test } from 'node:test'
import assert from 'node:assert/strict'
import { costShare, pinCost, reservedWeek, shade, sortTeams, togglePin } from './survivor.ts'
import type { SurvivorCell, SurvivorLeg } from '../types.ts'

const cell = (team: string, week: number, win_prob: number): SurvivorCell => ({
  team,
  week,
  game_id: `2026_${String(week).padStart(2, '0')}_OPP_${team}`,
  opponent: 'OPP',
  home: true,
  spread: 3,
  win_prob,
  source: 'model',
})

const leg = (week: number, team: string): SurvivorLeg => ({
  week,
  team,
  prob: 0.7,
  pinned: false,
})

test('pinning a square reserves it', () => {
  assert.deepEqual(togglePin({}, 'BUF', 12), { 12: 'BUF' })
})

test('clicking the same square again releases it', () => {
  assert.deepEqual(togglePin({ 12: 'BUF' }, 'BUF', 12), {})
})

test('a team holds one pin, so pinning it elsewhere moves it', () => {
  assert.deepEqual(togglePin({ 12: 'BUF' }, 'BUF', 15), { 15: 'BUF' })
})

test('pinning a different team to a taken week takes the week', () => {
  assert.deepEqual(togglePin({ 12: 'BUF' }, 'KC', 12), { 12: 'KC' })
})

test('other pins are left alone', () => {
  assert.deepEqual(togglePin({ 3: 'DET', 12: 'BUF' }, 'BUF', 15), { 3: 'DET', 15: 'BUF' })
})

test('reservedWeek finds the week a team is held for', () => {
  assert.equal(reservedWeek({ 3: 'DET', 12: 'BUF' }, 'BUF'), 12)
  assert.equal(reservedWeek({ 3: 'DET' }, 'BUF'), null)
})

test('shade is transparent at the floor and near-solid at the ceiling', () => {
  assert.match(shade(0.2), /0%/)
  assert.match(shade(0.35), /0%/)
  assert.match(shade(0.95), /82%/)
  // and never green or red, which mean win and loss everywhere else
  assert.match(shade(0.6), /var\(--pick\)/)
})

test('rows follow the plan, then the best week, then the spent', () => {
  const cells = [
    cell('BUF', 12, 0.9),
    cell('KC', 1, 0.7),
    cell('NYJ', 4, 0.55),
    cell('ARI', 4, 0.4),
  ]
  const plan = [leg(1, 'KC'), leg(12, 'BUF')]
  assert.deepEqual(sortTeams(cells, plan, ['DET']), ['KC', 'BUF', 'NYJ', 'ARI', 'DET'])
})

test('pinCost is the share of survival the pins gave up', () => {
  assert.equal(pinCost(0.03, 0.06), 0.5)
  assert.equal(pinCost(null, 0.06), 0)
  assert.equal(pinCost(0.03, null), 0)
})

test('costShare turns log-survival back into a share', () => {
  assert.equal(costShare(0), 0)
  assert.equal(costShare(null), 0)
  assert.ok(Math.abs(costShare(Math.log(2)) - 0.5) < 1e-12)
})
