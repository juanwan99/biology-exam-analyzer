import assert from 'node:assert/strict'
import test from 'node:test'
import { compareValues, decodeListQuery, encodeListQuery, matchFilter, nextSort } from './listQuery.js'

const columns = {
  name: { type: 'text' }, role: { type: 'enum' }, date: { type: 'date' },
  score: { type: 'number' }, actions: { type: 'text', sortable: false, filterable: false },
}

test('round trips literal delimiters, enum escapes and open bounds', () => {
  const state = {
    sort: { key: 'score', dir: 'desc' },
    filters: {
      name: '陈,张.. % +', role: ['甲,乙', '第..组', '%2C'],
      date: { start: '2024-02-29', end: null }, score: { start: null, end: 0 },
    },
  }
  const encoded = encodeListQuery(state)
  assert.match(encoded.toString(), /%252C/)
  assert.equal(encoded.get('f.date'), '2024-02-29..')
  assert.deepEqual(decodeListQuery(encoded.toString(), columns), { ...state, dropped: [] })
})

test('drops invalid sorts, unknown columns and invalid filters', () => {
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

test('sorts Chinese by pinyin, compares numbers and timestamps, and puts blanks last', () => {
  assert.ok(compareValues('陈', '张', 'text') < 0)
  assert.ok(compareValues('2班', '10班', 'text') < 0)
  assert.ok(compareValues('2', '10', 'number') < 0)
  assert.ok(compareValues('2026-11-27T08:00:00', '2026-11-27T20:00:00', 'date') < 0)
  for (const empty of [null, undefined, '']) {
    assert.ok(compareValues(0, empty, 'number') < 0)
    assert.ok(compareValues(empty, 0, 'number') > 0)
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
