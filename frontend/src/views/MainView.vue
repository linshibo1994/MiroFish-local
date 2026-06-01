<template>
  <div class="main-view" :class="{ 'landing-mode': isLandingMode }">

    <!-- 薄左侧图标栏（始终显示） -->
    <aside class="icon-sidebar">
      <div class="icon-sidebar-top">
        <button class="icon-btn" title="首页" aria-label="首页" @click="startNewSession">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
        </button>
        <button class="icon-btn" :class="{ active: showHistory }" title="历史记录" aria-label="历史记录" @click="showHistory = !showHistory">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="10"/></svg>
        </button>
      </div>
    </aside>

    <!-- 历史记录面板（可切换） -->
    <aside class="history-panel" :class="{ visible: showHistory }">
      <div class="history-panel-header">
        <button class="new-chat-btn" @click="startNewSession">+ 新建对话</button>
      </div>
      <div class="history-panel-list">
        <section class="history-section">
          <div class="history-section-title">推演记录</div>
          <div v-if="simulationHistoryLoading" class="history-empty">正在加载推演记录...</div>
          <div v-else-if="simulationHistory.length === 0" class="history-empty">暂无推演记录</div>
          <div
            v-for="simulation in simulationHistory"
            v-else
            :key="simulation.simulation_id"
            class="history-item simulation-history-item"
            :class="{ active: currentSimulationId === simulation.simulation_id }"
            @click="navigateToSimulation(simulation.simulation_id)"
          >
            <div class="history-item-row">
              <span class="history-item-title">{{ formatSimulationTitle(simulation) }}</span>
              <span class="simulation-status" :class="simulation.status">{{ formatSimulationStatus(simulation.status) }}</span>
            </div>
            <span class="history-item-date">{{ formatDate(simulation.updated_at || simulation.created_at) }}</span>
          </div>
        </section>

        <section class="history-section">
          <div class="history-section-title">项目会话</div>
          <div v-if="sessions.length === 0" class="history-empty">暂无项目会话</div>
        <div
          v-for="session in sessions"
          :key="session.projectId"
          class="history-item"
          :class="{ active: currentProjectId === session.projectId }"
          @click="navigateToSession(session.projectId)"
        >
          <span class="history-item-title">{{ session.title }}</span>
          <span class="history-item-date">{{ formatDate(session.createdAt) }}</span>
        </div>
        </section>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="main-content">

      <!-- 首页 Header（简洁模式） -->
      <header v-if="isLandingMode" class="app-header landing-header">
        <div class="header-left">
          <span class="brand">传播推演</span>
        </div>
        <div class="header-right">
          <div class="status-pill">
            <span class="pill-step">Step {{ currentStep }}/5</span>
            <span class="pill-name">{{ stepNames[currentStep - 1] }}</span>
            <span class="pill-divider">|</span>
            <span class="pill-dot" :class="statusClass"></span>
            <span class="pill-status">{{ statusText }}</span>
          </div>
        </div>
      </header>

      <!-- 二级页 Header（完整模式） -->
      <template v-else>
        <WorkflowTopbar
          :currentStep="currentStep"
          :projectId="projectData?.project_id || currentProjectId"
          :simulationId="currentSimulationId"
          :reportId="currentReportId"
          @missing-report="handleMissingReportNavigation"
        />

        <header class="app-header workspace-header">
          <div class="header-left">
            <span class="event-title">{{ projectTitle }}</span>
            <button class="info-icon-btn" title="事件信息">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
            </button>
          </div>
          <div class="header-center">
            <div class="view-switcher">
              <button v-for="mode in viewModes" :key="mode.key" class="switch-btn" :class="{ active: viewMode === mode.key }" @click="viewMode = mode.key">{{ mode.label }}</button>
            </div>
          </div>
          <div class="header-right">
            <span class="step-badge">Step {{ currentStep }}/5</span>
            <span class="step-label">{{ stepNames[currentStep - 1] }}</span>
            <span class="step-divider"></span>
            <span class="status-dot" :class="statusClass"></span>
            <span class="status-text">{{ statusText }}</span>
          </div>
        </header>
      </template>

      <!-- 首页内容区（Step1 输入/结果阶段） -->
      <div v-if="isLandingMode" class="landing-content">
        <Step1GraphBuild
          :currentPhase="currentPhase"
          :projectData="projectData"
          :projectStatus="projectData?.status || ''"
          :projectError="projectData?.error || ''"
          :pendingUpload="pendingUploadState"
          :ontologyProgress="ontologyProgress"
          :buildProgress="buildProgress"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @workspace-started="handleWorkspaceStarted"
          @add-log="addLog"
          @next-step="handleNextStep"
        />
      </div>

      <!-- 二级页内容区（进度阶段 + Step2+） -->
      <div v-else class="workspace-content">
        <div class="panel-wrapper left" :style="leftPanelStyle">
          <GraphPanel
            :graphData="graphData"
            :loading="graphLoading"
            :currentPhase="currentPhase"
            :status="projectData?.status || ''"
            @refresh="refreshGraph"
            @toggle-maximize="toggleMaximize('graph')"
          />
        </div>
        <div class="panel-wrapper right" :style="rightPanelStyle">
          <Step1GraphBuild
            v-if="currentStep === 1"
            :currentPhase="currentPhase"
            :projectData="projectData"
            :projectStatus="projectData?.status || ''"
            :projectError="projectData?.error || ''"
            :pendingUpload="pendingUploadState"
            :ontologyProgress="ontologyProgress"
            :buildProgress="buildProgress"
            :graphData="graphData"
            :systemLogs="systemLogs"
            @workspace-started="handleWorkspaceStarted"
            @add-log="addLog"
            @next-step="handleNextStep"
          />
          <Step2EnvSetup
            v-else-if="currentStep === 2"
            :simulationId="currentSimulationId"
            :projectData="projectData"
            :graphData="graphData"
            :systemLogs="systemLogs"
            @go-back="handleGoBack"
            @next-step="handleNextStep"
            @add-log="addLog"
            @update-status="updateEnvStatus"
            @simulation-created="handleSimulationCreated"
          />
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step1GraphBuild from '../components/Step1GraphBuild.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import WorkflowTopbar from '../components/WorkflowTopbar.vue'
import { getProject, generateOntology, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { createSimulation, listSimulations } from '../api/simulation'
import { checkReportStatus } from '../api/report'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'
import { getSessions, addSession } from '../store/sessionHistory'
import { getProjectDisplayTitle } from '../utils/projectTitle.js'

const route = useRoute()
const router = useRouter()

const viewMode = ref('split')
const viewModes = [
  { key: 'graph', label: '图谱' },
  { key: 'split', label: '双栏' },
  { key: 'workbench', label: '工作台' }
]
const showHistory = ref(false)

const currentStep = ref(1)
const stepNames = ['图谱构建', '环境搭建', '双平台推演', '生成报告', '深入对话']

const currentProjectId = ref(route.params.projectId)
const loading = ref(false)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const currentSimulationId = ref('')
const currentReportId = ref('')
const currentPhase = ref(-1)
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const systemLogs = ref([])
const pendingUploadState = ref(null)
const simulationCreating = ref(false)
const envSetupStatus = ref('processing')
const simulationHistory = ref([])
const simulationHistoryLoading = ref(false)

const sessions = ref(getSessions())

const isLandingMode = computed(() => currentStep.value === 1 && currentPhase.value < 0 && !projectData.value?.ontology)

const projectTitle = computed(() => {
  return getProjectDisplayTitle(projectData.value)
})

const refreshSessions = () => { sessions.value = getSessions() }

const formatDate = (ts) => {
  if (!ts) return '-'
  const date = typeof ts === 'number' ? new Date(ts) : new Date(ts)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('zh-CN')
}

const formatSimulationStatus = (status) => {
  const labels = {
    created: '已创建',
    preparing: '准备中',
    ready: '就绪',
    running: '运行中',
    paused: '已暂停',
    stopped: '已停止',
    completed: '已完成',
    failed: '失败'
  }
  return labels[status] || status || '未知'
}

const formatSimulationTitle = (simulation) => {
  const created = formatDate(simulation.created_at)
  const total = Number(simulation.profiles_count || simulation.entities_count || 0)
  return total > 0 ? `${created} · ${total} 个智能体` : `推演 ${simulation.simulation_id?.slice(-6) || ''}`
}

const navigateToSession = (projectId) => {
  showHistory.value = false
  router.push('/process/' + projectId)
}

const navigateToSimulation = (simulationId) => {
  if (!simulationId) return
  showHistory.value = false
  router.push({ name: 'SimulationRun', params: { simulationId } })
}

const startNewSession = () => {
  showHistory.value = false
  if (route.params.projectId === 'new') {
    currentStep.value = 1
    currentPhase.value = -1
    projectData.value = null
    graphData.value = null
    currentSimulationId.value = ''
    currentReportId.value = ''
    ontologyProgress.value = null
    buildProgress.value = null
    systemLogs.value = []
    error.value = ''
    stopPolling()
    stopGraphPolling()
    handleNewProject()
  } else {
    router.push('/process/new')
  }
}

let pollTimer = null
let graphPollTimer = null
const GRAPH_BUILD_POLL_INTERVAL_MS = 5000

const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1 }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, pointerEvents: 'none' }
  return { width: '50%', opacity: 1 }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1 }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, pointerEvents: 'none' }
  return { width: '50%', opacity: 1 }
})


const statusClass = computed(() => {
  if (error.value) return 'error'
  if (simulationCreating.value) return 'processing'
  if (currentStep.value === 2) return envSetupStatus.value
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return '错误'
  if (simulationCreating.value) return '创建中'
  if (currentStep.value === 2) {
    if (envSetupStatus.value === 'error') return '错误'
    if (envSetupStatus.value === 'completed') return 'Ready'
    return '准备中'
  }
  if (currentPhase.value >= 2) return 'Ready'
  if (currentPhase.value === 1) return 'Building'
  if (currentPhase.value === 0) return '生成中'
  return '等待输入'
})

const addLog = (msg) => {
  const now = new Date()
  const time = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + now.getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  if (systemLogs.value.length > 100) systemLogs.value.shift()
}

const toggleMaximize = (target) => {
  viewMode.value = viewMode.value === target ? 'split' : target
}


const handleNextStep = (params = {}) => {
  if (currentStep.value === 1) {
    enterEnvironmentSetup()
    return
  }
  if (currentStep.value === 2) {
    addLog('进入 Step 3: 开始模拟')
    const routeParams = { name: 'SimulationRun', params: { simulationId: currentSimulationId.value } }
    if (params.maxRounds) routeParams.query = { maxRounds: params.maxRounds }
    router.push(routeParams)
    return
  }
  if (currentStep.value < 5) {
    currentStep.value++
    addLog(`进入 Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

const updateEnvStatus = (status) => { envSetupStatus.value = status || 'processing' }

const handleSimulationCreated = (simulationId) => {
  currentSimulationId.value = simulationId || ''
  if (currentSimulationId.value) addLog(`模拟实例同步完成: ${currentSimulationId.value}`)
  loadReportContext()
}

const loadReportContext = async () => {
  if (!currentSimulationId.value) {
    currentReportId.value = ''
    return
  }
  try {
    const res = await checkReportStatus(currentSimulationId.value)
    currentReportId.value = res.success && res.data?.report_id ? res.data.report_id : ''
  } catch (err) {
    currentReportId.value = ''
  }
}

const handleMissingReportNavigation = async (targetStep) => {
  await loadReportContext()
  if (currentReportId.value) {
    router.push({
      name: targetStep === 5 ? 'Interaction' : 'Report',
      params: { reportId: currentReportId.value }
    })
  } else {
    addLog('当前模拟尚未生成报告，无法跳转到报告或深入对话。')
  }
}

const handleGoBack = () => {
  if (currentStep.value > 1) {
    currentStep.value--
    addLog(`返回 Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

const initProject = async () => {
  addLog('Project view initialized.')
  if (currentProjectId.value === 'new') {
    await handleNewProject()
  } else {
    await loadProject()
  }
}

const handleNewProject = async () => {
  const pending = getPendingUpload()
  pendingUploadState.value = pending.isPending ? pending : null
  currentPhase.value = -1
  ontologyProgress.value = null
  buildProgress.value = null
  projectData.value = null
  graphData.value = null
  currentSimulationId.value = ''
  currentReportId.value = ''
  simulationHistory.value = []
  addLog('Step1 ready. Waiting for seed input.')
}


const handleOntologyGenerated = async (data) => {
  if (!data?.project_id) {
    error.value = '本体生成结果缺少 project_id'
    addLog('Error: ontology result missing project_id.')
    return
  }
  currentProjectId.value = data.project_id
  projectData.value = data
  currentPhase.value = 0
  ontologyProgress.value = null
  error.value = ''
  clearPendingUpload()
  pendingUploadState.value = null

  addSession({
    id: data.project_id,
    title: (data.seed_summary_md || '新会话').slice(0, 40),
    projectId: data.project_id,
    createdAt: Date.now()
  })
  refreshSessions()

  addLog(`Ontology generated successfully for project ${data.project_id}`)
  await startBuildGraph()
  router.replace({ name: 'Process', params: { projectId: data.project_id } })
}

const handleWorkspaceStarted = (data = {}) => {
  if (currentPhase.value >= 0) return
  if (data.project_id) currentProjectId.value = data.project_id
  projectData.value = {
    ...(projectData.value || {}),
    ...data,
    project_id: data.project_id || projectData.value?.project_id || currentProjectId.value
  }
  currentPhase.value = 0
  ontologyProgress.value = { message: '正在生成本体...' }
  error.value = ''
  clearPendingUpload()
  pendingUploadState.value = null
  addLog('切换到图谱构建工作台，等待本体生成完成。')
  if (data.ontology_payload) {
    generateOntologyAndBuild(data.ontology_payload, data)
  }
}

const handleOntologyFailed = (message) => {
  currentPhase.value = -1
  ontologyProgress.value = null
  error.value = message || '本体生成失败'
  addLog(`本体生成失败，已返回推演方向确认页: ${error.value}`)
}

const generateOntologyAndBuild = async (payload, seedSnapshot = {}) => {
  try {
    const res = await generateOntology(payload)
    const data = {
      ...seedSnapshot,
      ...(res.data || {}),
      simulation_requirement: payload.simulation_requirement
    }
    await handleOntologyGenerated(data)
  } catch (err) {
    const message = err.message || '本体生成失败'
    addLog(`Ontology generation failed: ${message}`)
    handleOntologyFailed(message)
  }
}

const loadProject = async () => {
  try {
    loading.value = true
    addLog(`Loading project ${currentProjectId.value}...`)
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
      updatePhaseByStatus(res.data.status, res.data)
      addLog(`Project loaded. Status: ${res.data.status}`)
      if (res.data.status === 'ontology_generated' && !res.data.graph_id) {
        await startBuildGraph()
      } else if (res.data.status === 'graph_building' && res.data.graph_build_task_id) {
        currentPhase.value = 1
        startPollingTask(res.data.graph_build_task_id)
        startGraphPolling()
      } else if (res.data.status === 'graph_completed' && res.data.graph_id) {
        currentPhase.value = 2
        await loadGraph(res.data.graph_id)
      } else if (res.data.status === 'failed') {
        buildProgress.value = {
          ...(buildProgress.value || {}),
          status: 'failed',
          message: res.data.error || '图谱构建失败'
        }
        if (res.data.graph_id) await loadGraph(res.data.graph_id)
      }
      await loadSimulationHistory()
      await loadReportContext()
    } else {
      error.value = res.error
      addLog(`Error loading project: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in loadProject: ${err.message}`)
  } finally {
    loading.value = false
  }
}

const loadSimulationHistory = async () => {
  if (!currentProjectId.value || currentProjectId.value === 'new') {
    simulationHistory.value = []
    return
  }

  simulationHistoryLoading.value = true
  try {
    const res = await listSimulations(currentProjectId.value)
    if (res.success) {
      simulationHistory.value = (res.data || []).sort((a, b) => {
        const at = new Date(a.updated_at || a.created_at || 0).getTime()
        const bt = new Date(b.updated_at || b.created_at || 0).getTime()
        return bt - at
      })
      if (!currentSimulationId.value && simulationHistory.value.length > 0) {
        const reusable = simulationHistory.value.find(item =>
          ['ready', 'preparing', 'running', 'completed', 'stopped'].includes(item.status)
        ) || simulationHistory.value[0]
        currentSimulationId.value = reusable.simulation_id || ''
      }
    }
  } catch (err) {
    console.warn('加载推演历史失败:', err)
    simulationHistory.value = []
  } finally {
    simulationHistoryLoading.value = false
  }
}


const ensureProjectReadyForSimulation = async () => {
  if (!projectData.value?.graph_id && currentProjectId.value && currentProjectId.value !== 'new') {
    const res = await getProject(currentProjectId.value)
    if (res.success) projectData.value = res.data
    else throw new Error(res.error || '项目数据加载失败')
  }
  if (!projectData.value?.project_id) throw new Error('缺少 project_id，无法创建模拟实例')
  if (!projectData.value?.graph_id) throw new Error('项目尚未完成图谱构建，无法进入环境搭建')
}

const enterEnvironmentSetup = async () => {
  if (simulationCreating.value) return
  try {
    error.value = ''
    envSetupStatus.value = 'processing'
    await ensureProjectReadyForSimulation()
    if (!currentSimulationId.value) {
      simulationCreating.value = true
      addLog('正在创建模拟实例...')
      const res = await createSimulation({
        project_id: projectData.value.project_id,
        graph_id: projectData.value.graph_id,
        enable_twitter: true,
        enable_reddit: true
      })
      if (!res.success || !res.data?.simulation_id) throw new Error(res.error || '创建模拟实例失败')
      currentSimulationId.value = res.data.simulation_id
      await loadSimulationHistory()
      await loadReportContext()
      addLog(`模拟实例创建完成: ${currentSimulationId.value}`)
    }
    currentStep.value = 2
    addLog(`进入 Step 2: ${stepNames[1]}`)
  } catch (err) {
    error.value = err.message
    envSetupStatus.value = 'error'
    addLog(`进入环境搭建失败: ${err.message}`)
  } finally {
    simulationCreating.value = false
  }
}

const updatePhaseByStatus = (status, project = projectData.value || {}) => {
  if (status !== 'failed') error.value = ''
  switch (status) {
    case 'created': currentPhase.value = -1; break
    case 'ontology_generated': currentPhase.value = 0; break
    case 'graph_building': currentPhase.value = 1; break
    case 'graph_completed': currentPhase.value = 2; break
    case 'failed':
      currentPhase.value = project?.ontology || project?.graph_id ? 1 : -1
      error.value = project?.error || '项目处理失败'
      break
    default:
      if (project?.graph_id) currentPhase.value = 2
      else if (project?.ontology) currentPhase.value = 0
      else currentPhase.value = -1
  }
}


const startBuildGraph = async () => {
  try {
    currentPhase.value = 1
    buildProgress.value = { progress: 0, message: 'Starting build...' }
    addLog('Initiating graph build...')
    const res = await buildGraph({ project_id: currentProjectId.value })
    if (res.success) {
      addLog(`Graph build task started. Task ID: ${res.data.task_id}`)
      startGraphPolling()
      startPollingTask(res.data.task_id)
    } else {
      error.value = res.error
      addLog(`Error starting build: ${res.error}`)
    }
  } catch (err) {
    error.value = err.message
    addLog(`Exception in startBuildGraph: ${err.message}`)
  }
}

const startGraphPolling = () => {
  if (graphPollTimer) return
  fetchGraphData({ quiet: true })
  graphPollTimer = setInterval(async () => {
    await fetchGraphData({ quiet: true })
  }, GRAPH_BUILD_POLL_INTERVAL_MS)
}

const fetchGraphData = async (options = {}) => {
  try {
    const projRes = await getProject(currentProjectId.value)
    if (projRes.success && projRes.data.graph_id) {
      projectData.value = projRes.data
      const gRes = await getGraphData(projRes.data.graph_id)
      if (gRes.success) {
        graphData.value = gRes.data
        if (!options.quiet) {
          const nc = gRes.data.node_count || gRes.data.nodes?.length || 0
          const ec = gRes.data.edge_count || gRes.data.edges?.length || 0
          addLog(`Graph refreshed. Nodes: ${nc}, Edges: ${ec}`)
        }
      }
    }
  } catch (err) {
    console.warn('Graph fetch error:', err)
  }
}


const startPollingTask = (taskId) => {
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
  pollTaskStatus(taskId)
}

const pollTaskStatus = async (taskId) => {
  try {
    const res = await getTaskStatus(taskId)
    if (res.success) {
      const task = res.data
      if (task.message && task.message !== buildProgress.value?.message) addLog(task.message)
      buildProgress.value = { progress: task.progress || 0, message: task.message }
      if (task.status === 'completed') {
        addLog('Graph build task completed.')
        stopPolling()
        stopGraphPolling()
        currentPhase.value = 2
        const projRes = await getProject(currentProjectId.value)
        if (projRes.success && projRes.data.graph_id) {
          projectData.value = projRes.data
          await loadGraph(projRes.data.graph_id)
        }
      } else if (task.status === 'failed') {
        stopPolling()
        const message = task.error || task.message || '图谱构建失败'
        error.value = message
        currentPhase.value = 1
        buildProgress.value = {
          progress: task.progress || buildProgress.value?.progress || 0,
          message,
          status: 'failed',
          error: message
        }
        projectData.value = {
          ...(projectData.value || {}),
          status: 'failed',
          error: message
        }
        addLog(`Graph build task failed: ${message}`)
      }
    }
  } catch (e) {
    if (e?.status === 404 || e?.response?.status === 404 || /任务不存在/.test(e?.message || '')) {
      stopPolling()
      buildProgress.value = {
        progress: buildProgress.value?.progress || 0,
        message: '图谱构建任务记录不存在，请刷新项目状态或重新构建。'
      }
      addLog(`图谱构建任务不存在，已停止轮询: ${taskId}`)
      return
    }
    addLog(`查询图谱构建任务失败: ${e.message || '未知错误'}`)
  }
}

const loadGraph = async (graphId) => {
  graphLoading.value = true
  addLog(`Loading full graph data: ${graphId}`)
  try {
    const res = await getGraphData(graphId)
    if (res.success) { graphData.value = res.data; addLog('Graph data loaded successfully.') }
    else addLog(`Failed to load graph data: ${res.error}`)
  } catch (e) { addLog(`Exception loading graph: ${e.message}`) }
  finally { graphLoading.value = false }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) { addLog('Manual graph refresh.'); loadGraph(projectData.value.graph_id) }
}

const stopPolling = () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }
const stopGraphPolling = () => { if (graphPollTimer) { clearInterval(graphPollTimer); graphPollTimer = null } }

onMounted(() => { initProject() })

watch(() => route.params.projectId, (newId, oldId) => {
  if (newId && newId !== oldId) {
    currentProjectId.value = newId
    currentStep.value = 1
    currentPhase.value = -1
    projectData.value = null
    graphData.value = null
    currentSimulationId.value = ''
    currentReportId.value = ''
    simulationHistory.value = []
    ontologyProgress.value = null
    buildProgress.value = null
    systemLogs.value = []
    error.value = ''
    stopPolling()
    stopGraphPolling()
    initProject()
  }
})

onUnmounted(() => { stopPolling(); stopGraphPolling() })
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  background: #FFF;
}

/* 薄左侧图标栏 */
.icon-sidebar {
  width: 56px;
  min-width: 56px;
  background: #FAFAFA;
  border-right: 1px solid #EAEAEA;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  z-index: 200;
}

.icon-sidebar-top {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #6B7280;
  transition: all 0.15s;
}

.icon-btn:hover { background: #F0F0F0; color: #1A1A2E; }
.icon-btn.active { background: #EFF6FF; color: #1677FF; }

/* 历史面板 */
.history-panel {
  width: 0;
  min-width: 0;
  overflow: hidden;
  background: #FFF;
  border-right: 1px solid #EAEAEA;
  transition: width 0.25s ease, min-width 0.25s ease;
  display: none;
  flex-direction: column;
  z-index: 150;
  flex-shrink: 0;
}

.history-panel.visible {
  display: flex;
  width: 260px;
  min-width: 260px;
}

.history-panel-header {
  padding: 16px;
  border-bottom: 1px solid #EAEAEA;
}

.new-chat-btn {
  width: 100%;
  background: linear-gradient(135deg, #1677FF, #6366F1);
  color: #FFF;
  border: none;
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.new-chat-btn:hover { opacity: 0.88; }

.history-panel-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.history-section {
  padding-bottom: 12px;
}

.history-section + .history-section {
  border-top: 1px solid #F0F0F0;
  padding-top: 12px;
}

.history-section-title {
  padding: 6px 8px;
  color: #6B7280;
  font-size: 11px;
  font-weight: 700;
}

.history-empty {
  text-align: center;
  color: #9CA3AF;
  font-size: 13px;
  padding: 24px 16px;
}

.history-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-item:hover { background: #F3F4F6; }
.history-item.active { background: #EFF6FF; }

.history-item-row {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.history-item-title {
  font-size: 13px;
  color: #1A1A2E;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-item-date { font-size: 11px; color: #9CA3AF; }

.simulation-history-item .history-item-title {
  flex: 1;
}

.simulation-status {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 4px;
  background: #F3F4F6;
  color: #4B5563;
  font-size: 10px;
  font-weight: 700;
}

.simulation-status.running,
.simulation-status.preparing {
  background: #FFF7ED;
  color: #C2410C;
}

.simulation-status.ready,
.simulation-status.completed,
.simulation-status.stopped {
  background: #ECFDF5;
  color: #047857;
}

.simulation-status.failed {
  background: #FEF2F2;
  color: #B91C1C;
}

/* 主内容区 */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header 通用 */
.app-header {
  height: 56px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  flex-shrink: 0;
}

/* 首页 Header */
.landing-header .header-left { display: flex; align-items: center; }

.landing-header .brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 16px;
  color: #1A1A2E;
}

.landing-header .header-right {
  display: flex;
  align-items: center;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 20px;
  padding: 8px 20px;
  font-size: 13px;
  box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}

.pill-step {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #9CA3AF;
}

.pill-name { font-weight: 700; color: #1A1A2E; }
.pill-divider { color: #D1D5DB; }

.pill-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #FFAB91;
}

.pill-dot.processing { background: #FF5722; animation: pulse 1s infinite; }
.pill-dot.completed { background: #4CAF50; }
.pill-dot.error { background: #F44336; }

.pill-status { color: #6B7280; }

/* 二级页顶部流程栏 */
.workspace-topbar {
  height: 56px;
  border-bottom: 1px solid #EAEAEA;
  background: #FFF;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  padding: 0 24px;
  flex-shrink: 0;
  z-index: 110;
}

.back-brand-btn {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: none;
  background: transparent;
  color: #111827;
  font-size: 18px;
  font-weight: 800;
  cursor: pointer;
  padding: 8px 4px;
  transition: color 0.2s;
}

.back-brand-btn:hover {
  color: #1677FF;
}

.workflow-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-width: 0;
  white-space: nowrap;
}

.workflow-nav-item {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  color: #9CA3AF;
  font-size: 14px;
  font-weight: 700;
}

.workflow-nav-item.active {
  color: #1677FF;
  background: #EFF6FF;
  box-shadow: 0 8px 20px rgba(22, 119, 255, 0.12);
  border-radius: 999px;
  padding: 8px 18px;
}

.workflow-nav-item.completed {
  color: #4B5563;
}

.workflow-nav-arrow {
  color: #C7CDD8;
  font-weight: 500;
}

.topbar-actions {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 18px;
}

.topbar-icon-dot {
  width: 18px;
  height: 18px;
  border: 2px solid #111827;
  border-radius: 50%;
  position: relative;
}

.topbar-icon-dot::after {
  content: '';
  position: absolute;
  top: -5px;
  right: -5px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #EF4444;
}

.topbar-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563EB, #A5B4FC);
}

/* 二级页 Header */
.workspace-header {
  min-height: 56px;
  height: auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(180px, 1fr);
  column-gap: 18px;
  align-items: center;
  padding-top: 10px;
  padding-bottom: 10px;
}

.workspace-header .header-left {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

.event-title {
  font-size: 15px;
  font-weight: 700;
  color: #1A1A2E;
  line-height: 1.45;
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: normal;
}

.info-icon-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #9CA3AF;
  flex-shrink: 0;
  margin-top: -1px;
}

.workspace-header .header-center {
  justify-self: center;
  min-width: max-content;
}

.view-switcher {
  display: flex;
  background: #F5F5F5;
  padding: 3px;
  border-radius: 6px;
  gap: 2px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #666;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.switch-btn.active {
  background: #FFF;
  color: #000;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.workspace-header .header-right {
  display: flex;
  align-items: center;
  justify-self: end;
  gap: 10px;
  font-size: 13px;
  white-space: nowrap;
}

.step-badge {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #9CA3AF;
}

.step-label { font-weight: 600; color: #1A1A2E; }

.step-divider {
  width: 1px;
  height: 14px;
  background: #E5E7EB;
  margin: 0 4px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-dot.processing { background: #FF5722; animation: pulse 1s infinite; }
.status-dot.completed { background: #4CAF50; }
.status-dot.error { background: #F44336; }

.status-text { color: #6B7280; font-size: 12px; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* 首页内容区 */
.landing-content {
  flex: 1;
  overflow: hidden;
}

/* 二级页内容区 */
.workspace-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.3s ease, opacity 0.3s ease;
}

.panel-wrapper.left { border-right: 1px solid #EAEAEA; }

@media (max-width: 960px) {
  .workspace-topbar {
    grid-template-columns: 1fr;
    height: auto;
    gap: 10px;
    padding: 12px 16px;
  }

  .back-brand-btn,
  .topbar-actions {
    display: none;
  }

  .workflow-nav {
    overflow-x: auto;
    justify-content: flex-start;
  }

  .workspace-header {
    grid-template-columns: 1fr;
    gap: 10px;
    align-items: stretch;
    padding: 12px 16px;
  }

  .workspace-header .header-center {
    justify-self: start;
  }

  .workspace-header .header-right {
    justify-self: start;
    flex-wrap: wrap;
    white-space: normal;
  }
}
</style>
