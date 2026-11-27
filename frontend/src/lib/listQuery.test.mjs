import assert from 'node:assert/strict'
import test from 'node:test'
import { compareSortValues, compareValues, decodeListQuery, encodeListQuery, matchFilter, nextSort } from './listQuery.js'

const columns = {
  name: { type: 'text' }, role: { type: 'enum' }, date: { type: 'date' },
  score: { type: 'number' }, actions: { type: 'text', sortable: false, filterable: false },
}

test('round trips escaped queries and drops invalid columns and values', () => {
  const filters = {
    name: '陈,张.. % +', role: ['甲,乙', '第..组', '%2C'],
    date: { start: '2024-02-29', end: null }, score: { start: null, end: 0 },
  }
  const state = { sort: { key: 'score', dir: 'desc' }, filters }
  const encoded = encodeListQuery(state)
  assert.match(encoded.toString(), /%252C/)
  assert.equal(encoded.get('f.date'), '2024-02-29..')
  assert.deepEqual(decodeListQuery(encoded.toString(), columns), { ...state, dropped: [] })
  const params = new URLSearchParams({
    sort: 'actions:asc', 'f.unknown': 'x', 'f.__proto__': 'x', 'f.actions': 'x',
    'f.role': '%ZZ', 'f.date': '2025-02-29..', 'f.score': 'Infinity..', 'f.name': '陈', page: '2',
  })
  const result = decodeListQuery(params, columns)
  assert.equal(result.sort, null)
  assert.deepEqual(result.filters, { name: '陈' })
  assert.deepEqual(result.dropped.map(({ param }) => param), [...params.keys()].slice(0, 7))
  assert.equal(decodeListQuery('sort=name:sideways', columns).dropped.length, 1)
})

test('cycles each column through its first direction, reverse and default', () => {
  for (const [first, second] of [['asc', 'desc'], ['desc', 'asc']]) {
    const start = nextSort({ key: 'role', dir: 'asc' }, 'name', first)
    assert.deepEqual(start, { key: 'name', dir: first })
    const reverse = nextSort(start, 'name', first)
    assert.deepEqual(reverse, { key: 'name', dir: second })
    assert.equal(nextSort(reverse, 'name', first), null)
  }
})

test('sorts Chinese by pinyin, and compares numbers and timestamps', () => {
  assert.ok(compareValues('陈', '张', 'text') < 0)
  assert.ok(compareValues('2班', '10班', 'text') < 0)
  assert.ok(compareValues('2', '10', 'number') < 0)
  assert.ok(compareValues('2026-11-27T08:00:00', '2026-11-27T20:00:00', 'date') < 0)
})

test('sorts grades in option order with blanks last in both directions', () => {
  const grades = ['高一', '高二', '高三']
  const column = { type: 'enum', options: grades.map(value => ({ value })) }
  const input = ['高三', null, '高一', '', '高二']
  for (const [direction, expected] of [[1, grades], [-1, [...grades].reverse()]]) {
    const sorted = [...input].sort((a, b) => direction * compareSortValues(a, b, column, direction === -1))
    assert.deepEqual(sorted, [...expected, null, ''])
  }
})

test('matches substrings, enum selection and inclusive open ranges', () => {
  assert.equal(matchFilter('AB..,甲', 'b..,', 'text'), true)
  assert.equal(matchFilter('编辑', ['管理员', '编辑'], 'enum'), true)
  assert.equal(matchFilter(2, { start: 2, end: null }, 'number'), true)
  assert.equal(matchFilter(1, { start: 2, end: null }, 'number'), false)
  assert.equal(matchFilter(0, { start: null, end: 0 }, 'number'), true)
  assert.equal(matchFilter(null, { start: null, end: 0 }, 'number'), false)
  assert.equal(matchFilter('2026-11-27T23:59:59', { start: null, end: '2026-11-27' }, 'date'), true)
  assert.equal(matchFilter('2026-11-27', { start: '2026-11-28', end: null }, 'date'), false)
})
