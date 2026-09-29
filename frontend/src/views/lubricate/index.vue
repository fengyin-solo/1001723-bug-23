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
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
            <button class="link" type="button" @click="openEdit(row)">保存保养信息</button>
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
      <div class="modal-card">
        <h3>{{ formMode === 'create' ? '登记保养记录' : '保存保养信息' }}</h3>
        <div class="form-grid">
          <label v-for="field in formFields" :key="field" class="form-item">
            <span>{{ field }}{{ requiredFields.includes(field) ? ' *' : '' }}</span>
            <input
              v-model="formValues[field]"
              :readonly="field === '保养单号' && formMode === 'edit'"
              :type="field === '保养日期' ? 'date' : 'text'"
              :placeholder="`请输入${field}`"
            />
          </label>
        </div>
        <p v-if="formMessage" class="error-text" style="margin: 10px 0 0; font-size: 12px;">{{ formMessage }}</p>
        <div class="modal-foot">
          <button class="btn ghost" type="button" :disabled="saving" @click="closeForm">取消</button>
          <button class="btn" type="button" :disabled="saving" @click="submitForm(false)">保存</button>
          <button
            v-if="formMode === 'edit'"
            class="btn primary"
            type="button"
            :disabled="saving"
            @click="submitForm(true)"
          >
            保存并确认完成
          </button>
          <button v-else class="btn primary" type="button" :disabled="saving" @click="submitForm(false)">登记</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type FormMode = 'create' | 'edit'

const ENDPOINT = '/api/lubricate'
const columns = ["保养单号", "保养设备", "润滑点位", "油品规格", "加注用量", "保养人员", "保养日期", "保养状态"]
const actions = ["安排保养", "确认完成", "标记延期"]
const formFields = ["保养单号", "保养设备", "润滑点位", "油品规格", "加注用量", "保养人员", "保养日期"]
const requiredFields = ["保养单号", "保养设备", "润滑点位"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

// 页面统计与首页 /api/overview 同源：待处理就是 status !== '已完成'
// （已延期仍然算未完成），避免两个页面各算各的。
const stats = computed(() => {
  const now = new Date()
  const monthPrefix = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const pending = rows.value.filter((row) => row['status'] !== '已完成').length
  const monthCount = rows.value.filter((row) => String(row['保养日期'] ?? '').startsWith(monthPrefix)).length
  const delayed = rows.value.filter((row) => row['status'] === '已延期').length
  return [
    { label: '待保养设备', value: pending },
    { label: '本月保养单数', value: monthCount },
    { label: '已延期保养', value: delayed },
  ]
})

const formVisible = ref(false)
const formMode = ref<FormMode>('create')
const formValues = ref<Record<string, string>>({})
const editingId = ref<number | null>(null)
const formMessage = ref('')
const saving = ref(false)

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function emptyForm() {
  return Object.fromEntries(formFields.map((field) => [field, '']))
}

function openCreate() {
  formMode.value = 'create'
  editingId.value = null
  formValues.value = emptyForm()
  formMessage.value = ''
  formVisible.value = true
}

function openEdit(row: Row) {
  formMode.value = 'edit'
  editingId.value = Number(row.id)
  formValues.value = Object.fromEntries(
    formFields.map((field) => [field, row[field] == null ? '' : String(row[field])]),
  )
  formMessage.value = ''
  formVisible.value = true
}

function closeForm() {
  formVisible.value = false
  editingId.value = null
}

async function submitForm(complete: boolean) {
  formMessage.value = ''
  const missing = requiredFields.filter((field) => !formValues.value[field]?.trim())
  if (missing) {
    formMessage.value = `缺少必填字段：${missing.join('、')}`
    return
  }
  saving.value = true
  try {
    const values: Record<string, unknown> = { ...formValues.value }
    if (complete) {
      values.complete = true
    }
    const url = formMode.value === 'create' ? ENDPOINT : `${ENDPOINT}/${editingId.value}`
    const response = await request(url, {
      method: formMode.value === 'create' ? 'POST' : 'PUT',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message || '保养记录保存未生效，请稍后重试')
    }
    closeForm()
    await reload()
  } catch (error) {
    formMessage.value = error instanceof Error ? error.message : '保养记录保存失败'
  } finally {
    saving.value = false
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    // 业务失败时后端返回 ok:false，不能只看 HTTP 状态码，否则页面会显示“已完成”而记录没动。
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error(payload?.message || '润滑保养动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '润滑保养操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('保养记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '润滑保养列表读取失败'
  }
}

onMounted(reload)
</script>
