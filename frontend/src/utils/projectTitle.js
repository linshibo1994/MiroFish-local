const OPTION_PREFIX_PATTERN = /^\s*(?:[-*]\s*)?(?:第\s*)?(?:\d+|[一二三四五六七八九十]+)\s*(?:[.．](?!\d)|[、)\）:：])\s*/

export const stripOptionPrefix = (text = '') => {
  if (!text) return ''

  return String(text)
    .replace(/^#+\s*/, '')
    .replace(OPTION_PREFIX_PATTERN, '')
    .trim()
}

export const formatSimulationRequirement = (text = '') => {
  return stripOptionPrefix(String(text || '').replace(/可模拟/g, '推演'))
}

export const getProjectDisplayTitle = (project = {}) => {
  const directTitle = project?.simulation_requirement || project?.search_query
  if (directTitle) return formatSimulationRequirement(directTitle)

  const summary = project?.seed_summary_md || project?.analysis_summary || ''
  const firstLine = String(summary)
    .split('\n')
    .map(line => stripOptionPrefix(line))
    .find(Boolean)

  return firstLine || '事件概述'
}
