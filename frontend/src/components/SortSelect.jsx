export const EXERCISE_SORT_OPTIONS = [
  { value: '', label: '默认顺序' },
  { value: 'year:desc', label: '年份 新→旧' },
  { value: 'year:asc', label: '年份 旧→新' },
  { value: 'question_type:asc', label: '题型' },
  { value: 'exam_source:asc', label: '试卷来源' },
  { value: 'created_at:desc', label: '最近入库' },
]

export default function SortSelect({ value, options, onChange }) {
  return (
    <label className="inline-flex items-center gap-2 text-sm text-gray-600">
      排序
      <select
        className="border rounded px-3 py-1.5 bg-white text-gray-800"
        value={value}
        onChange={event => onChange(event.target.value)}
      >
        {options.map(option => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  )
}
