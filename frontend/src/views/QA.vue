<template>
  <div class="qa">
    <aside class="sidebar" :class="{ open: sidebarOpen }">
      <div class="sidebar-inner">
        <div class="drawer-head">
          <span class="drawer-title">历史会话</span>
          <button class="icon-btn" type="button" title="收起" @click="sidebarOpen = false">
            <el-icon :size="18"><DArrowLeft /></el-icon>
          </button>
        </div>
        <div class="drawer-tools">
          <el-input
            v-model="sessionQuery"
            placeholder="搜索历史会话"
            :prefix-icon="Search"
            clearable
          />
          <button class="new-eval-btn" type="button" @click="newSession">
            <el-icon :size="16"><Plus /></el-icon>
            新对话
          </button>
        </div>
        <div class="task-list">
          <div v-if="!sessions.length" class="empty-hint">还没有会话</div>
          <div v-else-if="!visibleGroups.length" class="empty-hint">没有匹配的会话</div>
          <section v-for="group in visibleGroups" :key="group.key" class="task-group">
            <div class="group-label">{{ group.label }}</div>
            <div
              v-for="s in group.items"
              :key="s.id"
              class="task"
              :class="{ active: s.id === sessionId, pinned: s.pinned, pending: s.pending }"
              @click="openSession(s.id)"
            >
              <el-icon class="task-icon" :size="18"><ChatDotRound /></el-icon>
              <div class="task-body">
                <div class="task-name">{{ s.title }}</div>
                <div v-if="s.pending" class="task-run">思考中</div>
                <div v-else class="task-status-row">
                  <span class="task-time">{{ formatTime(s.updated_at) }}</span>
                </div>
              </div>
              <el-dropdown
                trigger="click"
                @command="(cmd) => onSessionCommand(s, cmd)"
                @click.stop
              >
                <button class="more-btn" type="button" title="更多" @click.stop>
                  <el-icon :size="16"><MoreFilled /></el-icon>
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="rename">重命名</el-dropdown-item>
                    <el-dropdown-item command="pin">
                      {{ s.pinned ? '取消置顶' : '置顶' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </section>
        </div>
      </div>
    </aside>

    <div class="stage">
      <header class="chat-top">
        <div class="top-left">
          <template v-if="!sidebarOpen">
            <button
              class="icon-btn"
              type="button"
              title="历史会话"
              @click="sidebarOpen = true"
            >
              <el-icon :size="20"><ChatLineRound /></el-icon>
            </button>
            <button class="icon-btn" type="button" title="新对话" @click="newSession">
              <el-icon :size="20"><Plus /></el-icon>
            </button>
          </template>
        </div>
        <div class="top-heading">
          <div class="top-title">{{ currentTitle }}</div>
          <el-dropdown
            v-if="sessionId"
            trigger="click"
            @command="(cmd) => onCurrentCommand(cmd)"
          >
            <button class="more-btn header-more" type="button" title="更多">
              <el-icon :size="16"><MoreFilled /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="rename">重命名</el-dropdown-item>
                <el-dropdown-item command="pin">
                  {{ currentPinned ? '取消置顶' : '置顶' }}
                </el-dropdown-item>
                <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <section class="chat">
        <div ref="bodyEl" class="chat-body">
          <div v-if="!messages.length" class="chat-empty">
            <h1>{{ currentMode.label }}</h1>
            <p>{{ currentMode.description }}</p>
            <div class="samples">
              <button
                v-for="q in currentMode.starter_questions"
                :key="q"
                type="button"
                class="sample"
                @click="useSample(q)"
              >
                {{ q }}
              </button>
            </div>
          </div>

          <div v-else class="thread">
            <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
              <div v-if="m.role === 'user'" class="user-message">
                <div v-if="m.attachments?.length" class="message-attachments">
                  <span v-for="file in m.attachments" :key="file.id" class="message-attachment">
                    <el-icon><Document /></el-icon>{{ file.name }}
                  </span>
                </div>
                <div class="bubble user">{{ m.content }}</div>
              </div>
              <div v-else class="assistant">
                <div v-if="m.plan" class="plan">
                  <span class="mode-badge">{{ m.plan.mode_label || modeLabel(m.mode) }}</span>
                  <span class="plan-label">检索</span>
                  <el-tag v-for="q in m.plan.queries" :key="q" size="small" effect="plain">
                    {{ q }}
                  </el-tag>
                  <el-tag
                    v-for="c in m.plan.corpora"
                    :key="c"
                    size="small"
                    :type="c === 'eval_reports' && m.plan.pinned_eval_reports ? 'danger' : 'info'"
                    effect="plain"
                  >
                    {{ corpusLabel(c) }}
                    <template v-if="c === 'eval_reports' && m.plan.pinned_eval_reports">
                      ·已带入{{ m.plan.pinned_eval_reports }}份
                    </template>
                  </el-tag>
                </div>
                <div v-if="m.plan?.matched_cases?.length" class="matched-cases">
                  <span class="matched-label">匹配课程</span>
                  <a
                    v-for="course in m.plan.matched_cases"
                    :key="course.source"
                    :href="course.source_url || undefined"
                    :target="course.source_url ? '_blank' : undefined"
                    :rel="course.source_url ? 'noopener noreferrer' : undefined"
                    class="matched-course"
                  >
                    {{ course.source }}
                  </a>
                </div>

                <div v-if="m.content" class="markdown" v-html="renderMd(m.content)"></div>
                <span v-if="m.streaming" class="stream-status">
                  <span v-if="m.thinking" class="thinking">思考中<span class="dots"></span></span>
                  <span class="cursor">▋</span>
                </span>

                <el-collapse v-if="m.citations?.length" class="citations">
                  <el-collapse-item :title="`来源（${m.citations.length}）`" name="c">
                    <div v-for="c in m.citations" :key="c.index" class="citation">
                      <div class="citation-head">
                        <el-tag size="small" effect="plain">[{{ c.index }}]</el-tag>
                        <span class="citation-corpus">{{ c.corpus_label }}</span>
                        <a
                          v-if="c.source_url"
                          class="citation-source citation-link"
                          :href="c.source_url"
                          target="_blank"
                          rel="noopener noreferrer"
                        >{{ c.source }}</a>
                        <span v-else class="citation-source">{{ c.source }}</span>
                        <span class="citation-score">
                          {{ c.context_type === 'attachment' ? '上传材料' : c.pinned ? '指定带入' : c.whole_case ? '完整案例' : `相似度 ${c.score}` }}
                        </span>
                      </div>
                      <div v-if="c.whole_case && c.documents?.length" class="citation-documents">
                        已读取：{{ c.documents.join('、') }}
                      </div>
                      <div class="citation-text">{{ c.snippet }}</div>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </div>
          </div>
        </div>

        <footer class="composer-wrap">
          <div class="composer">
            <div class="composer-box">
              <div v-if="composerAttachments.length" class="attachment-tray">
                <div
                  v-for="file in composerAttachments"
                  :key="file.id"
                  class="attachment-chip"
                  :class="{ uploading: isUploading(file) }"
                >
                  <div class="attachment-type" :class="fileKind(file).tone">
                    {{ fileKind(file).label }}
                  </div>
                  <div class="attachment-chip-content">
                    <span class="attachment-chip-name" :title="file.name">{{ file.name }}</span>
                    <span class="attachment-chip-size">
                      {{ file.kind === 'eval_report' ? file.meta : formatSize(file.size) }}
                    </span>
                    <span class="attachment-chip-status" :class="{ done: !isUploading(file) }">
                      <template v-if="isUploading(file)">正在上传 {{ attachmentUploadProgress }}%</template>
                      <template v-else-if="file.kind === 'eval_report'">
                        <el-icon :size="14"><CircleCheckFilled /></el-icon>
                        已选取
                      </template>
                      <template v-else>
                        <el-icon :size="14"><CircleCheckFilled /></el-icon>
                        上传完成
                      </template>
                    </span>
                  </div>
                  <el-tooltip
                    v-if="file.warnings?.length"
                    :content="file.warnings.join(' ')"
                    placement="top"
                  >
                    <span class="attachment-warning">!</span>
                  </el-tooltip>
                  <button
                    type="button"
                    :title="file.kind === 'eval_report' ? '移除' : '移除并删除文件'"
                    @click="removeComposerAttachment(file)"
                  >
                    <el-icon><Close /></el-icon>
                  </button>
                  <el-progress
                    v-if="isUploading(file)"
                    class="attachment-progress"
                    :percentage="attachmentUploadProgress"
                    :stroke-width="3"
                    :show-text="false"
                  />
                </div>
              </div>
              <el-input
                v-model="input"
                class="composer-input"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 6 }"
                resize="none"
                :placeholder="currentMode.placeholder"
                @keydown.enter.exact.prevent="send"
              />
              <div class="composer-toolbar">
                <el-popover
                  v-model:visible="uploadMenuOpen"
                  placement="top-start"
                  :width="168"
                  trigger="click"
                  :disabled="uploadingAttachments"
                  popper-class="upload-source-popper"
                >
                  <template #reference>
                    <button
                      class="composer-tool-btn upload-btn"
                      type="button"
                      :disabled="uploadingAttachments"
                      title="上传文件或选取历史评估报告"
                      aria-label="添加材料"
                      aria-haspopup="menu"
                      :aria-expanded="uploadMenuOpen"
                    >
                      <el-icon :size="18" :class="{ 'is-loading': uploadingAttachments }">
                        <Loading v-if="uploadingAttachments" />
                        <Plus v-else />
                      </el-icon>
                    </button>
                  </template>
                  <div class="upload-source-menu" role="menu">
                    <button type="button" role="menuitem" @click="chooseUploadFiles">
                      <el-icon :size="16"><Upload /></el-icon>
                      <span>上传文件</span>
                    </button>
                    <button type="button" role="menuitem" @click="openEvalDialog">
                      <el-icon :size="16"><Document /></el-icon>
                      <span>选取历史报告</span>
                    </button>
                  </div>
                </el-popover>
                <input
                  ref="uploadInput"
                  class="visually-hidden"
                  type="file"
                  multiple
                  accept=".pdf,.docx,.doc,.pptx,.xlsx,.csv,.tsv,.md,.txt,.html,.htm,.jpg,.jpeg,.png,.gif,.webp,image/jpeg,image/png,image/gif,image/webp"
                  @change="onFilesChosen"
                />
                <div class="composer-toolbar-right">
                  <el-popover
                    v-model:visible="corpusMenuOpen"
                    placement="top-end"
                    :width="180"
                    trigger="click"
                    popper-class="mode-corpus-popper"
                    @show="onCorpusMenuShow"
                  >
                    <template #reference>
                      <button
                        class="mode-trigger"
                        type="button"
                        :title="`当前模式：${currentMode.label}；点击选择模式与知识库`"
                        aria-label="选择模式与知识库"
                      >
                        <el-icon :size="15" class="mode-icon">
                          <component :is="modeIcon(currentMode.name)" />
                        </el-icon>
                        <span>{{ currentMode.label }}</span>
                        <el-icon :size="13"><ArrowUp /></el-icon>
                      </button>
                    </template>
                    <div ref="modeCorpusMenuEl" class="mode-corpus-menu">
                      <div ref="modeMenuHeadEl" class="mode-menu-head">
                        <div class="corpus-menu-title">问答模式</div>
                        <div class="mode-menu" role="radiogroup" aria-label="问答模式">
                          <el-tooltip
                            v-for="mode in qaModes"
                            :key="mode.name"
                            :content="mode.description"
                            placement="left"
                            effect="dark"
                            :show-after="180"
                            :fallback-placements="['left-start', 'top']"
                            popper-class="mode-option-tip"
                          >
                            <button
                              type="button"
                              class="mode-option"
                              :class="{ active: selectedMode === mode.name }"
                              :aria-pressed="selectedMode === mode.name"
                              @click="setMode(mode.name)"
                            >
                              <el-icon :size="15" class="mode-icon">
                                <component :is="modeIcon(mode.name)" />
                              </el-icon>
                              <span>{{ mode.label }}</span>
                            </button>
                          </el-tooltip>
                        </div>
                        <div class="corpus-menu-title knowledge-title">知识库</div>
                      </div>
                      <el-checkbox-group v-model="staticSelectedCorpora">
                        <el-checkbox
                          v-for="c in staticCorpora"
                          :key="c.name"
                          :value="c.name"
                          :disabled="!c.count"
                        >
                          {{ c.label }}
                        </el-checkbox>
                      </el-checkbox-group>
                    </div>
                  </el-popover>
                  <el-button
                    class="send-btn"
                    type="primary"
                    circle
                    :loading="sending"
                    :disabled="sending || uploadingAttachments || !input.trim()"
                    @click="send"
                  >
                    <el-icon v-if="!sending" :size="16"><Promotion /></el-icon>
                  </el-button>
                </div>
              </div>
            </div>
            <div class="composer-hint">
              Enter 发送，Shift+Enter 换行
            </div>
          </div>
        </footer>
      </section>
    </div>

    <el-dialog
      v-model="evalDialogOpen"
      title="选择历史评估任务"
      width="480px"
      append-to-body
      class="eval-report-dialog"
      align-center
    >
      <div class="eval-dialog-toolbar">
        <span class="eval-dialog-count">
          已选 {{ evalDraftIds.length }} / {{ evalReports.length }}
        </span>
        <div class="eval-dialog-actions">
          <button type="button" :disabled="!evalReports.length" @click="selectAllEvalDraft">全选</button>
          <button type="button" :disabled="!evalDraftIds.length" @click="clearEvalDraft">清除</button>
        </div>
      </div>
      <div class="eval-dialog-list">
        <el-checkbox-group v-if="evalReports.length" v-model="evalDraftIds">
          <el-checkbox
            v-for="t in evalReports"
            :key="t.id"
            :value="t.id"
          >
            <span class="eval-report-name">{{ evalReportLabel(t) }}</span>
            <span v-if="evalReportTime(t)" class="eval-report-time">{{ evalReportTime(t) }}</span>
          </el-checkbox>
        </el-checkbox-group>
        <div v-else class="eval-report-empty">完成一次视频评估后会出现在这里</div>
      </div>
      <template #footer>
        <el-button @click="evalDialogOpen = false">取消</el-button>
        <el-button type="primary" @click="confirmEvalDialog">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
export default { name: 'QA' }
</script>

<script setup>
import { computed, nextTick, onActivated, onMounted, ref } from 'vue'
import {
  ArrowUp,
  ChatDotRound,
  ChatLineRound,
  CircleCheckFilled,
  Close,
  DArrowLeft,
  DataAnalysis,
  Document,
  EditPen,
  Loading,
  MoreFilled,
  Notebook,
  Plus,
  Promotion,
  Search,
  Upload,
} from '@element-plus/icons-vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { authState } from '../authStore'
import {
  applyEvalTaskSelection,
  attachmentUploadProgress,
  corpusLabel,
  currentMode,
  currentPinned,
  currentTitle,
  evalReportLabel,
  evalReportTime,
  evalReports,
  initQa,
  input,
  loadEvalReports,
  messages,
  modeLabel,
  newSession,
  onCurrentCommand,
  onQaActivated,
  onSessionCommand,
  openSession,
  qaModes,
  selectedEvalTaskIds,
  selectedAttachments,
  selectedMode,
  setMode,
  sending,
  sessionId,
  sessionQuery,
  sessions,
  setQaScroll,
  sidebarOpen,
  staticCorpora,
  staticSelectedCorpora,
  uploadingAttachments,
  uploadAttachments as uploadQaAttachments,
  removeAttachment,
  useSample,
  visibleGroups,
  send,
} from '../qaStore'

const bodyEl = ref(null)
const uploadInput = ref(null)
const uploadMenuOpen = ref(false)
const corpusMenuOpen = ref(false)
const modeCorpusMenuEl = ref(null)
const modeMenuHeadEl = ref(null)
const evalDialogOpen = ref(false)
const evalDraftIds = ref([])

const composerAttachments = computed(() => [
  ...selectedAttachments.value,
  ...selectedEvalTaskIds.value.flatMap((id) => {
    const task = evalReports.value.find((item) => item.id === id)
    if (!task) return []
    return [{
      id: `eval:${id}`,
      taskId: id,
      kind: 'eval_report',
      name: evalReportLabel(task),
      meta: evalReportTime(task) || '历史评估报告',
      status: 'ready',
      warnings: [],
    }]
  }),
])

function clipMenuToKnowledgeTitle() {
  const menu = modeCorpusMenuEl.value
  const head = modeMenuHeadEl.value
  if (!menu || !head || !head.offsetHeight) return false
  menu.style.maxHeight = `${head.offsetHeight}px`
  return true
}

async function onCorpusMenuShow() {
  for (let i = 0; i < 12; i += 1) {
    await nextTick()
    if (clipMenuToKnowledgeTitle()) return
    await new Promise((resolve) => requestAnimationFrame(resolve))
  }
}

function chooseUploadFiles() {
  uploadMenuOpen.value = false
  uploadInput.value?.click()
}

async function openEvalDialog() {
  corpusMenuOpen.value = false
  uploadMenuOpen.value = false
  await loadEvalReports()
  evalDraftIds.value = [...selectedEvalTaskIds.value]
  evalDialogOpen.value = true
}

function selectAllEvalDraft() {
  evalDraftIds.value = evalReports.value.map((t) => t.id)
}

function clearEvalDraft() {
  evalDraftIds.value = []
}

function confirmEvalDialog() {
  applyEvalTaskSelection(evalDraftIds.value)
  evalDialogOpen.value = false
}

async function onFilesChosen(event) {
  const files = event.target.files
  try {
    await uploadQaAttachments(files)
  } finally {
    event.target.value = ''
  }
}

const MODE_ICONS = {
  ask: ChatDotRound,
  syllabus_design: Notebook,
  teaching_design: EditPen,
  learning_diagnosis: DataAnalysis,
}

function modeIcon(name) {
  return MODE_ICONS[name] || ChatDotRound
}

function removeComposerAttachment(file) {
  if (file?.kind === 'eval_report') {
    applyEvalTaskSelection(selectedEvalTaskIds.value.filter((id) => id !== file.taskId))
    return
  }
  removeAttachment(file)
}

function isUploading(file) {
  return file?.status === 'uploading' || String(file?.id || '').startsWith('pending-')
}

function fileKind(file) {
  if (file?.kind === 'eval_report') return { label: '报告', tone: 'report' }
  const ext = String(file?.suffix || file?.name || '')
    .replace(/^\./, '')
    .split('.')
    .pop()
    .toLowerCase()
  if (ext === 'pdf') return { label: 'PDF', tone: 'pdf' }
  if (ext === 'doc' || ext === 'docx') return { label: 'DOC', tone: 'doc' }
  if (['xls', 'xlsx', 'csv', 'tsv'].includes(ext)) return { label: 'XLS', tone: 'xls' }
  if (ext === 'ppt' || ext === 'pptx') return { label: 'PPT', tone: 'ppt' }
  if (ext === 'md') return { label: 'MD', tone: 'txt' }
  if (ext === 'txt') return { label: 'TXT', tone: 'txt' }
  if (ext === 'html' || ext === 'htm') return { label: 'HTML', tone: 'txt' }
  if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return { label: 'IMG', tone: 'img' }
  return { label: (ext || 'FILE').toUpperCase().slice(0, 4), tone: 'file' }
}

function formatSize(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return ''
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

function renderMd(text) {
  return DOMPurify.sanitize(marked.parse(text || ''))
}

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  setQaScroll(() => {
    if (bodyEl.value) bodyEl.value.scrollTop = bodyEl.value.scrollHeight
  })
  initQa(authState.user?.id)
})

onActivated(() => {
  onQaActivated()
})
</script>

<style scoped>
.qa {
  height: calc(100vh - 56px);
  display: flex;
  background: #fff;
  overflow: hidden;
}

.sidebar {
  width: 0;
  flex-shrink: 0;
  overflow: hidden;
  background: #f7f7f8;
  border-right: 1px solid transparent;
  transition: width 0.2s ease, border-color 0.2s ease;
}
.sidebar.open {
  width: 300px;
  border-right-color: #ececec;
}
.sidebar-inner {
  width: 300px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.stage {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.chat-top {
  height: 52px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
}
.top-left {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}
.top-heading {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 4px;
}
.top-heading :deep(.el-dropdown) {
  margin-left: auto;
  flex-shrink: 0;
}
.top-title {
  min-width: 0;
  flex: 1;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

.icon-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  color: #4b4b4b;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.icon-btn:hover {
  background: #f3f3f3;
}

.chat {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
}

.chat-empty {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px 80px;
  text-align: center;
}
.chat-empty h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 600;
  color: #1f1f1f;
  letter-spacing: 0.5px;
}
.chat-empty p {
  margin: 12px 0 0;
  color: #8a8a8a;
  font-size: 14px;
  max-width: 420px;
  line-height: 1.7;
}
.samples {
  margin-top: 28px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  max-width: 560px;
  width: 100%;
}
.sample {
  text-align: left;
  padding: 14px 16px;
  border: 1px solid #e8e8e8;
  background: #fff;
  border-radius: 14px;
  font-size: 13px;
  color: #303133;
  cursor: pointer;
  line-height: 1.5;
}
.sample:hover {
  background: #f7f7f7;
  border-color: #dcdcdc;
}

.thread {
  max-width: 768px;
  margin: 0 auto;
  padding: 8px 20px 24px;
  width: 100%;
}

.msg {
  display: flex;
  margin: 18px 0;
}
.msg.user {
  justify-content: flex-end;
}
.msg.assistant {
  justify-content: flex-start;
}

.user-message {
  max-width: 72%;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.bubble.user {
  max-width: 72%;
  padding: 10px 16px;
  border-radius: 18px;
  background: #f4f4f4;
  color: #1f1f1f;
  font-size: 15px;
  line-height: 1.7;
  white-space: pre-wrap;
}
.user-message .bubble.user {
  max-width: 100%;
}
.message-attachments {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 5px;
}
.message-attachment {
  max-width: 280px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid #e4e4e4;
  border-radius: 8px;
  color: #606266;
  background: #fff;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.assistant {
  width: 100%;
  font-size: 15px;
  line-height: 1.8;
  color: #1f1f1f;
}

.plan {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-bottom: 10px;
}
.plan-label {
  font-size: 12px;
  color: #a8abb2;
}
.mode-badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: #f5e6e6;
  color: #7b1113;
  font-size: 12px;
  font-weight: 600;
}
.matched-cases {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: -3px 0 10px;
  font-size: 12px;
}
.matched-label {
  color: #a8abb2;
}
.matched-course {
  padding: 2px 8px;
  border-radius: 6px;
  background: #f7f7f8;
  color: #606266;
  text-decoration: none;
}
.matched-course[href]:hover {
  color: #7b1113;
  text-decoration: underline;
}

.stream-status {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  min-height: 1.8em;
}
.thinking {
  font-size: 14px;
  color: #a61b1b;
  letter-spacing: 0.04em;
}
.dots::after {
  display: inline-block;
  width: 1.4em;
  text-align: left;
  content: '';
  animation: thinking-dots 1.2s steps(4, end) infinite;
}
@keyframes thinking-dots {
  0% {
    content: '';
  }
  25% {
    content: '.';
  }
  50% {
    content: '..';
  }
  75% {
    content: '...';
  }
}

.cursor {
  animation: blink 1s step-end infinite;
  color: #a61b1b;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}

.citations {
  margin-top: 10px;
}
.citations :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: #a61b1b;
  height: 32px;
  line-height: 32px;
  border-bottom: none;
}
.citations :deep(.el-collapse-item__arrow) {
  color: #a61b1b;
}
.citation {
  padding: 8px 0;
  border-bottom: 1px dashed #f0f0f0;
}
.citation-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 4px;
}
.citation-corpus {
  color: #a61b1b;
  font-weight: 600;
}
.citation-source {
  color: #909399;
}
.citation-link {
  color: #606266;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.citation-link:hover {
  color: #a61b1b;
}
.citation-score {
  margin-left: auto;
  color: #c0c4cc;
}
.citation-text {
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}
.citation-documents {
  margin-bottom: 4px;
  color: #909399;
  font-size: 11px;
}

.markdown :deep(h2),
.markdown :deep(h3) {
  font-size: 15px;
  color: #1f1f1f;
  margin: 14px 0 6px;
}
.markdown :deep(p) {
  margin: 6px 0;
}
.markdown :deep(ul),
.markdown :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}
.markdown :deep(li) {
  margin: 3px 0;
}
.markdown :deep(code) {
  background: #f5f5f5;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 13px;
}
.markdown :deep(pre) {
  background: #f7f8fa;
  padding: 10px;
  border-radius: 8px;
  overflow-x: auto;
}

.composer-wrap {
  flex-shrink: 0;
  padding: 0 16px 16px;
}
.composer {
  max-width: 768px;
  margin: 0 auto;
}
.composer-box {
  display: flex;
  flex-direction: column;
  border: 1px solid #e4e4e4;
  border-radius: 24px;
  background: #fff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04);
  padding: 10px 12px 8px;
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.composer-box:focus-within {
  border-color: #d0d0d0;
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.06);
}
.composer-input {
  width: 100%;
}
.composer-box :deep(.el-textarea__inner) {
  box-shadow: none;
  border: none;
  padding: 2px 4px 8px;
  background: transparent;
  font-size: 15px;
  line-height: 1.6;
}
.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 34px;
}
.composer-toolbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}
.composer-tool-btn {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #4b4b4b;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.composer-tool-btn:hover {
  background: #f3f3f3;
}
.composer-tool-btn:disabled {
  cursor: wait;
  opacity: 0.7;
}
.mode-trigger {
  flex: 0 0 auto;
  height: 34px;
  padding: 0 5px 0 8px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: #4b4b4b;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  font-size: 13px;
  white-space: nowrap;
}
.mode-trigger:hover {
  background: #f3f3f3;
}
.mode-icon {
  flex-shrink: 0;
  color: inherit;
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.send-btn {
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
}
.composer-hint {
  text-align: center;
  font-size: 12px;
  color: #c0c4cc;
  margin-top: 8px;
}

.attachment-tray {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding: 2px 1px 10px;
}
.attachment-chip {
  flex: 0 0 auto;
  position: relative;
  width: 248px;
  min-height: 72px;
  padding: 10px 28px 10px 10px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border: 1px solid #ececec;
  border-radius: 12px;
  background: #fff;
  color: #303133;
  overflow: hidden;
}
.attachment-type {
  width: 44px;
  height: 52px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.attachment-type.pdf {
  background: #c0392b;
}
.attachment-type.doc {
  background: #2b579a;
}
.attachment-type.xls {
  background: #1d7a46;
}
.attachment-type.ppt {
  background: #d24726;
}
.attachment-type.txt,
.attachment-type.file {
  background: #6b7280;
}
.attachment-type.img {
  background: #0f766e;
}
.attachment-type.report {
  background: #7b1113;
}
.attachment-chip-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-top: 1px;
}
.attachment-chip-name {
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attachment-chip-size {
  color: #909399;
  font-size: 12px;
  line-height: 1.3;
  white-space: nowrap;
}
.attachment-chip-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.3;
}
.attachment-chip-status.done {
  color: #1a9e5c;
}
.attachment-warning {
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #fdf0df;
  color: #b36b00;
  font-size: 11px;
  font-weight: 700;
}
.attachment-chip button {
  position: absolute;
  right: 6px;
  top: 6px;
  width: 20px;
  height: 20px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: #c0c4cc;
  cursor: pointer;
}
.attachment-chip button:hover {
  background: #f3f3f3;
  color: #606266;
}
.attachment-progress {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  line-height: 0;
}
.attachment-progress :deep(.el-progress-bar__outer) {
  border-radius: 0 0 12px 12px;
  background: #f0f0f0;
}
.attachment-progress :deep(.el-progress-bar__inner) {
  border-radius: 0;
  background: #2b579a;
}

.mode-corpus-menu {
  position: relative;
  max-height: 220px;
  overflow-x: hidden;
  overflow-y: auto;
}
.corpus-menu-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.mode-corpus-menu :deep(.el-checkbox-group) {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mode-menu {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mode-option {
  width: 100%;
  min-width: 0;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #303133;
  text-align: left;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  line-height: 1.4;
}
.mode-option:hover {
  background: #f7f7f8;
}
.mode-option.active {
  background: #fdf6f6;
  color: #7b1113;
  font-weight: 600;
}
.knowledge-title {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #f0f0f0;
}
.eval-report-name {
  display: block;
  line-height: 1.35;
  word-break: break-all;
  white-space: normal;
}
.eval-report-time {
  display: block;
  font-size: 11px;
  color: #c0c4cc;
  line-height: 1.3;
  margin-top: 2px;
}
.eval-report-empty {
  font-size: 13px;
  color: #c0c4cc;
  line-height: 1.5;
  padding: 24px 0;
  text-align: center;
}

.drawer-head {
  height: 56px;
  padding: 0 8px 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #303133;
  flex-shrink: 0;
}
.drawer-title {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.02em;
  line-height: 1.2;
  color: #7b1113;
  position: relative;
  padding-left: 10px;
}
.drawer-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: 3px;
  border-radius: 2px;
  background: #a61b1b;
}
.drawer-tools {
  padding: 0 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}
.new-eval-btn {
  height: 36px;
  border: 1px solid #a61b1b;
  background: #fff;
  color: #a61b1b;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
}
.new-eval-btn:hover {
  background: #fdf4f4;
}
.task-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px 16px;
}
.empty-hint {
  color: #909399;
  font-size: 13px;
  text-align: center;
  padding: 24px 0;
}
.task-group + .task-group {
  margin-top: 8px;
}
.group-label {
  font-size: 12px;
  font-weight: 600;
  color: #8a8a8a;
  letter-spacing: 0.08em;
  padding: 8px 8px 4px;
}
.task {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 8px;
  border-top: 1px solid #ececec;
  cursor: pointer;
}
.task:hover {
  background: #ececed;
}
.task.active {
  background: #f5e6e6;
}
.task.active .task-name {
  color: #7b1113;
}
.task.pending .task-name {
  color: #7b1113;
}
.task-icon {
  flex-shrink: 0;
  margin-top: 2px;
  color: #8a8a8a;
}
.task.active .task-icon,
.task.pinned .task-icon,
.task.pending .task-icon {
  color: #a61b1b;
}
.task-body {
  min-width: 0;
  flex: 1;
}
.task-name {
  font-size: 13px;
  color: #303133;
  letter-spacing: 0.02em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
}
.task-time {
  font-size: 11px;
  color: #a8abb2;
}
.task-run {
  margin-top: 4px;
  font-size: 12px;
  color: #a61b1b;
}
.task :deep(.el-dropdown) {
  flex-shrink: 0;
}
.more-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: #909399;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.more-btn:hover {
  background: #fff;
  color: #303133;
}
.header-more:hover {
  background: #f3f3f3;
}

@media (max-width: 640px) {
  .samples {
    grid-template-columns: 1fr;
  }
  .chat-empty h1 {
    font-size: 24px;
  }
  .bubble.user {
    max-width: 88%;
  }
  .user-message {
    max-width: 88%;
  }
}
</style>

<style>
.mode-corpus-popper {
  padding: 10px 8px !important;
}
.upload-source-popper {
  padding: 6px !important;
}
.upload-source-popper .upload-source-menu {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.upload-source-popper .upload-source-menu button {
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #303133;
  text-align: left;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  line-height: 1.4;
}
.upload-source-popper .upload-source-menu button:hover {
  background: #f7f7f8;
  color: #7b1113;
}
.mode-corpus-popper .mode-corpus-menu {
  scrollbar-width: thin;
  scrollbar-color: #dcdcdc transparent;
}
.mode-option-tip.el-popper {
  max-width: 180px;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: #5c5c5c !important;
  color: #fff;
  font-size: 12px;
  line-height: 1.5;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
}
.mode-option-tip.el-popper .el-popper__arrow::before {
  background: #5c5c5c !important;
  border: none;
}
.eval-report-dialog .eval-dialog-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.eval-report-dialog .eval-dialog-count {
  font-size: 13px;
  color: #909399;
}
.eval-report-dialog .eval-dialog-actions {
  display: flex;
  gap: 4px;
}
.eval-report-dialog .eval-dialog-actions button {
  border: none;
  background: none;
  color: #7b1113;
  cursor: pointer;
  font-size: 13px;
  padding: 4px 8px;
}
.eval-report-dialog .eval-dialog-actions button:disabled {
  color: #c0c4cc;
  cursor: not-allowed;
}
.eval-report-dialog .eval-dialog-list {
  max-height: min(52vh, 420px);
  overflow-y: auto;
  padding-right: 4px;
}
.eval-report-dialog .el-checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.eval-report-dialog .el-checkbox {
  align-items: flex-start;
  height: auto;
  margin-right: 0;
  white-space: normal;
}
.eval-report-dialog .eval-report-name {
  display: block;
  line-height: 1.35;
  word-break: break-all;
  white-space: normal;
}
.eval-report-dialog .eval-report-time {
  display: block;
  font-size: 11px;
  color: #c0c4cc;
  line-height: 1.3;
  margin-top: 2px;
}
.eval-report-dialog .eval-report-empty {
  font-size: 13px;
  color: #c0c4cc;
  line-height: 1.5;
  padding: 24px 0;
  text-align: center;
}
</style>
