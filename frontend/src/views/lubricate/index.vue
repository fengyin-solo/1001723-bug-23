<template>
  <section class="page" data-module="lubricate">
    <header class="page-head">
      <div>
        <h2>润滑保养管理</h2>
        <p class="page-desc">维护保养记录，围绕保养单号、保养设备、润滑点位、油品规格做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记保养记录</button>
        <button class="btn" type="button" @click="exportRows">导出润滑保养清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>保养单号</span>
        <input v-model="keyword" placeholder="按保养单号检索" />
      </label>
      <label class="filter-item">
        <span>保养状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="name in statuses" :key="name" :value="name">{{ name }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">编辑保存</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无润滑保养数据，可先登记保养记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条润滑保养记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <form class="modal-card" @submit.prevent="submitForm">
        <h3 class="modal-title">{{ formId === null ? '登记保养记录' : '编辑保养记录' }}</h3>
        <div class="modal-grid">
          <label v-for="field in editableFields" :key="field" class="modal-field">
            <span>{{ field }}<em v-if="requiredFields.includes(field)">*</em></span>
            <input
              v-model="formValues[field]"
              :type="field === '保养日期' ? 'date' : 'text'"
              :placeholder="`请输入${field}`"
            />
          </label>
        </div>
        <div class="modal-foot">
          <span v-if="formError" class="error-text">{{ formError }}</span>
          <span class="modal-spacer" />
          <button class="btn ghost" type="button" @click="closeForm">取消</button>
          <button class="btn primary" type="submit" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/lubricate'
const columns = ['保养单号', '保养设备', '润滑点位', '油品规格', '加注用量', '保养人员', '保养日期', '保养状态']
const editableFields = ['保养单号', '保养设备', '润滑点位', '油品规格', '加注用量', '保养人员', '保养日期']
const requiredFields = ['保养单号', '保养设备', '润滑点位']
const actions = ['安排保养', '确认完成', '标记延期']
const statuses = ['待保养', '保养中', '已完成', '已延期']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const status = ref('')

const stats = reactive([
  { label: '未完成保养', value: 0 },
  { label: '本月保养单数', value: 0 },
  { label: '已延期保养', value: 0 },
])

const formVisible = ref(false)
const saving = ref(false)
const formId = ref<number | null>(null)
const formError = ref('')
const formValues = reactive<Record<string, string>>({})

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function refreshStats() {
  // 统计口径与首页「待处理」一致：拉全量后按 pending / 保养状态计数，不被分页和筛选影响
  const response = await request(`${ENDPOINT}?size=200`)
  if (!response.ok) {
    return
  }
  const payload = await response.json()
  const all: Row[] = payload.items ?? []
  const now = new Date()
  const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  stats[0].value = all.filter((row) => row.pending !== false && row['保养状态'] !== '已完成').length
  stats[1].value = all.filter((row) => String(row['保养日期'] ?? '').startsWith(month)).length
  stats[2].value = all.filter((row) => row['保养状态'] === '已延期').length
}

function openCreate() {
  formId.value = null
  formError.value = ''
  for (const field of editableFields) {
    formValues[field] = ''
  }
  formVisible.value = true
}

function openEdit(row: Row) {
  formId.value = Number(row.id)
  formError.value = ''
  for (const field of editableFields) {
    const value = row[field]
    formValues[field] = value === null || value === undefined ? '' : String(value)
  }
  formVisible.value = true
}

function closeForm() {
  if (saving.value) {
    return
  }
  formVisible.value = false
}

async function submitForm() {
  formError.value = ''
  saving.value = true
  try {
    const url = formId.value === null ? ENDPOINT : `${ENDPOINT}/${formId.value}`
    const response = await request(url, {
      method: formId.value === null ? 'POST' : 'PUT',
      body: JSON.stringify({ values: { ...formValues } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '保养记录保存失败')
    }
    formVisible.value = false
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '保养记录保存失败'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '润滑保养动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '润滑保养操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) {
    query.set('keyword', keyword.value.trim())
  }
  if (status.value) {
    query.set('status', status.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('保养记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    await refreshStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '润滑保养列表读取失败'
  }
}

onMounted(reload)
</script>
