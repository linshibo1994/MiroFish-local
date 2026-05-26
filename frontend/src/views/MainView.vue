<template>
  <div class="main-view">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="brand" @click="router.push('/')">NEWSPOWER</div>
      </div>
      
      <div class="header-center">
        <div class="view-switcher">
          <button 
            v-for="mode in ['graph', 'split', 'workbench']" 
            :key="mode"
            class="switch-btn"
            :class="{ active: viewMode === mode }"
            @click="viewMode = mode"
          >
            {{ { graph: '图谱', split: '双栏', workbench: '工作台' }[mode] }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">Step {{ currentStep }}/5</span>
          <span class="step-name">{{ stepNames[currentStep - 1] }}</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <!-- Main Content Area -->
    <main class="content-area">
      <!-- Left Panel: Graph -->
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <GraphPanel 
          :graphData="graphData"
          :loading="graphLoading"
          :currentPhase="currentPhase"
          @refresh="refreshGraph"
          @toggle-maximize="toggleMaximize('graph')"
        />
      </div>

      <!-- Right Panel: Step Components -->
      <div class="panel-wrapper right" :style="rightPanelStyle">
        <!-- Step 1: 图谱构建 -->
        <Step1GraphBuild 
          v-if="currentStep === 1"
          :currentPhase="currentPhase"
          :projectData="projectData"
          :pendingUpload="pendingUploadState"
          :ontologyProgress="ontologyProgress"
          :buildProgress="buildProgress"
          :graphData="graphData"
          :systemLogs="systemLogs"
          @ontology-generated="handleOntologyGenerated"
          @add-log="addLog"
          @next-step="handleNextStep"
        />
        <!-- Step 2: 环境搭建 -->
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
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import Step1GraphBuild from '../components/Step1GraphBuild.vue'
import Step2EnvSetup from '../components/Step2EnvSetup.vue'
import { getProject, buildGraph, getTaskStatus, getGraphData } from '../api/graph'
import { createSimulation } from '../api/simulation'
import { getPendingUpload, clearPendingUpload } from '../store/pendingUpload'

const route = useRoute()
const router = useRouter()

// Layout State
const viewMode = ref('split') // graph | split | workbench

// Step State
const currentStep = ref(1) // 1: 图谱构建, 2: 环境搭建, 3: 开始模拟, 4: 报告生成, 5: 深度互动
const stepNames = ['图谱构建', '环境搭建', '开始模拟', '报告生成', '深度互动']

// Data State
const currentProjectId = ref(route.params.projectId)
const loading = ref(false)
const graphLoading = ref(false)
const error = ref('')
const projectData = ref(null)
const graphData = ref(null)
const currentSimulationId = ref('')
const currentPhase = ref(-1) // -1: Upload, 0: Ontology, 1: Build, 2: Complete
const ontologyProgress = ref(null)
const buildProgress = ref(null)
const systemLogs = ref([])
const pendingUploadState = ref(null)
const simulationCreating = ref(false)
const envSetupStatus = ref('processing') // processing | completed | error

// Polling timers
let pollTimer = null
let graphPollTimer = null
let graphPollCount = 0
const GRAPH_BUILD_POLL_INTERVAL_MS = 60000
const GRAPH_BUILD_MAX_POLL_COUNT = 3

// --- Computed Layout Styles ---
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(20px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})

// --- Status Computed ---
const statusClass = computed(() => {
  if (error.value) return 'error'
  if (simulationCreating.value) return 'processing'
  if (currentStep.value === 2) return envSetupStatus.value
  if (currentPhase.value >= 2) return 'completed'
  return 'processing'
})

const statusText = computed(() => {
  if (error.value) return '错误'
  if (simulationCreating.value) return '创建模拟实例'
  if (currentStep.value === 2) {
    if (envSetupStatus.value === 'error') return '错误'
    if (envSetupStatus.value === 'completed') return '就绪'
    return '准备中'
  }
  if (currentPhase.value >= 2) return '就绪'
  if (currentPhase.value === 1) return '图谱构建中'
  if (currentPhase.value === 0) return '本体生成中'
  return '等待输入'
})

// --- Helpers ---
const addLog = (msg) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }) + '.' + new Date().getMilliseconds().toString().padStart(3, '0')
  systemLogs.value.push({ time, msg })
  // Keep last 100 logs
  if (systemLogs.value.length > 100) {
    systemLogs.value.shift()
  }
}

// --- Layout Methods ---
const toggleMaximize = (target) => {
  if (viewMode.value === target) {
    viewMode.value = 'split'
  } else {
    viewMode.value = target
  }
}

const handleNextStep = (params = {}) => {
  if (currentStep.value === 1) {
    enterEnvironmentSetup()
    return
  }

  if (currentStep.value === 2) {
    addLog('进入 Step 3: 开始模拟')

    if (params.maxRounds) {
      addLog(`自定义模拟轮数: ${params.maxRounds} 轮`)
    } else {
      addLog('使用自动配置的模拟轮数')
    }

    const routeParams = {
      name: 'SimulationRun',
      params: { simulationId: currentSimulationId.value }
    }

    if (params.maxRounds) {
      routeParams.query = { maxRounds: params.maxRounds }
    }

    router.push(routeParams)
    return
  }

  if (currentStep.value < 5) {
    currentStep.value++
    addLog(`进入 Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

const updateEnvStatus = (status) => {
  envSetupStatus.value = status || 'processing'
}

const handleSimulationCreated = (simulationId) => {
  currentSimulationId.value = simulationId || ''
  if (currentSimulationId.value) {
    addLog(`模拟实例同步完成: ${currentSimulationId.value}`)
  }
}

const handleGoBack = () => {
  if (currentStep.value > 1) {
    currentStep.value--
    addLog(`返回 Step ${currentStep.value}: ${stepNames[currentStep.value - 1]}`)
  }
}

// --- Data Logic ---

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

  router.replace({ name: 'Process', params: { projectId: data.project_id } })
  addLog(`Ontology generated successfully for project ${data.project_id}`)
  await startBuildGraph()
}

const loadProject = async () => {
  try {
    loading.value = true
    addLog(`Loading project ${currentProjectId.value}...`)
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
      updatePhaseByStatus(res.data.status)
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
      }
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

const ensureProjectReadyForSimulation = async () => {
  if (!projectData.value?.graph_id && currentProjectId.value && currentProjectId.value !== 'new') {
    const res = await getProject(currentProjectId.value)
    if (res.success) {
      projectData.value = res.data
    } else {
      throw new Error(res.error || '项目数据加载失败')
    }
  }

  if (!projectData.value?.project_id) {
    throw new Error('缺少 project_id，无法创建模拟实例')
  }

  if (!projectData.value?.graph_id) {
    throw new Error('项目尚未完成图谱构建，无法进入环境搭建')
  }
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

      if (!res.success || !res.data?.simulation_id) {
        throw new Error(res.error || '创建模拟实例失败')
      }

      currentSimulationId.value = res.data.simulation_id
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

const updatePhaseByStatus = (status) => {
  switch (status) {
    case 'created':
      currentPhase.value = -1; break;
    case 'ontology_generated': currentPhase.value = 0; break;
    case 'graph_building': currentPhase.value = 1; break;
    case 'graph_completed': currentPhase.value = 2; break;
    case 'failed': error.value = 'Project failed'; break;
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
  graphPollCount = 0
  addLog('图谱构建中，降低全量图谱刷新频率以减少后端压力。')
  graphPollTimer = setInterval(async () => {
    graphPollCount += 1
    await fetchGraphData({ skipBuilding: true, quiet: true })
    if (graphPollCount >= GRAPH_BUILD_MAX_POLL_COUNT) {
      stopGraphPolling()
      addLog('构建阶段全量图谱低频刷新已暂停，完成后会自动加载最终图谱。')
    }
  }, GRAPH_BUILD_POLL_INTERVAL_MS)
}

const fetchGraphData = async (options = {}) => {
  try {
    // Refresh project info to check for graph_id
    const projRes = await getProject(currentProjectId.value)
    if (projRes.success && projRes.data.graph_id) {
      projectData.value = projRes.data
      if (options.skipBuilding && projRes.data.status === 'graph_building') {
        return
      }
      const gRes = await getGraphData(projRes.data.graph_id)
      if (gRes.success) {
        graphData.value = gRes.data
        const nodeCount = gRes.data.node_count || gRes.data.nodes?.length || 0
        const edgeCount = gRes.data.edge_count || gRes.data.edges?.length || 0
        if (!options.quiet) {
          addLog(`Graph data refreshed. Nodes: ${nodeCount}, Edges: ${edgeCount}`)
        }
      }
    }
  } catch (err) {
    console.warn('Graph fetch error:', err)
  }
}

const startPollingTask = (taskId) => {
  pollTaskStatus(taskId)
  pollTimer = setInterval(() => pollTaskStatus(taskId), 2000)
}

const pollTaskStatus = async (taskId) => {
  try {
    const res = await getTaskStatus(taskId)
    if (res.success) {
      const task = res.data
      
      // Log progress message if it changed
      if (task.message && task.message !== buildProgress.value?.message) {
        addLog(task.message)
      }
      
      buildProgress.value = { progress: task.progress || 0, message: task.message }
      
      if (task.status === 'completed') {
        addLog('Graph build task completed.')
        stopPolling()
        stopGraphPolling() // Stop polling, do final load
        currentPhase.value = 2
        
        // Final load
        const projRes = await getProject(currentProjectId.value)
        if (projRes.success && projRes.data.graph_id) {
            projectData.value = projRes.data
            await loadGraph(projRes.data.graph_id)
        }
      } else if (task.status === 'failed') {
        stopPolling()
        error.value = task.error
        addLog(`Graph build task failed: ${task.error}`)
      }
    }
  } catch (e) {
    console.error(e)
  }
}

const loadGraph = async (graphId) => {
  graphLoading.value = true
  addLog(`Loading full graph data: ${graphId}`)
  try {
    const res = await getGraphData(graphId)
    if (res.success) {
      graphData.value = res.data
      addLog('Graph data loaded successfully.')
    } else {
      addLog(`Failed to load graph data: ${res.error}`)
    }
  } catch (e) {
    addLog(`Exception loading graph: ${e.message}`)
  } finally {
    graphLoading.value = false
  }
}

const refreshGraph = () => {
  if (projectData.value?.graph_id) {
    addLog('Manual graph refresh triggered.')
    loadGraph(projectData.value.graph_id)
  }
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const stopGraphPolling = () => {
  if (graphPollTimer) {
    clearInterval(graphPollTimer)
    graphPollTimer = null
    addLog('Graph polling stopped.')
  }
  graphPollCount = 0
}

onMounted(() => {
  initProject()
})

onUnmounted(() => {
  stopPolling()
  stopGraphPolling()
})
</script>

<style scoped>
.main-view {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #FFF;
  overflow: hidden;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
}

/* Header */
.app-header {
  height: 60px;
  border-bottom: 1px solid #EAEAEA;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #FFF;
  z-index: 100;
  position: relative;
}

.header-center {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
}

.brand {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 800;
  font-size: 18px;
  letter-spacing: 1px;
  cursor: pointer;
}

.view-switcher {
  display: flex;
  background: #F5F5F5;
  padding: 4px;
  border-radius: 6px;
  gap: 4px;
}

.switch-btn {
  border: none;
  background: transparent;
  padding: 6px 16px;
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
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.workflow-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.step-num {
  font-family: 'JetBrains Mono', monospace;
  font-weight: 700;
  color: #999;
}

.step-name {
  font-weight: 700;
  color: #000;
}

.step-divider {
  width: 1px;
  height: 14px;
  background-color: #E0E0E0;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #CCC;
}

.status-indicator.processing .dot { background: #FF5722; animation: pulse 1s infinite; }
.status-indicator.completed .dot { background: #4CAF50; }
.status-indicator.error .dot { background: #F44336; }

@keyframes pulse { 50% { opacity: 0.5; } }

/* Content */
.content-area {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

.panel-wrapper {
  height: 100%;
  overflow: hidden;
  transition: width 0.4s cubic-bezier(0.25, 0.8, 0.25, 1), opacity 0.3s ease, transform 0.3s ease;
  will-change: width, opacity, transform;
}

.panel-wrapper.left {
  border-right: 1px solid #EAEAEA;
}
</style>
