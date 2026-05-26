<template>
  <div class="workbench-panel">
    <div class="scroll-container">
      <div class="step-card" :class="{ active: !seedResult && currentPhase < 1, completed: !!seedResult }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">01</span>
            <span class="step-title">现实事件输入</span>
          </div>
          <div class="step-status">
            <span v-if="seedResult" class="badge success">已分析</span>
            <span v-else-if="seedAnalyzing" class="badge processing">分析中</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="description">
            选择一种现实事件来源。联网搜索与文件上传互斥，同一次分析请求不会混合提交。
          </p>

          <div class="mode-switcher" role="tablist" aria-label="现实事件输入方式">
            <button
              type="button"
              class="mode-btn"
              :class="{ active: inputMode === 'web_search' }"
              :disabled="isBusy"
              @click="switchInputMode('web_search')"
            >
              联网搜索
            </button>
            <button
              type="button"
              class="mode-btn"
              :class="{ active: inputMode === 'file_upload' }"
              :disabled="isBusy"
              @click="switchInputMode('file_upload')"
            >
              文件上传
            </button>
          </div>

          <div v-if="inputMode === 'web_search'" class="input-block">
            <label class="field-label" for="search-query">搜索关键词</label>
            <input
              id="search-query"
              v-model="searchQuery"
              class="text-field"
              type="text"
              placeholder="例如：张雪机车事件"
              :disabled="isBusy"
            />
          </div>

          <div v-else class="input-block">
            <input
              ref="fileInput"
              type="file"
              multiple
              accept=".pdf,.md,.txt"
              class="hidden-input"
              :disabled="isBusy"
              @change="handleFileSelect"
            />
            <div
              class="upload-zone"
              :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0 }"
              @click="triggerFileInput"
              @dragover.prevent="handleDragOver"
              @dragleave.prevent="handleDragLeave"
              @drop.prevent="handleDrop"
            >
              <div v-if="files.length === 0" class="upload-placeholder">
                <div class="upload-icon">↑</div>
                <div class="upload-title">拖拽 PDF / MD / TXT 到这里</div>
                <div class="upload-hint">或点击选择文件</div>
              </div>

              <div v-else class="file-list">
                <div v-for="(file, index) in files" :key="`${file.name}-${index}`" class="file-item">
                  <span class="file-name">{{ file.name }}</span>
                  <button type="button" class="remove-btn" :disabled="isBusy" @click.stop="removeFile(index)">×</button>
                </div>
              </div>
            </div>
          </div>

          <div class="input-block compact">
            <label class="field-label" for="additional-context">补充上下文</label>
            <textarea
              id="additional-context"
              v-model="additionalContext"
              class="text-area"
              rows="3"
              placeholder="可选：关注的时间线、角色、机构或传播平台"
              :disabled="isBusy"
            ></textarea>
          </div>

          <button type="button" class="action-btn" :disabled="!canAnalyze" @click="analyzeSeed">
            <span v-if="seedAnalyzing" class="spinner-sm"></span>
            {{ seedAnalyzing ? '分析现实事件...' : '分析现实事件' }}
          </button>

          <p v-if="localError" class="error-text">{{ localError }}</p>
        </div>
      </div>

      <div v-if="seedResult" class="step-card completed">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">02</span>
            <span class="step-title">事件摘要与建议</span>
          </div>
          <div class="step-status">
            <span class="badge success">{{ suggestions.length }} 条建议</span>
          </div>
        </div>

        <div class="card-content">
          <div class="summary-panel">
            <div class="panel-title">现实事件摘要</div>
            <pre class="summary-text">{{ seedSummary }}</pre>
          </div>

          <div v-if="sources.length" class="sources-panel">
            <div class="panel-title">信息来源</div>
            <div class="source-list">
              <a
                v-for="(source, index) in sources"
                :key="source.url || `${source.title}-${index}`"
                class="source-item"
                :href="source.url"
                target="_blank"
                rel="noreferrer"
              >
                <span class="source-title">{{ source.title || source.name || source.url || '未命名来源' }}</span>
                <span class="source-meta">{{ source.publisher || source.siteName || source.published_at || source.datePublished || '来源记录' }}</span>
              </a>
            </div>
          </div>

          <div class="suggestions-panel">
            <div class="panel-title">推荐模拟提示词</div>
            <div v-if="suggestions.length" class="suggestion-list">
              <button
                v-for="suggestion in suggestions"
                :key="suggestion"
                type="button"
                class="suggestion-btn"
                :class="{ selected: selectedSuggestion === suggestion }"
                :disabled="isBusy"
                @click="applySuggestion(suggestion)"
              >
                {{ suggestion }}
              </button>
            </div>
            <p v-else class="empty-hint">暂无建议，可直接手动输入。</p>
          </div>

          <div class="input-block">
            <label class="field-label" for="simulation-requirement">最终模拟提示词</label>
            <textarea
              id="simulation-requirement"
              v-model="simulationRequirement"
              class="text-area"
              rows="5"
              placeholder="选择一条建议，或手动输入你要模拟 / 预测的问题"
              :disabled="isBusy"
            ></textarea>
          </div>
        </div>
      </div>

      <div class="step-card" :class="{ active: ontologyGenerating || (seedResult && currentPhase < 1), completed: currentPhase > 0 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">03</span>
            <span class="step-title">本体生成</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 0" class="badge success">已完成</span>
            <span v-else-if="ontologyGenerating" class="badge processing">生成中</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note" style="display:none">POST /api/graph/ontology/generate</p>
          <p class="description">
            确认模拟提示词后，基于已保存的现实事件文本生成图谱本体。
          </p>

          <button type="button" class="action-btn" :disabled="!canGenerateOntology" @click="handleGenerateOntology">
            <span v-if="ontologyGenerating" class="spinner-sm"></span>
            {{ ontologyGenerating ? '正在生成本体...' : '确认提示词并生成本体' }}
          </button>

          <p v-if="localError" class="error-text">{{ localError }}</p>

          <div v-if="currentPhase === 0 && ontologyProgress" class="progress-section">
            <div class="spinner-sm"></div>
            <span>{{ ontologyProgress.message || '正在生成本体...' }}</span>
          </div>

          <div v-if="projectData?.ontology" class="ontology-preview">
            <div class="tags-container" :class="{ dimmed: selectedOntologyItem }">
              <span class="tag-label">实体类型</span>
              <div class="tags-list">
                <span
                  v-for="entity in projectData.ontology.entity_types"
                  :key="entity.name"
                  class="entity-tag clickable"
                  @click="selectOntologyItem(entity, 'entity')"
                >
                  {{ translateEntityType(entity.name) }}
                </span>
              </div>
            </div>

            <div class="tags-container" :class="{ dimmed: selectedOntologyItem }">
              <span class="tag-label">关系类型</span>
              <div class="tags-list">
                <span
                  v-for="rel in projectData.ontology.edge_types"
                  :key="rel.name"
                  class="entity-tag clickable"
                  @click="selectOntologyItem(rel, 'relation')"
                >
                  {{ translateRelationType(rel.name) }}
                </span>
              </div>
            </div>
          </div>

          <div v-if="selectedOntologyItem" class="ontology-detail-overlay">
            <div class="detail-header">
              <div class="detail-title-group">
                <span class="detail-type-badge">{{ selectedOntologyItem.itemType === 'entity' ? '实体' : '关系' }}</span>
                <span class="detail-name">{{ selectedOntologyItem.itemType === 'entity' ? translateEntityType(selectedOntologyItem.name) : translateRelationType(selectedOntologyItem.name) }}</span>
              </div>
              <button class="close-btn" @click="selectedOntologyItem = null">×</button>
            </div>
            <div class="detail-body">
              <div class="detail-desc">{{ selectedOntologyItem.description }}</div>
              <div class="detail-section" v-if="selectedOntologyItem.attributes?.length">
                <span class="section-label">属性</span>
                <div class="attr-list">
                  <div v-for="attr in selectedOntologyItem.attributes" :key="attr.name" class="attr-item">
                    <span class="attr-name">{{ attr.name }}</span>
                    <span class="attr-type">({{ attr.type }})</span>
                    <span class="attr-desc">{{ attr.description }}</span>
                  </div>
                </div>
              </div>
              <div class="detail-section" v-if="selectedOntologyItem.examples?.length">
                <span class="section-label">示例</span>
                <div class="example-list">
                  <span v-for="ex in selectedOntologyItem.examples" :key="ex" class="example-tag">{{ ex }}</span>
                </div>
              </div>
              <div class="detail-section" v-if="selectedOntologyItem.source_targets?.length">
                <span class="section-label">连接关系</span>
                <div class="conn-list">
                  <div v-for="(conn, idx) in selectedOntologyItem.source_targets" :key="idx" class="conn-item">
                    <span class="conn-node">{{ translateEntityType(conn.source) }}</span>
                    <span class="conn-arrow">→</span>
                    <span class="conn-node">{{ translateEntityType(conn.target) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="step-card" :class="{ active: currentPhase === 1, completed: currentPhase > 1 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">04</span>
            <span class="step-title">知识图谱构建</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase > 1" class="badge success">已完成</span>
            <span v-else-if="currentPhase === 1" class="badge processing">{{ buildProgress?.progress || 0 }}%</span>
            <span v-else class="badge pending">等待</span>
          </div>
        </div>

        <div class="card-content">
          <p class="api-note" style="display:none">POST /api/graph/build</p>
          <p class="description">
            基于生成的本体构建知识图谱，形成实体、关系、时序记忆与社区摘要。
          </p>

          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.nodes }}</span>
              <span class="stat-label">实体节点</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.edges }}</span>
              <span class="stat-label">关系边</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ graphStats.types }}</span>
              <span class="stat-label">实体类型数</span>
            </div>
          </div>
        </div>
      </div>

      <div class="step-card" :class="{ active: currentPhase === 2, completed: currentPhase >= 2 }">
        <div class="card-header">
          <div class="step-info">
            <span class="step-num">05</span>
            <span class="step-title">构建完成</span>
          </div>
          <div class="step-status">
            <span v-if="currentPhase >= 2" class="badge accent">就绪</span>
          </div>
        </div>

        <div class="card-content">
          <p class="description">图谱构建已完成，请进入下一步进行模拟环境搭建。</p>
          <button type="button" class="action-btn" :disabled="currentPhase < 2" @click="emit('next-step')">
            进入环境搭建 ➝
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { analyzeUploadedSeed, generateOntology, searchSeedByKeyword } from '../api/graph'
import { translateEntityType, translateRelationType } from '../utils/entityTranslations.js'

const props = defineProps({
  currentPhase: { type: Number, default: -1 },
  projectData: Object,
  pendingUpload: Object,
  ontologyProgress: Object,
  buildProgress: Object,
  graphData: Object,
  systemLogs: { type: Array, default: () => [] }
})

const emit = defineEmits(['ontology-generated', 'next-step', 'add-log'])

const inputMode = ref('web_search')
const searchQuery = ref('')
const files = ref([])
const additionalContext = ref('')
const seedResult = ref(null)
const selectedSuggestion = ref('')
const simulationRequirement = ref('')
const seedAnalyzing = ref(false)
const ontologyGenerating = ref(false)
const localError = ref('')
const isDragOver = ref(false)
const fileInput = ref(null)
const selectedOntologyItem = ref(null)

const isBusy = computed(() => seedAnalyzing.value || ontologyGenerating.value || props.currentPhase >= 1)

const suggestions = computed(() => {
  const value = seedResult.value?.simulation_suggestions || seedResult.value?.suggestions || []
  return value.filter(Boolean).slice(0, 3)
})

const sources = computed(() => {
  const value = seedResult.value?.seed_sources || seedResult.value?.sources || []
  return Array.isArray(value) ? value : []
})

const seedSummary = computed(() => {
  return seedResult.value?.seed_summary_md || seedResult.value?.analysis_summary || '暂无摘要。'
})

const currentProjectId = computed(() => seedResult.value?.project_id || props.projectData?.project_id || '')

const canAnalyze = computed(() => {
  if (isBusy.value) return false
  if (inputMode.value === 'web_search') return searchQuery.value.trim().length > 0
  return files.value.length > 0
})

const canGenerateOntology = computed(() => {
  return !!seedResult.value && !!currentProjectId.value && simulationRequirement.value.trim().length > 0 && !isBusy.value
})

const graphStats = computed(() => {
  const nodes = props.graphData?.node_count || props.graphData?.nodes?.length || 0
  const edges = props.graphData?.edge_count || props.graphData?.edges?.length || 0
  const types = props.projectData?.ontology?.entity_types?.length || 0
  return { nodes, edges, types }
})

const resetAnalysisResult = () => {
  seedResult.value = null
  selectedSuggestion.value = ''
  localError.value = ''
}

const switchInputMode = (mode) => {
  if (inputMode.value === mode || isBusy.value) return
  inputMode.value = mode
  resetAnalysisResult()
  simulationRequirement.value = ''

  if (mode === 'web_search') {
    files.value = []
    if (fileInput.value) fileInput.value.value = ''
  } else {
    searchQuery.value = ''
  }

  emit('add-log', `Step1 input mode switched to ${mode}.`)
}

const triggerFileInput = () => {
  if (!isBusy.value) fileInput.value?.click()
}

const addFiles = (newFiles) => {
  resetAnalysisResult()
  const validFiles = newFiles.filter(file => {
    const ext = file.name.split('.').pop().toLowerCase()
    return ['pdf', 'md', 'txt'].includes(ext)
  })
  files.value.push(...validFiles)
  if (validFiles.length !== newFiles.length) {
    localError.value = '仅支持 PDF、MD、TXT 文件。'
  } else {
    localError.value = ''
  }
}

const handleFileSelect = (event) => {
  addFiles(Array.from(event.target.files || []))
}

const handleDragOver = () => {
  if (!isBusy.value) isDragOver.value = true
}

const handleDragLeave = () => {
  isDragOver.value = false
}

const handleDrop = (event) => {
  isDragOver.value = false
  if (isBusy.value) return
  addFiles(Array.from(event.dataTransfer.files || []))
}

const removeFile = (index) => {
  files.value.splice(index, 1)
  resetAnalysisResult()
}

const normalizeSeedResult = (data) => {
  const normalized = data || {}
  return {
    ...normalized,
    seed_summary_md: normalized.seed_summary_md || normalized.analysis_summary || '',
    simulation_suggestions: normalized.simulation_suggestions || normalized.suggestions || [],
    seed_sources: normalized.seed_sources || normalized.sources || []
  }
}

const analyzeSeed = async () => {
  localError.value = ''

  if (inputMode.value === 'web_search' && files.value.length > 0) {
    localError.value = '联网搜索模式不能携带文件。'
    return
  }

  if (inputMode.value === 'file_upload' && searchQuery.value.trim()) {
    localError.value = '文件上传模式不能携带搜索关键词。'
    return
  }

  seedAnalyzing.value = true
  emit('add-log', inputMode.value === 'web_search' ? 'Analyzing seed by web search...' : 'Analyzing uploaded seed files...')

  try {
    const res = inputMode.value === 'web_search'
      ? await searchSeedByKeyword({
          search_query: searchQuery.value.trim(),
          additional_context: additionalContext.value.trim()
        })
      : await analyzeUploadedSeed(buildUploadFormData())

    seedResult.value = normalizeSeedResult(res.data)
    if (suggestions.value.length > 0 && !simulationRequirement.value.trim()) {
      applySuggestion(suggestions.value[0])
    }
    emit('add-log', `Seed analyzed for project ${seedResult.value.project_id || 'unknown'}.`)
  } catch (err) {
    localError.value = err.message || '现实事件分析失败'
    emit('add-log', `Seed analysis failed: ${localError.value}`)
  } finally {
    seedAnalyzing.value = false
  }
}

const buildUploadFormData = () => {
  const formData = new FormData()
  files.value.forEach(file => formData.append('files', file))
  if (additionalContext.value.trim()) {
    formData.append('additional_context', additionalContext.value.trim())
  }
  return formData
}

const applySuggestion = (suggestion) => {
  selectedSuggestion.value = suggestion
  simulationRequirement.value = suggestion
}

const handleGenerateOntology = async () => {
  if (!canGenerateOntology.value) return

  ontologyGenerating.value = true
  localError.value = ''
  emit('add-log', 'Generating ontology from confirmed simulation requirement...')

  try {
    const payload = {
      project_id: currentProjectId.value,
      simulation_requirement: simulationRequirement.value.trim()
    }
    if (additionalContext.value.trim()) {
      payload.additional_context = additionalContext.value.trim()
    }

    const res = await generateOntology(payload)
    const data = {
      ...seedResult.value,
      ...(res.data || {}),
      simulation_requirement: payload.simulation_requirement
    }
    seedResult.value = normalizeSeedResult(data)
    emit('ontology-generated', data)
  } catch (err) {
    localError.value = err.message || '本体生成失败'
    emit('add-log', `Ontology generation failed: ${localError.value}`)
  } finally {
    ontologyGenerating.value = false
  }
}

const selectOntologyItem = (item, type) => {
  selectedOntologyItem.value = { ...item, itemType: type }
}

watch(() => props.pendingUpload, (pending) => {
  if (!pending?.isPending) return

  if (pending.files?.length) {
    inputMode.value = 'file_upload'
    files.value = [...pending.files]
    searchQuery.value = ''
  }

  if (pending.simulationRequirement) {
    simulationRequirement.value = pending.simulationRequirement
  }
}, { immediate: true })
</script>

<style scoped>
.workbench-panel {
  height: 100%;
  background-color: #FAFAFA;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.scroll-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-card {
  background: #FFF;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  border: 1px solid #EAEAEA;
  transition: all 0.2s ease;
  position: relative;
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 700;
  color: #E0E0E0;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #000;
}

.step-title {
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.5px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.badge.success { background: #E8F5E9; color: #2E7D32; }
.badge.processing { background: #FF5722; color: #FFF; }
.badge.accent { background: #FF5722; color: #FFF; }
.badge.pending { background: #F5F5F5; color: #999; }

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
}

.description {
  font-size: 12px;
  color: #666;
  line-height: 1.5;
  margin-bottom: 16px;
}

.mode-switcher {
  display: grid;
  grid-template-columns: 1fr 1fr;
  background: #F5F5F5;
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
  margin-bottom: 16px;
}

.mode-btn {
  border: none;
  background: transparent;
  color: #666;
  border-radius: 4px;
  padding: 9px 12px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, box-shadow 0.2s;
}

.mode-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.mode-btn:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.input-block {
  margin-bottom: 14px;
}

.input-block.compact {
  margin-top: 12px;
}

.field-label,
.panel-title {
  display: block;
  font-size: 10px;
  color: #999;
  margin-bottom: 8px;
  font-weight: 700;
  letter-spacing: 0.6px;
}

.text-field,
.text-area {
  width: 100%;
  border: 1px solid #E0E0E0;
  border-radius: 6px;
  background: #FFF;
  color: #111;
  font-size: 13px;
  line-height: 1.5;
  padding: 11px 12px;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.text-field:focus,
.text-area:focus {
  border-color: #FF5722;
  box-shadow: 0 0 0 3px rgba(255, 87, 34, 0.1);
}

.hidden-input {
  display: none;
}

.upload-zone {
  min-height: 140px;
  border: 1px dashed #CCC;
  border-radius: 6px;
  background: #F9F9F9;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.upload-zone.drag-over {
  border-color: #FF5722;
  background: #FFF3EE;
}

.upload-zone.has-files {
  align-items: stretch;
  justify-content: flex-start;
}

.upload-placeholder {
  text-align: center;
  color: #777;
}

.upload-icon {
  font-size: 24px;
  color: #FF5722;
  margin-bottom: 8px;
}

.upload-title {
  font-size: 13px;
  font-weight: 700;
  color: #333;
}

.upload-hint {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.file-list {
  width: 100%;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 4px;
  padding: 8px 10px;
}

.file-name {
  font-size: 12px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-btn,
.close-btn {
  background: none;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.remove-btn:hover,
.close-btn:hover {
  color: #333;
}

.action-btn {
  width: 100%;
  background: #000;
  color: #FFF;
  border: none;
  padding: 14px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s, background 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.action-btn:hover:not(:disabled) {
  opacity: 0.82;
}

.action-btn:disabled {
  background: #CCC;
  cursor: not-allowed;
}

.error-text {
  margin: 10px 0 0;
  color: #C62828;
  font-size: 12px;
}

.summary-panel,
.sources-panel,
.suggestions-panel {
  margin-bottom: 16px;
}

.summary-text {
  background: #F9F9F9;
  border: 1px solid #EAEAEA;
  border-radius: 6px;
  padding: 14px;
  white-space: pre-wrap;
  word-break: break-word;
  color: #333;
  font-size: 12px;
  line-height: 1.7;
  max-height: 260px;
  overflow: auto;
  font-family: inherit;
}

.source-list,
.suggestion-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid #EAEAEA;
  border-radius: 6px;
  color: inherit;
  text-decoration: none;
  background: #FFF;
  transition: border-color 0.2s, background 0.2s;
}

.source-item:hover {
  border-color: #FF5722;
  background: #FFFDFB;
}

.source-title {
  font-size: 12px;
  color: #222;
  font-weight: 700;
}

.source-meta {
  font-size: 10px;
  color: #999;
}

.suggestion-btn {
  text-align: left;
  border: 1px solid #EAEAEA;
  background: #FFF;
  color: #333;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.5;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.suggestion-btn:hover,
.suggestion-btn.selected {
  border-color: #FF5722;
  background: #FFF3EE;
}

.empty-hint {
  color: #999;
  font-size: 12px;
  margin: 0;
}

.ontology-preview {
  margin-top: 16px;
}

.tags-container {
  margin-top: 12px;
  transition: opacity 0.3s;
}

.tags-container.dimmed {
  opacity: 0.3;
  pointer-events: none;
}

.tag-label {
  display: block;
  font-size: 10px;
  color: #AAA;
  margin-bottom: 8px;
  font-weight: 600;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.entity-tag {
  background: #F5F5F5;
  border: 1px solid #EEE;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  color: #333;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.2s;
}

.entity-tag.clickable {
  cursor: pointer;
}

.entity-tag.clickable:hover {
  background: #E0E0E0;
  border-color: #CCC;
}

.ontology-detail-overlay {
  position: absolute;
  top: 60px;
  left: 20px;
  right: 20px;
  bottom: 20px;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(4px);
  z-index: 10;
  border: 1px solid #EAEAEA;
  box-shadow: 0 4px 20px rgba(0,0,0,0.05);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #EAEAEA;
  background: #FAFAFA;
}

.detail-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-type-badge {
  font-size: 9px;
  font-weight: 700;
  color: #FFF;
  background: #000;
  padding: 2px 6px;
  border-radius: 2px;
  text-transform: uppercase;
}

.detail-name {
  font-size: 14px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.detail-desc {
  font-size: 12px;
  color: #444;
  line-height: 1.5;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #EAEAEA;
}

.detail-section {
  margin-bottom: 16px;
}

.section-label {
  display: block;
  font-size: 10px;
  font-weight: 600;
  color: #AAA;
  margin-bottom: 8px;
}

.attr-list,
.conn-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.attr-item {
  font-size: 11px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  padding: 4px;
  background: #F9F9F9;
  border-radius: 4px;
}

.attr-name {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: #000;
}

.attr-type {
  color: #999;
  font-size: 10px;
}

.attr-desc {
  color: #555;
  flex: 1;
  min-width: 150px;
}

.example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.example-tag {
  font-size: 11px;
  background: #FFF;
  border: 1px solid #E0E0E0;
  padding: 3px 8px;
  border-radius: 12px;
  color: #555;
}

.conn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  padding: 6px;
  background: #F5F5F5;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
}

.conn-node {
  font-weight: 600;
  color: #333;
}

.conn-arrow {
  color: #BBB;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  background: #F9F9F9;
  padding: 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #FF5722;
  margin-top: 12px;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid #FFCCBC;
  border-top-color: #FF5722;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 760px) {
  .scroll-container {
    padding: 16px;
  }

  .stats-grid,
  .mode-switcher {
    grid-template-columns: 1fr;
  }
}
</style>
