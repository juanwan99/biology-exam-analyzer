import { useState, useEffect } from 'react'
import axios from 'axios'

function PromptsTab({ token, getHeaders }) {
  const [prompts, setPrompts] = useState({ split: '', analysis: '' })
  const [editingPrompt, setEditingPrompt] = useState('split')
  const [promptContent, setPromptContent] = useState('')

  const loadPrompts = async () => {
    try {
      const response = await axios.get('/api/admin/prompts', { headers: getHeaders() })
      setPrompts(response.data)
      setPromptContent(response.data.split)
    } catch (err) {
      if (import.meta.env.DEV) console.error('加载Prompt失败:', err)
    }
  }

  const savePrompt = async () => {
    try {
      await axios.put(
        '/api/admin/prompts',
        { type: editingPrompt, content: promptContent },
        { headers: getHeaders() }
      )
      alert('保存成功！')
      setPrompts({ ...prompts, [editingPrompt]: promptContent })
    } catch (err) {
      alert('保存失败')
    }
  }

  const switchPrompt = (type) => {
    setEditingPrompt(type)
    setPromptContent(prompts[type])
  }

  // 初始加载
  useEffect(() => {
    loadPrompts()
  }, [])

  return (
    <div className="bg-white shadow rounded-lg p-6">
      <div className="flex gap-4 mb-6">
        <button
          onClick={() => switchPrompt('split')}
          className={`px-4 py-2 rounded ${editingPrompt === 'split' ? 'bg-[#1a2e1f] text-white' : 'bg-gray-200 text-gray-700'}`}
        >
          拆分Prompt
        </button>
        <button
          onClick={() => switchPrompt('analysis')}
          className={`px-4 py-2 rounded ${editingPrompt === 'analysis' ? 'bg-[#1a2e1f] text-white' : 'bg-gray-200 text-gray-700'}`}
        >
          分析Prompt
        </button>
      </div>
      <textarea
        value={promptContent}
        onChange={(e) => setPromptContent(e.target.value)}
        rows={20}
        className="w-full px-4 py-2 border border-gray-300 rounded-lg font-mono text-sm"
      />
      <div className="mt-4 flex justify-between items-center">
        <span className="text-sm text-gray-600">字符数: {promptContent.length}</span>
        <button onClick={savePrompt} className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700">
          保存并生效
        </button>
      </div>
    </div>
  )
}

export default PromptsTab
