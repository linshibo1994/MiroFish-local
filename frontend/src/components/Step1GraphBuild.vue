<template>
  <div class="step1-root">

    <!-- 阶段1：输入阶段 -->
    <div v-if="!seedResult && !ontologyGenerating && currentPhase < 0" class="phase-input">
      <div class="input-center">
        <!-- 标题区 -->
        <div class="hero-section">
          <h1 class="hero-title"><span class="title-news">News</span><span class="title-power">Power</span><span class="title-suffix">. 传播推演</span></h1>
          <p class="hero-subtitle">输入任意事件，即刻推演未来</p>
          <div class="step-indicator">
            <span class="step-dot active">01 事件背景</span>
            <span class="step-line">———</span>
            <span class="step-dot">02 推演方向</span>
          </div>
        </div>

        <!-- 输入卡片 -->
        <div class="input-card">
          <!-- 文字输入区 -->
          <div class="text-input-section" :class="{ disabled: files.length > 0 }">
            <textarea
              v-model="searchQuery"
              class="keyword-textarea"
              placeholder="请输入你想要推演的主题"
              :disabled="isBusy || files.length > 0"
              @input="onTextInput"
            ></textarea>
            <p v-if="files.length > 0" class="input-disabled-hint">已上传文件，不可输入文字</p>
          </div>

          <!-- 分隔线 -->
          <div class="input-divider"></div>

          <!-- 文件上传区 -->
          <input
            ref="fileInput"
            type="file"
            multiple
            accept=".pdf,.md,.txt"
            class="hidden-input"
            :disabled="isBusy || searchQuery.trim().length > 0"
            @change="handleFileSelect"
          />
          <div class="file-upload-section" :class="{ disabled: searchQuery.trim().length > 0 }">
            <div
              class="upload-zone"
              :class="{ 'drag-over': isDragOver, 'has-files': files.length > 0, disabled: searchQuery.trim().length > 0 }"
              @click="!searchQuery.trim() && triggerFileInput()"
              @dragover.prevent="handleDragOver"
              @dragleave.prevent="handleDragLeave"
              @drop.prevent="handleDrop"
            >
              <!-- 空状态 -->
              <div v-if="files.length === 0 && !searchQuery.trim()" class="upload-placeholder">
                <div class="upload-icon">↑</div>
                <div class="upload-title">拖拽 PDF / MD / TXT 到这里</div>
                <div class="upload-hint">或点击选择文件</div>
              </div>
              <!-- 禁用状态 -->
              <div v-else-if="searchQuery.trim().length > 0" class="upload-placeholder disabled-placeholder">
                <div class="upload-hint">已输入文字，不可上传文件</div>
              </div>
              <!-- 文件列表 -->
              <div v-else class="file-list">
                <div v-for="(file, index) in files" :key="`${file.name}-${index}`" class="file-card">
                  <div class="file-info">
                    <span class="file-type-tag">{{ file.name.split('.').pop().toUpperCase() }}</span>
                    <span class="file-name">{{ file.name }}</span>
                    <span class="file-size">{{ (file.size / 1024).toFixed(1) }} KB</span>
                  </div>
                  <button type="button" class="file-remove-btn" :disabled="isBusy" @click.stop="removeFile(index)">×</button>
                </div>
              </div>
            </div>
            <p v-if="files.length > 0" class="input-disabled-hint upload-hint-text">已上传文件，文字输入已禁用</p>
          </div>

          <!-- 补充上下文（隐藏，仅在有内容时显示） -->
          <div v-if="additionalContext.trim()" class="context-row">
            <textarea
              v-model="additionalContext"
              class="context-textarea"
              placeholder="补充上下文（可选）：关注的时间线、角色、机构或传播平台"
              :disabled="isBusy"
              rows="2"
            ></textarea>
          </div>

          <!-- 提交按钮 -->
          <div class="submit-row">
            <button
              type="button"
              class="primary-btn submit-btn"
              :disabled="!canAnalyze"
              @click="analyzeSeed"
            >
              <span v-if="seedAnalyzing" class="spinner-sm"></span>
              {{ seedAnalyzing ? '正在分析...' : '生成推演方向' }}
            </button>
          </div>

          <p v-if="localError" class="error-text">{{ localError }}</p>
        </div>

        <!-- 优势卡片区 -->
        <div class="features-section">
          <h3 class="features-title">传播推演优势</h3>
          <div class="features-grid">
            <div class="feature-card">
              <span class="feature-icon">◈</span>
              <div class="feature-content">
                <div class="feature-name">通用全能，不限场景</div>
                <div class="feature-desc">适配舆情发酵、事件传播、大众态度演变等各类场景，上传文件即可推演，不局限单一用途</div>
              </div>
            </div>
            <div class="feature-card">
              <span class="feature-icon">◉</span>
              <div class="feature-content">
                <div class="feature-name">数据省心，无需预处理</div>
                <div class="feature-desc">支持各类非结构化资料直接导入，系统自动解析数据、搭建真实模拟场景，上手零门槛</div>
              </div>
            </div>
            <div class="feature-card">
              <span class="feature-icon">◎</span>
              <div class="feature-content">
                <div class="feature-name">超低成本，可高频试错</div>
                <div class="feature-desc">单次常规推演低至5元，低成本支持多版本方案反复模拟，轻松筛选最优传播策略</div>
              </div>
            </div>
            <div class="feature-card">
              <span class="feature-icon">◆</span>
              <div class="feature-content">
                <div class="feature-name">超大仿真规模，更贴近真实</div>
                <div class="feature-desc">支持百万级智能体同时模拟，高度还原海量人群的真实互动、传播联动，推演结果更精准</div>
              </div>
            </div>
            <div class="feature-card">
              <span class="feature-icon">◇</span>
              <div class="feature-content">
                <div class="feature-name">全程自动，一键出结果</div>
                <div class="feature-desc">从场景搭建、模拟推演到生成专业报告全自动化，无需人工操作，零基础也能用</div>
              </div>
            </div>
            <div class="feature-card">
              <span class="feature-icon">○</span>
              <div class="feature-content">
                <div class="feature-name">可交互可追溯，不做盲推演</div>
                <div class="feature-desc">可和模拟场景里的任意角色对话，也能智能解读报告、深挖细节，决策依据更扎实</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 阶段2：结果阶段 -->
    <div v-else-if="seedResult && !ontologyGenerating && currentPhase < 0" class="phase-result">
      <div class="result-center">
        <!-- 步骤指示器 -->
        <div class="step-indicator result-indicator">
          <span class="step-dot">01 事件背景</span>
          <span class="step-line">———</span>
          <span class="step-dot active">02 推演方向</span>
        </div>

        <!-- 事件摘要卡片 -->
        <div class="result-card">
          <div class="card-header-row" @click="showSummary = !showSummary">
            <span class="card-section-title">完整事件内容</span>
            <button type="button" class="collapse-btn">{{ showSummary ? '▲' : '▼' }}</button>
          </div>
          <div v-show="showSummary" class="summary-content">
            <div class="summary-text markdown-body" v-html="renderedSummary"></div>
          </div>
        </div>

        <!-- 推演方向区域 -->
        <div class="result-card">
          <div class="card-section-title">选择推演方向</div>
          <div class="suggestions-list">
            <div
              v-for="suggestion in suggestions"
              :key="suggestion"
              class="suggestion-card"
              :class="{ selected: selectedSuggestion === suggestion }"
              @click="applySuggestion(suggestion)"
            >
              <span class="suggestion-check">{{ selectedSuggestion === suggestion ? '◉' : '○' }}</span>
              <span class="suggestion-text">{{ formatSuggestion(suggestion) }}</span>
            </div>
          </div>
          <!-- 自定义方向 -->
          <div class="custom-direction">
            <div class="custom-direction-label">自定义方向（如不需要推荐的建议，可以自行输入您想要推演的任意方向/主题）</div>
            <textarea
              v-model="simulationRequirement"
              class="direction-textarea"
              placeholder="选择一条建议，或手动输入你要推演的问题"
              :disabled="isBusy"
              rows="4"
            ></textarea>
          </div>
        </div>

        <!-- 参考信息源 -->
        <div v-if="sources.length" class="result-card sources-card">
          <div class="card-header-row" @click="showSources = !showSources">
            <span class="card-section-title">参考 {{ sources.length }} 条信息源</span>
            <button type="button" class="collapse-btn">{{ showSources ? '▲' : '▼' }}</button>
          </div>
          <div v-show="showSources" class="sources-list">
            <a
              v-for="(source, index) in sources"
              :key="source.url || `${source.title}-${index}`"
              class="source-item"
              :href="source.url"
              target="_blank"
              rel="noopener noreferrer nofollow"
            >
              <span class="source-title">{{ source.title || source.name || source.url || '未命名来源' }}</span>
              <span class="source-meta">{{ source.publisher || source.site_name || source.siteName || source.published_at || source.date_published || source.datePublished || '来源记录' }}</span>
            </a>
          </div>
        </div>

        <!-- 底部按钮区 -->
        <div class="result-actions">
          <button type="button" class="back-btn" @click="resetToInput">返回修改</button>
          <button
            type="button"
            class="primary-btn start-btn"
            :disabled="!canGenerateOntology"
            @click="handleGenerateOntology"
          >开始推演</button>
        </div>

        <p v-if="localError" class="error-text">{{ localError }}</p>
      </div>
    </div>

    <!-- 阶段3：图谱构建工作台 -->
    <div v-else class="phase-progress workbench-phase">
      <div class="scroll-container">
        <div class="step-card completed">
          <div class="step-card-header">
            <div class="step-info">
              <span class="step-num">01</span>
              <span class="step-title">本体生成</span>
            </div>
            <div class="step-status">
              <span class="badge success">已完成</span>
            </div>
          </div>

          <div class="step-card-content">
            <p class="api-note">POST /api/graph/ontology/generate</p>
            <p class="description">
              LLM 分析文档内容与模拟需求，提取出现实种子，自动生成合适的本体结构。
            </p>

            <div v-if="ontologyProgress && currentPhase === 0" class="progress-section">
              <div class="spinner-sm dark"></div>
              <span>{{ ontologyProgress.message || '正在生成本体...' }}</span>
            </div>

            <div v-if="projectData?.ontology" class="ontology-preview">
              <div class="tags-container" :class="{ dimmed: selectedOntologyItem }">
                <span class="tag-label">生成的实体类型</span>
                <div class="tags-list">
                  <span
                    v-for="entity in projectData.ontology.entity_types"
                    :key="entity.name"
                    class="entity-tag clickable"
                    @click="selectOntologyItem(entity, 'entity')"
                  >{{ translateEntityType(entity.name) }}</span>
                </div>
              </div>
              <div class="tags-container" :class="{ dimmed: selectedOntologyItem }">
                <span class="tag-label">生成的关系类型</span>
                <div class="tags-list">
                  <span
                    v-for="rel in projectData.ontology.edge_types"
                    :key="rel.name"
                    class="entity-tag clickable"
                    @click="selectOntologyItem(rel, 'relation')"
                  >{{ translateRelationType(rel.name) }}</span>
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
          <div class="step-card-header">
            <div class="step-info">
              <span class="step-num">02</span>
              <span class="step-title">图谱构建</span>
            </div>
            <div class="step-status">
              <span v-if="currentPhase > 1" class="badge success">已完成</span>
              <span v-else class="badge processing">{{ buildProgress?.progress || 0 }}%</span>
            </div>
          </div>

          <div class="step-card-content">
            <p class="api-note">POST /api/graph/build</p>
            <p class="description">
              基于生成的本体，将文档自动分块后调用 Zep 构建知识图谱，提取实体和关系，并形成时序记忆与社区摘要。
            </p>
            <p v-if="buildProgress?.message" class="progress-message inline">{{ buildProgress.message }}</p>

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
          <div class="step-card-header">
            <div class="step-info">
              <span class="step-num">03</span>
              <span class="step-title">构建完成</span>
            </div>
            <div class="step-status">
              <span v-if="currentPhase >= 2" class="badge accent">进行中</span>
              <span v-else class="badge pending">等待</span>
            </div>
          </div>

          <div class="step-card-content">
            <p class="api-note">POST /api/simulation/create</p>
            <p class="description">图谱构建已完成，请进入下一步进行模拟环境搭建。</p>
            <button type="button" class="action-btn" :disabled="currentPhase < 2" @click="emit('next-step')">
              进入环境搭建 →
            </button>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { marked } from 'marked'
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

const emit = defineEmits(['ontology-generated', 'workspace-started', 'next-step', 'add-log'])

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
const showSources = ref(false)
const showSummary = ref(true)

const resetToInput = () => {
  seedResult.value = null
  selectedSuggestion.value = ''
  simulationRequirement.value = ''
  localError.value = ''
}

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
  const result = seedResult.value || {}
  if (result.seed_input_mode === 'file_upload') {
    return result.seed_full_content_md || result.seed_summary_md || result.analysis_summary || '暂无内容。'
  }
  return result.seed_summary_md || result.seed_full_content_md || result.analysis_summary || '暂无内容。'
})

const renderedSummary = computed(() => {
  const md = seedSummary.value
  if (!md) return ''
  return marked(md)
})

const formatSuggestion = (text) => {
  return String(text || '').replace(/可模拟/g, '推演')
}

const currentProjectId = computed(() => seedResult.value?.project_id || props.projectData?.project_id || '')

const canAnalyze = computed(() => {
  if (isBusy.value) return false
  return searchQuery.value.trim().length > 0 || files.value.length > 0
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

const onTextInput = () => {
  if (searchQuery.value.trim()) {
    inputMode.value = 'web_search'
  }
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
  if (files.value.length > 0) {
    inputMode.value = 'file_upload'
  }
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
  if (files.value.length === 0) {
    inputMode.value = 'web_search'
  }
  resetAnalysisResult()
}

const normalizeSeedResult = (data) => {
  const normalized = data || {}
  return {
    ...normalized,
    seed_summary_md: normalized.seed_summary_md || normalized.analysis_summary || '',
    seed_full_content_md: normalized.seed_full_content_md || normalized.full_content_md || '',
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
  const cleanSuggestion = formatSuggestion(suggestion)
  selectedSuggestion.value = suggestion
  simulationRequirement.value = cleanSuggestion
}

const handleGenerateOntology = async () => {
  if (!canGenerateOntology.value) return
  ontologyGenerating.value = true
  localError.value = ''
  emit('workspace-started', {
    project_id: currentProjectId.value,
    simulation_requirement: simulationRequirement.value.trim(),
    seed_summary_md: seedResult.value?.seed_summary_md,
    analysis_summary: seedResult.value?.analysis_summary,
    search_query: searchQuery.value.trim()
  })
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
/* ===== 根容器 ===== */
.step1-root {
  height: 100%;
  background: #F5F7FA;
  overflow-y: auto;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* ===== 阶段1：输入 ===== */
.phase-input {
  min-height: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 24px 60px;
}

.input-center {
  width: 100%;
  max-width: 780px;
  display: flex;
  flex-direction: column;
  gap: 32px;
}

/* 标题区 */
.hero-section {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.hero-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 2.5rem;
  font-weight: 800;
  margin: 0;
  line-height: 1.2;
}

.title-news {
  color: #1A1A2E;
}

.title-power {
  background: linear-gradient(135deg, #1677FF, #6366F1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.title-suffix {
  color: #1A1A2E;
}

.hero-subtitle {
  font-size: 1rem;
  color: #6B7280;
  margin: 0;
}

.step-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}

.step-dot {
  font-size: 13px;
  font-weight: 600;
  color: #9CA3AF;
}

.step-dot.active {
  color: #1677FF;
}

.step-line {
  color: #D1D5DB;
  font-size: 13px;
  letter-spacing: 2px;
}

/* 输入卡片 */
.input-card {
  background: #FFFFFF;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 输入区域互斥样式 */
.text-input-section.disabled .keyword-textarea {
  background: #F3F4F6;
  color: #9CA3AF;
  cursor: not-allowed;
}

.file-upload-section.disabled .upload-zone {
  border-color: #E5E7EB;
  background: #F3F4F6;
  cursor: not-allowed;
  pointer-events: none;
}

.input-disabled-hint {
  font-size: 12px;
  color: #9CA3AF;
  margin: 4px 0 0;
  font-style: italic;
}

.upload-hint-text {
  margin-top: 6px;
}

.input-divider {
  height: 1px;
  background: #E8ECF0;
  margin: 4px 0;
}

.disabled-placeholder {
  opacity: 0.5;
}

.upload-zone.disabled {
  border-color: #E5E7EB;
  background: #F3F4F6;
  cursor: not-allowed;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.keyword-textarea {
  width: 100%;
  min-height: 120px;
  border: none;
  outline: none;
  resize: none;
  font-size: 15px;
  color: #1A1A2E;
  line-height: 1.6;
  font-family: inherit;
  background: transparent;
  box-sizing: border-box;
}

.keyword-textarea::placeholder {
  color: #9CA3AF;
}

.context-textarea {
  width: 100%;
  border: 1px solid #E8ECF0;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: #1A1A2E;
  line-height: 1.5;
  resize: none;
  outline: none;
  font-family: inherit;
  background: #F9FAFB;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.context-textarea:focus {
  border-color: #1677FF;
  background: #FFFFFF;
}

.context-textarea::placeholder {
  color: #9CA3AF;
}

.context-row {
  margin-top: 4px;
}

/* 文件上传 */
.hidden-input {
  display: none;
}

.upload-zone {
  min-height: 140px;
  border: 2px dashed #D1D5DB;
  border-radius: 8px;
  background: #F9FAFB;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.upload-zone.drag-over {
  border-color: #1677FF;
  background: #EFF6FF;
}

.upload-zone.has-files {
  align-items: stretch;
  justify-content: flex-start;
}

.upload-placeholder {
  text-align: center;
  color: #6B7280;
}

.upload-icon {
  font-size: 28px;
  color: #1677FF;
  margin-bottom: 8px;
}

.upload-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.upload-hint {
  font-size: 12px;
  color: #9CA3AF;
  margin-top: 4px;
}

.file-list {
  width: 100%;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #FFFFFF;
  border: 1px solid #E8ECF0;
  border-radius: 8px;
  padding: 10px 12px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.file-type-tag {
  font-size: 10px;
  font-weight: 700;
  color: #1677FF;
  background: #EFF6FF;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.file-name {
  font-size: 13px;
  color: #374151;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 11px;
  color: #9CA3AF;
  flex-shrink: 0;
}

.file-remove-btn {
  background: none;
  border: none;
  color: #9CA3AF;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  padding: 0 4px;
  flex-shrink: 0;
}

.file-remove-btn:hover {
  color: #EF4444;
}

/* 主按钮 */
.submit-row {
  display: flex;
  justify-content: flex-end;
}

.primary-btn {
  background: linear-gradient(135deg, #1677FF, #6366F1);
  color: #FFFFFF;
  border: none;
  border-radius: 8px;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-family: inherit;
}

.primary-btn:hover:not(:disabled) {
  opacity: 0.88;
}

.primary-btn:disabled {
  background: #D1D5DB;
  cursor: not-allowed;
}

.error-text {
  color: #EF4444;
  font-size: 13px;
  margin: 0;
}

/* 优势卡片区 */
.features-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.features-title {
  font-size: 14px;
  font-weight: 700;
  color: #6B7280;
  margin: 0;
  text-align: center;
  letter-spacing: 0.5px;
}

.features-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
}

.feature-card {
  background: #FFFFFF;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border: 1px solid #E8ECF0;
  transition: box-shadow 0.2s;
}

.feature-card:hover {
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.08);
}

.feature-icon {
  font-size: 18px;
  color: #1677FF;
  flex-shrink: 0;
  line-height: 1.4;
}

.feature-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.feature-name {
  font-size: 13px;
  font-weight: 700;
  color: #1A1A2E;
}

.feature-desc {
  font-size: 11px;
  color: #6B7280;
  line-height: 1.4;
}

/* ===== 阶段2：结果 ===== */
.phase-result {
  min-height: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 40px 24px 60px;
}

.result-center {
  width: 100%;
  max-width: 680px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-indicator {
  justify-content: center;
  margin-bottom: 8px;
}

.result-card {
  background: #FFFFFF;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  padding: 20px;
  border: 1px solid #E8ECF0;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
}

.card-section-title {
  font-size: 14px;
  font-weight: 700;
  color: #1A1A2E;
}

.collapse-btn {
  background: none;
  border: none;
  color: #9CA3AF;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}

.summary-content {
  margin-top: 12px;
}

.summary-text {
  background: #F9FAFB;
  border: 1px solid #E8ECF0;
  border-radius: 8px;
  padding: 14px;
  color: #374151;
  font-size: 13px;
  line-height: 1.7;
  max-height: 300px;
  overflow-y: auto;
  font-family: inherit;
}

.summary-text :deep(h1),
.summary-text :deep(h2),
.summary-text :deep(h3) {
  font-size: 14px;
  font-weight: 700;
  margin: 12px 0 6px;
  color: #1A1A2E;
}

.summary-text :deep(h1) { font-size: 16px; }

.summary-text :deep(p) { margin: 6px 0; }

.summary-text :deep(ul),
.summary-text :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.summary-text :deep(li) { margin: 3px 0; }

/* 推演方向 */
.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.suggestion-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  border: 1px solid #E5E7EB;
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.suggestion-card.selected {
  border: 2px solid #1677FF;
  background: #EFF6FF;
}

.suggestion-card:hover:not(.selected) {
  border-color: #93C5FD;
  background: #F8FAFF;
}

.suggestion-check {
  font-size: 16px;
  color: #1677FF;
  flex-shrink: 0;
  line-height: 1.4;
}

.suggestion-text {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
}

.custom-direction {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.custom-direction-label {
  font-size: 12px;
  font-weight: 600;
  color: #6B7280;
}

.direction-textarea {
  width: 100%;
  border: 1px solid #E8ECF0;
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  color: #1A1A2E;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  font-family: inherit;
  background: #F9FAFB;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.direction-textarea:focus {
  border-color: #1677FF;
  background: #FFFFFF;
}

/* 信息源 */
.sources-card {
  border: 1px solid #E8ECF0;
}

.sources-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.source-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid #E8ECF0;
  border-radius: 8px;
  color: inherit;
  text-decoration: none;
  background: #F9FAFB;
  transition: border-color 0.2s, background 0.2s;
}

.source-item:hover {
  border-color: #1677FF;
  background: #EFF6FF;
}

.source-title {
  font-size: 13px;
  color: #1A1A2E;
  font-weight: 600;
}

.source-meta {
  font-size: 11px;
  color: #9CA3AF;
}

/* 底部按钮 */
.result-actions {
  display: flex;
  gap: 12px;
}

.back-btn {
  flex: 1;
  background: #FFFFFF;
  color: #374151;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 14px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
  font-family: inherit;
}

.back-btn:hover {
  background: #F3F4F6;
  border-color: #D1D5DB;
}

.start-btn {
  flex: 2;
}

/* ===== 阶段3：图谱构建工作台 ===== */
.workbench-phase {
  height: 100%;
  background: #FAFAFA;
  overflow: hidden;
}

.scroll-container {
  height: 100%;
  overflow-y: auto;
  padding: 16px 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.step-card {
  background: #FFFFFF;
  border-radius: 8px;
  padding: 16px 18px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid #EAEAEA;
  transition: border-color 0.2s, box-shadow 0.2s;
  position: relative;
}

.step-card.active {
  border-color: #FF5722;
  box-shadow: 0 4px 12px rgba(255, 87, 34, 0.08);
}

.step-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.step-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-size: 20px;
  font-weight: 800;
  color: #D1D5DB;
}

.step-card.active .step-num,
.step-card.completed .step-num {
  color: #111827;
}

.step-title {
  font-weight: 700;
  font-size: 14px;
  color: #111827;
  letter-spacing: 0.2px;
}

.badge {
  font-size: 10px;
  padding: 4px 8px;
  border-radius: 4px;
  font-weight: 700;
  white-space: nowrap;
}

.badge.success {
  background: #E8F5E9;
  color: #2E7D32;
}

.badge.processing,
.badge.accent {
  background: #FF5722;
  color: #FFFFFF;
}

.badge.pending {
  background: #F5F5F5;
  color: #999999;
}

.step-card-content {
  position: relative;
}

.api-note {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: #999999;
  margin: 0 0 8px;
}

.description {
  font-size: 12px;
  color: #666666;
  line-height: 1.6;
  margin: 0 0 12px;
}

.progress-section {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #FF5722;
  margin-bottom: 14px;
}

.progress-message.inline {
  text-align: left;
  color: #6B7280;
  font-size: 12px;
  margin: -4px 0 14px;
}

/* 本体预览 */
.ontology-preview {
  width: 100%;
  background: #FFFFFF;
  border-radius: 8px;
  padding: 0;
  border: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tags-container {
  transition: opacity 0.3s;
  margin-top: 4px;
}

.tags-container.dimmed {
  opacity: 0.3;
  pointer-events: none;
}

.tag-label {
  display: block;
  font-size: 10px;
  color: #AAAAAA;
  margin-bottom: 8px;
  font-weight: 700;
  letter-spacing: 0.4px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.entity-tag {
  background: #F5F5F5;
  border: 1px solid #EEEEEE;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 10px;
  color: #333333;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.2s;
}

.entity-tag.clickable {
  cursor: pointer;
}

.entity-tag.clickable:hover {
  background: #E0E0E0;
  border-color: #CCCCCC;
  color: #111827;
}

/* 图谱统计 */
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  width: 100%;
  background: #F9F9F9;
  padding: 14px 16px;
  border-radius: 6px;
}

.stat-card {
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 20px;
  font-weight: 800;
  color: #000000;
  font-family: 'JetBrains Mono', monospace;
}

.stat-label {
  font-size: 9px;
  color: #999999;
  text-transform: uppercase;
  margin-top: 4px;
  display: block;
  letter-spacing: 0.5px;
}

.action-btn {
  width: 100%;
  background: #111111;
  color: #FFFFFF;
  border: none;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  transition: opacity 0.2s, background 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-family: inherit;
}

.action-btn:hover:not(:disabled) {
  opacity: 0.82;
}

.action-btn:disabled {
  background: #CCCCCC;
  cursor: not-allowed;
}

/* 本体详情 overlay */
.ontology-detail-overlay {
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  width: 90%;
  max-width: 560px;
  max-height: 70vh;
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(8px);
  z-index: 100;
  border: 1px solid #E8ECF0;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.12);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid #E8ECF0;
  background: #F9FAFB;
}

.detail-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.detail-type-badge {
  font-size: 10px;
  font-weight: 700;
  color: #FFFFFF;
  background: #1677FF;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}

.detail-name {
  font-size: 15px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  color: #1A1A2E;
}

.close-btn {
  background: none;
  border: none;
  color: #9CA3AF;
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
  padding: 0;
}

.close-btn:hover {
  color: #374151;
}

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}

.detail-desc {
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px dashed #E8ECF0;
}

.detail-section {
  margin-bottom: 16px;
}

.section-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #9CA3AF;
  margin-bottom: 8px;
  letter-spacing: 0.5px;
}

.attr-list,
.conn-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.attr-item {
  font-size: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
  padding: 6px 8px;
  background: #F9FAFB;
  border-radius: 6px;
}

.attr-name {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 600;
  color: #1A1A2E;
}

.attr-type {
  color: #9CA3AF;
  font-size: 11px;
}

.attr-desc {
  color: #6B7280;
  flex: 1;
  min-width: 150px;
}

.example-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.example-tag {
  font-size: 12px;
  background: #FFFFFF;
  border: 1px solid #E5E7EB;
  padding: 3px 10px;
  border-radius: 12px;
  color: #6B7280;
}

.conn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 6px 8px;
  background: #F3F4F6;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
}

.conn-node {
  font-weight: 600;
  color: #374151;
}

.conn-arrow {
  color: #9CA3AF;
}

/* spinner */
.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.4);
  border-top-color: #FFFFFF;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  flex-shrink: 0;
}

.spinner-sm.dark {
  border-color: #FFCCBC;
  border-top-color: #FF5722;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 响应式 */
@media (max-width: 760px) {
  .scroll-container {
    padding: 16px;
  }

  .features-grid {
    grid-template-columns: 1fr 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .result-actions {
    flex-direction: column;
  }

  .hero-title {
    font-size: 1.8rem;
  }
}
</style>
