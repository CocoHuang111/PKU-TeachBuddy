/**
 * 问答状态放在页面组件外面：切到评估 / 大纲、或换另一个会话时，SSE 继续跑。
 * 后端会在提问当下落库；刷新后若仍在生成，则轮询直到完成。
 * 多个会话可以同时生成，发送按钮只锁当前正在思考的那一个。
 */
import { computed, nextTick, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { qaApi, evaluationApi } from './api/client'
import { askStream } from './api/stream'

const SESSION_KEY = 'pku-askedu-qa-session'
const POLL_MS = 1500

export const sessions = ref([])
export const sessionId = ref(null)
export const messages = ref([])
export const qaModes = ref([])
export const selectedMode = ref('ask')
export const corpora = ref([])
export const selectedCorpora = ref([])
export const evalReports = ref([])
export const selectedEvalTaskIds = ref([])
export const selectedAttachments = ref([])
export const uploadingAttachments = ref(false)
export const attachmentUploadProgress = ref(0)
export const input = ref('')
export const sidebarOpen = ref(true)
export const sessionQuery = ref('')

let ownerId = null
let scrollHook = null
let pollTimer = null
let openSessionRequest = 0
const jobs = ref([])
const pollingId = ref(null)

export const sending = computed(() => {
  if (sessionId.value) {
    if (jobs.value.some((j) => j.sending && j.sessionId === sessionId.value)) return true
    return pollingId.value === sessionId.value
  }
  return jobs.value.some((j) => j.sending && !j.sessionId && j.messages === messages.value)
})

export function setQaScroll(fn) {
  scrollHook = fn
}

export function resetQa() {
  openSessionRequest += 1
  stopPoll()
  ownerId = null
  jobs.value = []
  pollingId.value = null
  sessions.value = []
  sessionId.value = null
  messages.value = []
  qaModes.value = []
  selectedMode.value = 'ask'
  corpora.value = []
  selectedCorpora.value = []
  evalReports.value = []
  selectedEvalTaskIds.value = []
  selectedAttachments.value = []
  uploadingAttachments.value = false
  attachmentUploadProgress.value = 0
  input.value = ''
  sessionQuery.value = ''
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
}

function persistSessionId(id) {
  try {
    if (id) sessionStorage.setItem(SESSION_KEY, id)
    else sessionStorage.removeItem(SESSION_KEY)
  } catch {
    /* ignore */
  }
}

function readSavedSessionId() {
  try {
    return sessionStorage.getItem(SESSION_KEY)
  } catch {
    return null
  }
}

function ensureQaOwner(userId) {
  if (ownerId === userId) return
  if (ownerId !== null) resetQa()
  ownerId = userId
}

async function scrollDown() {
  await nextTick()
  scrollHook?.()
}

function hydrateMessages(history) {
  return (history || []).map((m) => {
    const pending = !!m.pending
    return {
      ...m,
      mode: m.mode || m.plan?.mode || 'ask',
      streaming: pending,
      thinking: pending && !m.content,
    }
  })
}

function stopPoll() {
  clearTimeout(pollTimer)
  pollTimer = null
}

function markListPending(id, pending) {
  const item = sessions.value.find((s) => s.id === id)
  if (item) item.pending = pending
}

export const currentTitle = computed(() => {
  if (!sessionId.value) return '新对话'
  return sessions.value.find((s) => s.id === sessionId.value)?.title || '对话'
})

export const currentPinned = computed(() => {
  return !!sessions.value.find((s) => s.id === sessionId.value)?.pinned
})

export const currentMode = computed(() =>
  qaModes.value.find((m) => m.name === selectedMode.value) || {
    name: 'ask',
    label: '通用问答',
    description: '解释教学问题，并给出有依据的可执行建议',
    placeholder: '问任何教学相关的问题',
    default_corpora: [],
    starter_questions: [],
  }
)

export function modeLabel(name) {
  return qaModes.value.find((m) => m.name === name)?.label || '通用问答'
}

export const visibleGroups = computed(() => {
  const q = sessionQuery.value.trim().toLowerCase()
  const filtered = sessions.value.filter((s) => {
    if (q && !(s.title || '').toLowerCase().includes(q)) return false
    return true
  })
  const pinned = filtered.filter((s) => s.pinned)
  const recent = filtered.filter((s) => !s.pinned)
  return [
    { key: 'pinned', label: '置顶', items: pinned },
    { key: 'recent', label: '最近', items: recent },
  ].filter((g) => g.items.length)
})

export const selectableNames = computed(() =>
  corpora.value.filter((c) => c.count && c.name !== 'eval_reports').map((c) => c.name)
)

export const evalCorpus = computed(() => corpora.value.find((c) => c.name === 'eval_reports'))

export const staticCorpora = computed(() =>
  corpora.value.filter((c) => c.name !== 'eval_reports')
)

export const staticSelectedCorpora = computed({
  get() {
    return selectedCorpora.value.filter((n) => n !== 'eval_reports')
  },
  set(names) {
    const next = Array.isArray(names) ? names : []
    selectedCorpora.value = selectedEvalTaskIds.value.length
      ? [...next, 'eval_reports']
      : next
  },
})

export const corporaNarrowed = computed(() => {
  const all = selectableNames.value
  const staticSelected = selectedCorpora.value.filter((n) => n !== 'eval_reports')
  const staticNotAll =
    all.length > 0 &&
    (all.length !== staticSelected.length || all.some((n) => !staticSelected.includes(n)))
  const hasEval = selectedEvalTaskIds.value.length > 0
  return staticNotAll || hasEval
})

export function corpusLabel(name) {
  return corpora.value.find((c) => c.name === name)?.label || name
}

export async function loadSessions() {
  try {
    sessions.value = await qaApi.sessions()
    for (const job of jobs.value) {
      if (job.sending && job.sessionId) markListPending(job.sessionId, true)
    }
  } catch {
    /* 拦截器已提示 */
  }
}

export async function loadModes() {
  try {
    qaModes.value = await qaApi.modes()
    if (!qaModes.value.some((m) => m.name === selectedMode.value)) {
      selectedMode.value = qaModes.value[0]?.name || 'ask'
    }
  } catch {
    /* 拦截器已提示 */
  }
}

function applyModeCorpora() {
  const available = new Set(selectableNames.value)
  const defaults = (currentMode.value.default_corpora || []).filter((name) =>
    available.has(name)
  )
  const selected = defaults.length ? defaults : [...selectableNames.value]
  selectedCorpora.value = selectedEvalTaskIds.value.length
    ? [...selected, 'eval_reports']
    : selected
}

export function setMode(name, { resetCorpora = true } = {}) {
  if (!qaModes.value.some((m) => m.name === name)) name = 'ask'
  selectedMode.value = name
  if (resetCorpora) applyModeCorpora()
}

export async function loadCorpora() {
  try {
    corpora.value = await qaApi.corpora()
    if (!selectedCorpora.value.length) {
      applyModeCorpora()
    }
  } catch {
    /* 拦截器已提示 */
  }
}

export async function loadEvalReports() {
  try {
    const tasks = await evaluationApi.listTasks({ status: 'completed', limit: 200 })
    const ids = new Set(tasks.map((t) => t.id))
    evalReports.value = tasks
    selectedEvalTaskIds.value = selectedEvalTaskIds.value.filter((id) => ids.has(id))
    syncEvalCorpusSelection()
  } catch {
    /* 拦截器已提示 */
  }
}

export function applyEvalTaskSelection(ids) {
  const allowed = new Set(evalReports.value.map((t) => t.id))
  selectedEvalTaskIds.value = ids.filter((id) => allowed.has(id))
  syncEvalCorpusSelection()
}

function syncEvalCorpusSelection() {
  const has = selectedEvalTaskIds.value.length > 0
  const selected = selectedCorpora.value.filter((n) => n !== 'eval_reports')
  selectedCorpora.value = has ? [...selected, 'eval_reports'] : selected
}

export function evalReportLabel(task) {
  const name = task.filename || '未命名视频'
  const score = task.summary?.score
  const scoreText = Number.isFinite(score) ? `${Math.round(score)}分` : ''
  return scoreText ? `${name}（${scoreText}）` : name
}

export function evalReportTime(task) {
  if (!task.created_at) return ''
  return new Date(task.created_at * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function newSession() {
  openSessionRequest += 1
  stopPoll()
  pollingId.value = null
  sessionId.value = null
  messages.value = []
  selectedAttachments.value = []
  setMode('ask')
  persistSessionId(null)
}

function jobForSession(id, msgs) {
  if (id) return jobs.value.find((j) => j.sessionId === id)
  return jobs.value.find((j) => !j.sessionId && j.messages === msgs)
}

export async function openSession(id) {
  const requestId = ++openSessionRequest
  // Historical attachments belong to their message; switching sessions must
  // not silently reattach them to the composer.
  selectedAttachments.value = []
  const liveJob = jobForSession(id)
  if (liveJob) {
    sessionId.value = id
    messages.value = liveJob.messages
    setMode(liveJob.mode || 'ask')
    persistSessionId(id)
    stopPoll()
    pollingId.value = null
    scrollDown()
    return
  }
  try {
    const s = await qaApi.getSession(id)
    if (requestId !== openSessionRequest) return
    sessionId.value = id
    messages.value = hydrateMessages(s.history)
    const lastMode = [...messages.value].reverse().find((m) => m.mode)?.mode || 'ask'
    setMode(lastMode)
    persistSessionId(id)
    scrollDown()
    const last = messages.value[messages.value.length - 1]
    if (last?.pending) {
      pollPending(id)
    } else {
      stopPoll()
      if (pollingId.value === id) pollingId.value = null
    }
  } catch {
    /* 拦截器已提示 */
  }
}

async function pollPending(id) {
  stopPoll()
  pollingId.value = id
  const tick = async () => {
    if (sessionId.value !== id) return
    if (jobForSession(id)) return
    try {
      const s = await qaApi.getSession(id)
      const hist = s.history || []
      const last = hist[hist.length - 1]
      messages.value = hydrateMessages(hist)
      if (!last?.pending) {
        if (pollingId.value === id) pollingId.value = null
        markListPending(id, false)
        await loadSessions()
        await scrollDown()
        return
      }
      await scrollDown()
    } catch {
      /* 下一轮再试 */
    }
    pollTimer = setTimeout(tick, POLL_MS)
  }
  pollTimer = setTimeout(tick, 400)
}

export async function removeSession(id) {
  try {
    await ElMessageBox.confirm('确定删除这个会话？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await qaApi.deleteSession(id)
  jobs.value = jobs.value.filter((j) => j.sessionId !== id)
  if (pollingId.value === id) pollingId.value = null
  if (sessionId.value === id) newSession()
  loadSessions()
}

export async function renameSession(id) {
  const current = sessions.value.find((s) => s.id === id)?.title || ''
  let name
  try {
    const { value } = await ElMessageBox.prompt('请输入新的会话名称', '重命名', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: current,
      inputPattern: /\S/,
      inputErrorMessage: '名称不能为空',
    })
    name = (value || '').trim()
  } catch {
    return
  }
  if (!name) return
  await qaApi.patchSession(id, { title: name.slice(0, 80) })
  await loadSessions()
}

export async function togglePin(id, pinned) {
  await qaApi.patchSession(id, { pinned })
  await loadSessions()
}

export function onSessionCommand(s, cmd) {
  if (cmd === 'rename') renameSession(s.id)
  else if (cmd === 'pin') togglePin(s.id, !s.pinned)
  else if (cmd === 'delete') removeSession(s.id)
}

export function onCurrentCommand(cmd) {
  const s = sessions.value.find((item) => item.id === sessionId.value)
  if (!s) return
  onSessionCommand(s, cmd)
}

export function useSample(q) {
  input.value = q
}

function isPendingAttachment(item) {
  return !item || item.status === 'uploading' || String(item.id || '').startsWith('pending-')
}

function isFileAttachment(item) {
  return item && item.kind !== 'eval_report'
}

function fileAttachments(items) {
  return (items || []).filter(isFileAttachment)
}

function evalReportAttachments() {
  return selectedEvalTaskIds.value.flatMap((id) => {
    const task = evalReports.value.find((item) => item.id === id)
    if (!task) return []
    return [{
      id: `eval:${id}`,
      name: evalReportLabel(task),
      size: 0,
      kind: 'eval_report',
      meta: evalReportTime(task) || '历史评估报告',
      warnings: [],
    }]
  })
}

export async function uploadAttachments(files) {
  const pending = Array.from(files || [])
  if (!pending.length || uploadingAttachments.value) return
  if (selectedAttachments.value.length + pending.length > 8) {
    ElMessage.warning('一次最多选择 8 个文件')
    return
  }
  const placeholders = pending.map((file, index) => ({
    id: `pending-${Date.now()}-${index}`,
    name: file.name,
    suffix: `.${String(file.name).split('.').pop() || ''}`.toLowerCase(),
    size: file.size || 0,
    status: 'uploading',
    preview: '',
    warnings: [],
  }))
  selectedAttachments.value = [...selectedAttachments.value, ...placeholders]
  uploadingAttachments.value = true
  attachmentUploadProgress.value = 0
  try {
    const result = await qaApi.uploadAttachments(pending, (progress) => {
      attachmentUploadProgress.value = progress
    })
    const existing = new Set(
      selectedAttachments.value.filter((item) => !isPendingAttachment(item)).map((item) => item.id)
    )
    selectedAttachments.value = [
      ...selectedAttachments.value.filter((item) => !isPendingAttachment(item)),
      ...(result.attachments || []).filter((item) => !existing.has(item.id)),
    ]
    for (const error of result.errors || []) {
      ElMessage.warning(`${error.name}：${error.message}`)
    }
    if (result.attachments?.length) {
      ElMessage.success(`已添加 ${result.attachments.length} 个文件`)
    }
  } catch {
    selectedAttachments.value = selectedAttachments.value.filter((item) => !isPendingAttachment(item))
  } finally {
    uploadingAttachments.value = false
    attachmentUploadProgress.value = 0
  }
}

export async function removeAttachment(item) {
  selectedAttachments.value = selectedAttachments.value.filter((a) => a.id !== item.id)
  if (isPendingAttachment(item)) return
  try {
    await qaApi.deleteAttachment(item.id)
  } catch {
    // 已从当前问题移除；服务端不存在或删除失败由拦截器提示。
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function createLineRevealer(reply, job) {
  let committed = ''
  let pending = ''
  const queue = []
  let running = false

  function viewing() {
    return messages.value === job.messages
  }

  function paint() {
    reply.content = committed + pending
    reply.thinking = !reply.content
    if (viewing()) scrollDown()
  }

  async function run() {
    if (running) return
    running = true
    while (queue.length) {
      committed += queue.shift()
      paint()
      if (queue.length) await sleep(queue.length > 12 ? 16 : 40)
    }
    running = false
  }

  return {
    push(text) {
      pending += text
      const parts = pending.split('\n')
      pending = parts.pop() ?? ''
      if (parts.length) {
        for (const line of parts) queue.push(`${line}\n`)
        run()
      }
      paint()
    },
    async flush() {
      if (pending) {
        queue.push(pending)
        pending = ''
      }
      while (queue.length || running) {
        await run()
        if (!queue.length) break
        await sleep(8)
      }
      paint()
    },
  }
}

export async function send() {
  const question = input.value.trim()
  if (!question || sending.value || uploadingAttachments.value) return

  // The attached evaluation reports apply to this question only. Snapshot them
  // before resetting the composer so the next question returns to the current
  // mode's recommended knowledge-base selection.
  const corporaForRequest = [...selectedCorpora.value]
  const modeForRequest = selectedMode.value
  const evalTaskIdsForRequest = corporaForRequest.includes('eval_reports')
    ? [...selectedEvalTaskIds.value]
    : null
  const attachmentsForRequest = fileAttachments(selectedAttachments.value).map((item) => ({ ...item }))
  const visibleAttachments = [...attachmentsForRequest, ...evalReportAttachments()]
  applyEvalTaskSelection([])
  applyModeCorpora()

  stopPoll()
  pollingId.value = null
  input.value = ''
  const thread = messages.value
  thread.push({
    role: 'user',
    content: question,
    mode: modeForRequest,
    attachments: visibleAttachments,
  })

  const reply = {
    role: 'assistant',
    mode: modeForRequest,
    content: '',
    citations: [],
    plan: null,
    streaming: true,
    thinking: true,
    pending: true,
  }
  thread.push(reply)

  const job = {
    sessionId: sessionId.value,
    messages: thread,
    sending: true,
    mode: modeForRequest,
    attachments: attachmentsForRequest,
  }
  jobs.value = [...jobs.value, job]
  const reveal = createLineRevealer(reply, job)
  scrollDown()

  try {
    await askStream(
      {
        question,
        mode: modeForRequest,
        sessionId: job.sessionId,
        corpora: corporaForRequest,
        evalTaskIds: evalTaskIdsForRequest,
        attachmentIds: attachmentsForRequest.map((item) => item.id),
      },
      (event) => {
        if (event.type === 'plan') reply.plan = event.data
        else if (event.type === 'citations') reply.citations = event.data
        else if (event.type === 'chunk') reveal.push(event.data)
        else if (event.type === 'session') {
          job.sessionId = event.session_id
          jobs.value = [...jobs.value]
          if (messages.value === job.messages) {
            sessionId.value = event.session_id
            persistSessionId(event.session_id)
          }
          markListPending(event.session_id, true)
          loadSessions()
        } else if (event.type === 'error') {
          ElMessage.error(event.data)
        }
      }
    )
    await reveal.flush()
  } catch (e) {
    await reveal.flush()
    reply.content += `\n\n（请求失败：${e.message}）`
    ElMessage.error(e.message)
  } finally {
    reply.thinking = false
    reply.streaming = false
    reply.pending = false
    job.sending = false
    jobs.value = jobs.value.filter((j) => j !== job)
    if (job.sessionId) markListPending(job.sessionId, false)
    loadSessions()
    if (messages.value === job.messages) scrollDown()
  }
}

export async function initQa(userId) {
  ensureQaOwner(userId)
  if (!qaModes.value.length) await loadModes()
  if (!corpora.value.length) await loadCorpora()
  await loadEvalReports()
  await loadSessions()
  if (jobs.value.some((j) => j.sending) || messages.value.length) return
  const saved = readSavedSessionId()
  if (saved && sessions.value.some((s) => s.id === saved)) {
    await openSession(saved)
    return
  }
  const pending = sessions.value.find((s) => s.pending)
  if (pending) await openSession(pending.id)
}

export async function onQaActivated() {
  await loadModes()
  await loadCorpora()
  await loadEvalReports()
  await loadSessions()
  await scrollDown()
}
