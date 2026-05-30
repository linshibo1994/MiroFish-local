import service, { requestWithRetry } from './index'
import { setGraphTypeTranslations } from '../utils/entityTranslations.js'

function normalizeBaseURL(baseURL) {
  const trimmed = (baseURL || '').replace(/\/+$/, '')
  return trimmed === '/api' ? '' : trimmed
}

function getApiUrl(path) {
  const baseURL = normalizeBaseURL(import.meta.env.VITE_API_BASE_URL)
  if (!baseURL) return path
  if (baseURL.endsWith('/api') && path.startsWith('/api/')) {
    return `${baseURL}${path.slice(4)}`
  }
  return `${baseURL}${path}`
}

async function streamNdjson(path, options, handlers = {}) {
  const response = await fetch(getApiUrl(path), options)
  if (!response.ok) {
    let detail = ''
    try {
      detail = await response.text()
    } catch (err) {
      detail = ''
    }
    throw new Error(detail || `请求失败：HTTP ${response.status}`)
  }

  if (!response.body) {
    const payload = await response.json()
    if (payload?.success === false) throw new Error(payload.error || '请求失败')
    handlers.onEvent?.({ event: 'complete', data: payload?.data, message: payload?.message || '处理完成' })
    return payload?.data
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let finalData = null

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const cleanLine = line.trim()
      if (!cleanLine) continue
      const event = JSON.parse(cleanLine)
      handlers.onEvent?.(event)
      if (event.event === 'error') throw new Error(event.message || '处理失败')
      if (event.event === 'complete') finalData = event.data
    }
  }

  if (buffer.trim()) {
    const event = JSON.parse(buffer.trim())
    handlers.onEvent?.(event)
    if (event.event === 'error') throw new Error(event.message || '处理失败')
    if (event.event === 'complete') finalData = event.data
  }

  return finalData
}

/**
 * 联网搜索现实事件
 * @param {Object} data - 包含 search_query, project_name, additional_context
 * @returns {Promise}
 */
export function searchSeedByKeyword(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/seed/web-search',
      method: 'post',
      data
    })
  )
}

/**
 * 流式联网搜索现实事件
 * @param {Object} data - 包含 search_query, project_name, additional_context
 * @param {Object} handlers - { onEvent }
 * @returns {Promise<Object>}
 */
export function streamSearchSeedByKeyword(data, handlers = {}) {
  return streamNdjson('/api/graph/seed/web-search/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  }, handlers)
}

/**
 * 上传文件并分析现实事件（multipart 阶段）
 * @param {FormData} formData - 包含 files, project_name, additional_context
 * @returns {Promise}
 */
export function analyzeUploadedSeed(formData) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * 流式上传文件并分析现实事件
 * @param {FormData} formData - 包含 files, project_name, additional_context
 * @param {Object} handlers - { onEvent }
 * @returns {Promise<Object>}
 */
export function streamAnalyzeUploadedSeed(formData, handlers = {}) {
  return streamNdjson('/api/graph/seed/upload/stream', {
    method: 'POST',
    body: formData
  }, handlers)
}

/**
 * 基于已确认的项目和模拟需求生成本体。
 * 兼容旧调用：如果传入 FormData，则退回 multipart 文件分析函数。
 * @param {Object|FormData} data - JSON 阶段包含 project_id, simulation_requirement
 * @returns {Promise}
 */
export function generateOntology(data) {
  if (typeof FormData !== 'undefined' && data instanceof FormData) {
    return analyzeUploadedSeed(data)
  }

  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data
    })
  )
}

/**
 * 构建图谱
 * @param {Object} data - 包含project_id, graph_name等
 * @returns {Promise}
 */
export function buildGraph(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * 查询任务状态
 * @param {String} taskId - 任务ID
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * 获取图谱数据
 * @param {String} graphId - 图谱ID
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  }).then(res => {
    if (res.success && res.data?.type_translations) {
      setGraphTypeTranslations(res.data.type_translations)
    }
    return res
  })
}

/**
 * 获取图谱实体/关系类型翻译表
 * @returns {Promise}
 */
export function getGraphTypeTranslations() {
  return service({
    url: '/api/graph/type-translations',
    method: 'get'
  })
}

/**
 * 获取项目信息
 * @param {String} projectId - 项目ID
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}
