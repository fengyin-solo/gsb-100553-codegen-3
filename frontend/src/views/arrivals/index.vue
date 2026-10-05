<template>
  <section class="page" data-module="arrivals">
    <header class="page-head">
      <div>
        <h2>到货验收台账</h2>
        <p class="page-desc">一个到货批次一条记录，开箱、验收、入库、质保按顺序留痕；同一批次重复登记自动并入补充记录。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openRegister">登记到货批次</button>
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
        <span>到货批次 / 送货单 / 备件</span>
        <input v-model="keyword" placeholder="输入关键字检索" />
      </label>
      <label class="filter-item">
        <span>验收状态</span>
        <select v-model="status">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
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
          <td v-for="column in columns" :key="column">
            <template v-if="column === '状态'">
              <span class="status-tag" :class="statusClass(String(row.status))">{{ row[column] ?? '—' }}</span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button v-if="String(row.status) === '待验收'" class="link" type="button" @click="runSimpleAction('开始验收', row)">
              开始验收
            </button>
            <template v-if="String(row.status) === '验收中'">
              <button class="link" type="button" @click="openDetail(row, 'open')">填写开箱</button>
              <button class="link" type="button" @click="openDetail(row, 'accept')">提交验收</button>
              <button class="link" type="button" @click="openDetail(row, 'store')">确认入库</button>
            </template>
            <template v-if="String(row.status) === '已入库'">
              <button class="link" type="button" @click="runSimpleAction('开始验收', row)">重新验收</button>
              <button class="link" type="button" @click="runSimpleAction('质保生效', row)">质保生效</button>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无到货验收记录，可先登记到货批次</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条到货批次</span>
      <span v-if="message" :class="messageOk ? 'success-text' : 'error-text'">{{ message }}</span>
    </footer>

    <div v-if="registerVisible" class="modal-mask" @click.self="registerVisible = false">
      <form class="modal" @submit.prevent="submitRegister">
        <div class="modal-head">
          <h3>登记到货批次</h3>
          <button class="icon-btn" type="button" @click="registerVisible = false">×</button>
        </div>
        <div class="form-grid">
          <label v-for="field in registerFields" :key="field.name" :class="{ wide: field.wide }">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <input
              v-model="registerForm[field.name]"
              :type="field.type ?? 'text'"
              :placeholder="`请输入${field.label}`"
            />
          </label>
        </div>
        <p v-if="message" :class="messageOk ? 'success-text' : 'error-text'">{{ message }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="registerVisible = false">取消</button>
          <button class="btn primary" type="submit">保存登记</button>
        </div>
      </form>
    </div>

    <div v-if="detailVisible && detail" class="modal-mask detail-mask" @click.self="detailVisible = false">
      <div class="modal detail-modal">
        <div class="modal-head">
          <h3>到货批次详情 · {{ detail['到货批次'] }}</h3>
          <button class="icon-btn" type="button" @click="detailVisible = false">×</button>
        </div>

        <p v-if="message" :class="messageOk ? 'success-text' : 'error-text'">{{ message }}</p>

        <div class="detail-grid">
          <div v-for="item in detailItems" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <section id="arrival-open-record" class="record-block">
          <h4>开箱记录</h4>
          <div class="form-grid">
            <label v-for="field in openFields" :key="field">
              <span>{{ field }}<em>*</em></span>
              <input v-model="detailForm[field]" :type="field.includes('日期') ? 'date' : 'text'" />
            </label>
          </div>
          <button class="btn" type="button" :disabled="!detail" @click="submitDetailAction('保存开箱记录')">
            保存开箱记录
          </button>
        </section>

        <section id="arrival-accept-record" class="record-block">
          <h4>验收记录</h4>
          <div class="form-grid">
            <label>
              <span>验收人<em>*</em></span>
              <input v-model="detailForm['验收人']" />
            </label>
            <label>
              <span>验收日期<em>*</em></span>
              <input v-model="detailForm['验收日期']" type="date" />
            </label>
            <label>
              <span>验收结论<em>*</em></span>
              <select v-model="detailForm['验收结论']">
                <option value="">请选择</option>
                <option v-for="item in conclusions" :key="item" :value="item">{{ item }}</option>
              </select>
            </label>
            <label v-if="detailForm['验收结论'] === '部分合格'">
              <span>合格数量<em>*</em></span>
              <input v-model="detailForm['合格数量']" type="number" min="1" />
            </label>
            <label class="wide">
              <span>问题说明{{ detailForm['验收结论'] === '合格' ? '' : '*' }}</span>
              <textarea v-model="detailForm['问题说明']" rows="3" />
            </label>
          </div>
          <button class="btn" type="button" @click="submitDetailAction('提交验收结论')">提交验收结论</button>
        </section>

        <section id="arrival-storage-record" class="record-block">
          <h4>入库与质保</h4>
          <div class="form-grid">
            <label>
              <span>入库经办人<em>*</em></span>
              <input v-model="detailForm['入库经办人']" />
            </label>
            <label>
              <span>实际入库日期<em>*</em></span>
              <input v-model="detailForm['入库日期']" type="date" />
            </label>
            <label>
              <span>质保期（月）</span>
              <input v-model="detailForm['质保期月数']" type="number" min="1" />
            </label>
            <label>
              <span>质保起算日</span>
              <input :value="detailForm['质保起算日'] || '入库后自动生成'" disabled />
            </label>
          </div>
          <div class="inline-actions">
            <button class="btn primary" type="button" @click="submitDetailAction('确认入库')">确认入库</button>
            <button v-if="String(detail.status) === '已入库'" class="btn" type="button" @click="runSimpleAction('质保生效')">
              质保生效
            </button>
            <button v-if="String(detail.status) === '已入库'" class="btn ghost" type="button" @click="runSimpleAction('开始验收')">
              退回验收中
            </button>
          </div>
        </section>

        <section v-if="supplements.length" class="record-block">
          <h4>补充记录</h4>
          <ul class="supplement-list">
            <li v-for="(item, index) in supplements" :key="index">
              <strong>第 {{ index + 1 }} 次补充 · {{ item['登记时间'] }}</strong>
              <span v-for="(value, key) in withoutMeta(item)" :key="String(key)">{{ key }}：{{ value }}</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, unknown>
type FormValues = Record<string, string>

const ENDPOINT = '/api/arrivals'
const columns = [
  '状态', '到货批次', '送货单号', '送货日期', '备件编号', '备件名称',
  '到货数量', '合格数量', '入库数量', '验收结论', '入库日期', '质保起算日', '质保到期日',
]
const statuses = ['待验收', '验收中', '已入库', '质保生效']
const conclusions = ['合格', '部分合格', '不合格']
const openFields = ['开箱人', '开箱日期', '包装检查', '外观检查', '资料附件']

const rows = ref<Row[]>([])
const total = ref(0)
const keyword = ref('')
const status = ref('')
const message = ref('')
const messageOk = ref(false)

const registerVisible = ref(false)
const detailVisible = ref(false)
const detail = ref<Row | null>(null)

interface RegisterField {
  name: string
  label: string
  required?: boolean
  type?: string
  wide?: boolean
}

const registerFields: RegisterField[] = [
  { name: '到货批次', label: '到货批次', required: true },
  { name: '送货单号', label: '送货单号' },
  { name: '送货日期', label: '送货日期', required: true, type: 'date' },
  { name: '供应商', label: '供应商' },
  { name: '承运单位', label: '承运单位' },
  { name: '备件编号', label: '备件编号', required: true },
  { name: '备件名称', label: '备件名称', required: true },
  { name: '规格型号', label: '规格型号' },
  { name: '到货数量', label: '到货数量', required: true, type: 'number' },
  { name: '质保期月数', label: '质保期（月）', type: 'number' },
]
const registerForm = reactive<FormValues>({})
const detailForm = reactive<FormValues>({})

const stats = computed(() => {
  const checking = rows.value.filter((item) => ['待验收', '验收中'].includes(String(item.status))).length
  const stored = rows.value.filter((item) => ['已入库', '质保生效'].includes(String(item.status))).length
  const abnormal = rows.value.filter((item) => item['验收结论'] === '部分合格' || item['验收结论'] === '不合格').length
  return [
    { label: '到货批次', value: total.value },
    { label: '待验收/验收中', value: checking },
    { label: '已入库批次', value: stored },
    { label: '差异批次', value: abnormal },
  ]
})

const supplements = computed(() => {
  const value = detail.value?.['补充记录']
  return Array.isArray(value) ? (value as Row[]) : []
})

const detailItems = computed(() => [
  { label: '当前状态', value: detail.value?.status ?? '—' },
  { label: '送货日期', value: detail.value?.['送货日期'] ?? '—' },
  { label: '供应商', value: detail.value?.['供应商'] ?? '—' },
  { label: '承运单位', value: detail.value?.['承运单位'] ?? '—' },
  { label: '规格型号', value: detail.value?.['规格型号'] ?? '—' },
  { label: '到货数量', value: detail.value?.['到货数量'] ?? 0 },
  { label: '合格数量', value: detail.value?.['合格数量'] ?? 0 },
  { label: '不合格数量', value: detail.value?.['不合格数量'] ?? 0 },
  { label: '入库数量', value: detail.value?.['入库数量'] ?? 0 },
])

function setMessage(text: string, ok = false) {
  message.value = text
  messageOk.value = ok
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function statusClass(value: string) {
  return {
    checking: value === '验收中' || value === '待验收',
    done: value === '已入库' || value === '质保生效',
    warranty: value === '质保生效',
  }
}

function fillDetailForm(row: Row) {
  const fields = [
    ...openFields,
    '验收人', '验收日期', '验收结论', '问题说明', '合格数量',
    '入库经办人', '入库日期', '质保期月数', '质保起算日', '质保到期日',
  ]
  for (const field of fields) {
    detailForm[field] = row[field] === undefined || row[field] === null ? '' : String(row[field])
  }
}

async function reload() {
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (status.value) query.set('status', status.value)
  query.set('size', '100')
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('到货验收列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '到货验收列表读取失败')
  }
}

function openRegister() {
  for (const key of Object.keys(registerForm)) delete registerForm[key]
  registerForm['质保期月数'] = '12'
  registerVisible.value = true
}

async function submitRegister() {
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...registerForm } }),
    })
    const payload = await response.json()
    if (!payload.ok) throw new Error(payload.message ?? '登记失败')
    registerVisible.value = false
    setMessage(payload.message, true)
    await reload()
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '登记失败')
  }
}

async function openDetail(row: Row, focus?: 'open' | 'accept' | 'store') {
  try {
    const response = await request(`${ENDPOINT}/${String(row.id)}`)
    if (!response.ok) throw new Error('到货批次详情读取失败')
    const loaded: Row = await response.json()
    detail.value = loaded
    fillDetailForm(loaded)
    detailVisible.value = true
    setMessage('', false)
    requestAnimationFrame(() => {
      const sectionId = focus === 'accept'
        ? 'arrival-accept-record'
        : focus === 'store'
          ? 'arrival-storage-record'
          : 'arrival-open-record'
      document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '到货批次详情读取失败')
  }
}

async function postAction(id: string, action: string, values: Record<string, unknown> = {}) {
  const response = await request(`${ENDPOINT}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action, ...values } }),
  })
  return response.json()
}

async function runSimpleAction(action: string, row?: Row) {
  const current = row ?? detail.value
  if (!current) return
  try {
    const payload = await postAction(String(current.id), action)
    if (!payload.ok) throw new Error(payload.message ?? '操作未生效')
    setMessage(payload.message, true)
    await reload()
    if (detailVisible.value && payload.entry && detail.value?.id === current.id) {
      const updated: Row = payload.entry
      detail.value = updated
      fillDetailForm(updated)
    }
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '操作失败')
  }
}

async function submitDetailAction(action: string) {
  if (!detail.value) return
  const current = detail.value
  try {
    const payload = await postAction(String(current.id), action, { ...detailForm })
    if (!payload.ok) throw new Error(payload.message ?? '操作未生效')
    const updated: Row = payload.entry
    detail.value = updated
    fillDetailForm(updated)
    setMessage(payload.message, true)
    await reload()
  } catch (error) {
    setMessage(error instanceof Error ? error.message : '操作失败')
  }
}

function withoutMeta(item: Row) {
  return Object.fromEntries(Object.entries(item).filter(([key]) => key !== '登记时间'))
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.success-text { color: #027a48; }
.filter-item select { min-width: 140px; }
.status-tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; background: #eef2ff; color: #3730a3; }
.status-tag.done { background: #ecfdf3; color: #027a48; }
.status-tag.warranty { background: #fff7ed; color: #c2410c; }
.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); z-index: 20; display: flex; align-items: center; justify-content: center; padding: 24px; }
.modal { background: #fff; border-radius: 10px; width: min(680px, 100%); max-height: 90vh; overflow: auto; padding: 18px 20px; box-shadow: 0 20px 40px rgba(15, 23, 42, 0.24); }
.detail-mask { align-items: flex-start; }
.detail-modal { width: min(960px, 100%); }
.modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.modal-head h3 { margin: 0; font-size: 18px; }
.icon-btn { border: none; background: none; font-size: 24px; cursor: pointer; color: var(--muted); }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; margin-bottom: 12px; }
.form-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-grid label.wide { grid-column: span 2; }
.form-grid input, .form-grid select, .form-grid textarea { border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; font: inherit; color: #1f2937; }
.form-grid input:disabled { background: #f1f5f9; color: var(--muted); }
.form-grid em { color: #d92d20; font-style: normal; margin-left: 2px; }
.modal-actions, .inline-actions { display: flex; justify-content: flex-end; gap: 8px; }
.detail-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px; }
.detail-grid div { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; }
.detail-grid span, .detail-grid strong { display: block; }
.detail-grid span { color: var(--muted); font-size: 12px; }
.detail-grid strong { margin-top: 3px; font-size: 13px; }
.record-block { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 12px; }
.record-block h4 { margin: 0 0 10px; font-size: 14px; }
.supplement-list { padding-left: 18px; margin: 0; display: grid; gap: 8px; }
.supplement-list li { display: grid; gap: 3px; font-size: 12px; }
.supplement-list span { color: var(--muted); margin-right: 12px; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
