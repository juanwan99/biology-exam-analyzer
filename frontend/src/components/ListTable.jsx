import { Fragment, useId, useMemo, useState } from 'react'
import { getCoreRowModel, getFilteredRowModel, getSortedRowModel, useReactTable } from '@tanstack/react-table'
import { compareSortValues, matchFilter, nextSort } from '../lib/listQuery'

const inputClass = 'rounded border border-gray-300 px-2 py-1 text-sm min-w-0'
const buttonClass = 'rounded border px-3 py-1 text-sm hover:bg-gray-100'
const enumLabel = (options, value) => options.find(option => option.value === String(value))?.label ?? value

function filterLabel(column, value) {
  if (column.type === 'text') return value
  if (column.type === 'enum') return value.map(item => enumLabel(column.options, item)).join('、')
  if (value.start == null) return `≤ ${value.end}`
  if (value.end == null) return `≥ ${value.start}`
  return `${value.start} 至 ${value.end}`
}

function FilterControl({ column, value, onChange }) {
  const { header, type, options } = column
  if (type === 'text') {
    return <input className={inputClass} type="search" aria-label={header} value={value ?? ''}
      onChange={event => onChange(event.target.value || undefined)} />
  }
  if (type === 'enum') {
    const selected = value ?? []
    return <div className="flex flex-wrap gap-x-3 gap-y-1">{options.map(option => (
      <label key={option.value} className="inline-flex items-center gap-1 text-sm">
        <input type="checkbox" checked={selected.includes(option.value)} onChange={event => {
          const next = event.target.checked ? [...selected, option.value] : selected.filter(item => item !== option.value)
          onChange(next.length ? next : undefined)
        }} />{option.label}
      </label>
    ))}</div>
  }
  return <div className="grid grid-cols-2 gap-2">{['start', 'end'].map((bound, index) => (
    <input key={bound} className={inputClass} type={type} step={type === 'number' ? 'any' : undefined}
      aria-label={header + (index ? '结束' : '开始')} placeholder={index ? '最大值' : '最小值'}
      value={value?.[bound] ?? ''} onChange={({ target }) => {
        if (target.validity.badInput) return
        const next = { start: null, end: null, ...value,
          [bound]: target.value === '' ? null : type === 'number' ? target.valueAsNumber : target.value }
        onChange(next.start == null && next.end == null ? undefined : next)
      }} />
  ))}</div>
}

/** Columns use { key, header, type, accessor, sortable?, filterable?, firstDir?, options? }.
 * Enum options use { value, label } with string values. renderRow(row) returns a tr.
 */
export default function ListTable({
  columns, rows, rowKey, mode = 'client', query, onQueryChange, hasData = rows.length > 0, emptyText = '暂无记录', renderRow,
}) {
  const server = mode === 'server'
  const [localQuery, setLocalQuery] = useState({ sort: null, filters: {} })
  const [open, setOpen] = useState(false)
  const popoverId = useId()
  const { sort, filters } = query ?? localQuery
  const descending = sort?.dir === 'desc'
  const tableColumns = useMemo(() => columns.map(column => ({
    id: column.key,
    accessorFn: column.accessor,
    sortUndefined: false,
    sortingFn: (a, b, id) => compareSortValues(a.getValue(id), b.getValue(id), column, descending),
    filterFn: (row, id, filter) => matchFilter(row.getValue(id), filter, column.type),
  })), [columns, descending])
  const sorting = useMemo(() => sort ? [{ id: sort.key, desc: descending }] : [], [sort, descending])
  const columnFilters = useMemo(() => Object.entries(filters).map(([id, value]) => ({ id, value })), [filters])
  const table = useReactTable({
    data: rows, columns: tableColumns, state: { sorting, columnFilters },
    manualSorting: server, manualFiltering: server,
    getRowId: row => String(typeof rowKey === 'function' ? rowKey(row) : row[rowKey]),
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  function changeQuery(next) {
    if (!server && query == null) setLocalQuery(next)
    onQueryChange?.(next)
  }
  function changeFilter(key, value) {
    const next = { ...filters, [key]: value }
    if (value === undefined) delete next[key]
    changeQuery({ sort, filters: next })
  }

  const clear = <button type="button" className={buttonClass} onClick={() => changeQuery({ sort, filters: {} })}>清除筛选</button>
  const filterColumns = columns.filter(column => column.filterable !== false)
  const visible = table.getRowModel().rows
  const filteredEmpty = columnFilters.length > 0 && hasData

  return <>
    {filterColumns.length > 0 && (
      <div className="relative flex flex-wrap items-center gap-2 border-b px-3 py-2"
        onKeyDown={event => event.key === 'Escape' && setOpen(false)}>
        <button type="button" className={buttonClass} aria-expanded={open} aria-controls={popoverId}
          onClick={() => setOpen(!open)}>筛选</button>
        <div id={popoverId} hidden={!open}
          className="absolute left-3 top-full z-20 max-h-[50vh] w-[26rem] max-w-[calc(100%-1.5rem)] space-y-2 overflow-auto rounded-lg border bg-white p-3 shadow-lg">
          {filterColumns.map(column => <fieldset key={column.key}>
            <legend className="mb-1 text-xs font-medium text-gray-700">{column.header}</legend>
            <FilterControl column={column} value={filters[column.key]} onChange={value => changeFilter(column.key, value)} />
          </fieldset>)}
        </div>
        {filterColumns.filter(column => Object.prototype.hasOwnProperty.call(filters, column.key)).map(column => (
          <button key={column.key} type="button" className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-700"
            aria-label={`移除${column.header}筛选`} onClick={() => changeFilter(column.key, undefined)}>
            {column.header}：{filterLabel(column, filters[column.key])} ×
          </button>
        ))}
        {columnFilters.length > 0 && clear}
      </div>
    )}
    <div className="flex-1 overflow-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="sticky top-0 bg-gray-50">
          <tr>{columns.map(({ key, header, sortable, firstDir, type }) => {
            const dir = sort?.key === key ? sort.dir : null
            return <th key={key} scope="col" aria-sort={sortable === false ? undefined :
              ({ asc: 'ascending', desc: 'descending' })[dir] ?? 'none'}
              className={`px-3 py-2 text-xs font-medium uppercase text-gray-500 ${type === 'number' ? 'text-right' : 'text-left'}`}>
              {sortable === false ? header : (
                <button type="button" className="inline-flex items-center gap-1 hover:text-gray-900"
                  onClick={() => changeQuery({ sort: nextSort(sort, key, firstDir), filters })}>
                  {header}<span aria-hidden="true">{({ asc: '↑', desc: '↓' })[dir] ?? '↕'}</span>
                </button>
              )}
            </th>
          })}</tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {visible.map(row => renderRow ? <Fragment key={row.id}>{renderRow(row.original)}</Fragment> : (
            <tr key={row.id} className="hover:bg-gray-50">{columns.map(({ key, type, options }) => {
              const value = row.getValue(key)
              return <td key={key} className={`px-3 py-2 text-xs text-gray-500 ${type === 'number' ? 'text-right' : ''}`}>
                {type === 'enum' ? enumLabel(options, value) : value}
              </td>
            })}</tr>
          ))}
          {visible.length === 0 && <tr><td colSpan={columns.length} className="p-8 text-center text-sm text-gray-500">
            <p>{filteredEmpty ? '暂无符合筛选的记录' : emptyText}</p>
            {filteredEmpty && <div className="mt-2">{clear}</div>}
          </td></tr>}
        </tbody>
      </table>
    </div>
  </>
}
