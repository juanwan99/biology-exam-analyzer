const collator = new Intl.Collator('zh-Hans-CN', { numeric: true })
const types = ['text', 'enum', 'date', 'number']
const numberSyntax = /^[+-]?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i

export const isEmptyValue = (value) => value == null || value === ''

/**
 * Query state is { sort: { key, dir } | null, filters: { [key]: string | string[] | { start, end } } }.
 * URLSearchParams escapes the whole value. Text treats commas and '..' literally.
 * Enum items are individually URI-encoded before joining with commas.
 * ISO date and number bounds cannot contain '..'. A null bound leaves that end open.
 */
export function encodeListQuery({ sort, filters = {} }) {
  const params = new URLSearchParams()
  if (sort) params.set('sort', `${sort.key}:${sort.dir}`)
  for (const [key, filter] of Object.entries(filters)) {
    let value = filter
    if (Array.isArray(filter)) value = filter.map(encodeURIComponent).join(',')
    else if (filter && typeof filter === 'object') {
      const { start, end } = filter
      value = start == null && end == null ? '' : `${start ?? ''}..${end ?? ''}`
    }
    if (!isEmptyValue(value)) params.set(`f.${key}`, value)
  }
  return params
}

function parseFilter(value, type) {
  if (value === '') return undefined
  if (type === 'text') return value
  if (type === 'enum') {
    const items = value.split(',')
    if (items.includes('')) return undefined
    try {
      return items.map(decodeURIComponent)
    } catch (error) {
      if (!(error instanceof URIError)) throw error
      return undefined
    }
  }

  const parts = value.split('..')
  if (parts.length !== 2) return undefined
  if (parts.every((part) => part === '')) return null
  const bounds = parts.map((part) => {
    if (!part) return null
    if (type === 'number') return numberSyntax.test(part) && Number.isFinite(Number(part)) ? Number(part) : undefined
    if (!/^\d{4}-\d{2}-\d{2}$/.test(part) || part.startsWith('0000')) return undefined
    const date = new Date(`${part}T00:00:00Z`)
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === part ? part : undefined
  })
  return bounds.includes(undefined) ? undefined : { start: bounds[0], end: bounds[1] }
}

export function decodeListQuery(params, columns) {
  let sort = null
  const filters = new Map()
  const dropped = []
  for (const [param, value] of new URLSearchParams(params)) {
    if (param === 'sort') {
      const [, key, dir] = /^(.+):(asc|desc)$/.exec(value) ?? []
      if (!key) {
        dropped.push({ param, value, reason: 'invalid_sort' })
      } else if (!Object.hasOwn(columns, key) || !types.includes(columns[key].type) || columns[key].sortable === false) {
        dropped.push({ param, value, reason: 'unknown_column' })
      } else sort = { key, dir }
    } else if (param.startsWith('f.')) {
      const key = param.slice(2)
      if (!Object.hasOwn(columns, key) || !types.includes(columns[key].type) || columns[key].filterable === false) {
        dropped.push({ param, value, reason: 'unknown_column' })
      } else {
        const filter = parseFilter(value, columns[key].type)
        if (filter === undefined) dropped.push({ param, value, reason: 'invalid_filter' })
        else if (filter === null) filters.delete(key)
        else filters.set(key, filter)
      }
    }
  }
  return { sort, filters: Object.fromEntries(filters), dropped }
}

export function nextSort(cur, key, firstDir = 'asc') {
  if (cur?.key !== key) return { key, dir: firstDir }
  if (cur.dir !== firstDir) return null
  return { key, dir: firstDir === 'asc' ? 'desc' : 'asc' }
}

// Ascending comparator. Keep the empty-value order when reversing for descending.
export function compareValues(a, b, type) {
  if (isEmptyValue(a)) return isEmptyValue(b) ? 0 : 1
  if (isEmptyValue(b)) return -1
  if (type === 'number') return Number(a) - Number(b)
  if (type === 'date') return a < b ? -1 : a > b ? 1 : 0
  return collator.compare(String(a), String(b))
}

export function matchFilter(value, filter, type) {
  if (type === 'text') return !isEmptyValue(value) && String(value).toLowerCase().includes(filter.toLowerCase())
  if (type === 'enum') return !isEmptyValue(value) && filter.includes(String(value))
  if (filter.start == null && filter.end == null) return true
  if (isEmptyValue(value)) return false
  const candidate = type === 'date' ? value.slice(0, 10) : value
  return (filter.start == null || compareValues(candidate, filter.start, type) >= 0)
    && (filter.end == null || compareValues(candidate, filter.end, type) <= 0)
}
