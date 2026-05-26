import service, { requestWithRetry } from './index'

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
