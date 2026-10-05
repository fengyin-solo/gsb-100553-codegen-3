<template>
  <section class="page" data-module="arrival">
    <header class="page-head">
      <div>
        <h2>到货验收台账</h2>
        <p class="page-desc">
          一个到货批次一条记录：待验收 → 验收中 → 已入库 → 质保生效。开箱记录没填完不许入库，
          已入库再点验收退回验收中；同批号重复登记只留最早一条，后一次并成补充记录。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openRegister">登记到货批次</button>
        <button class="btn" type="button" @click="exportRows">导出台账</button>
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
        <span>关键字</span>
        <input v-model="filters.keyword" placeholder="到货批号 / 送货单号 / 备件编号" />
      </label>
      <label class="filter-item">
        <span>验收状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>到货批号</th>
          <th>送货单号</th>
          <th>备件</th>
          <th>送货/入库</th>
          <th>送货日期</th>
          <th>质保起算日</th>
          <th>质保截止日</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['到货批号'] }}</td>
          <td>{{ row['送货单号'] || '—' }}</td>
          <td>{{ row['备件编号'] }} · {{ row['备件名称'] }}</td>
          <td>{{ row['送货数量'] }} / {{ row['入库数量'] || 0 }}</td>
          <td>{{ row['送货日期'] }}</td>
          <td>{{ row['质保起算日'] || '—' }}</td>
          <td>{{ row['质保截止日'] || '—' }}</td>
          <td>
            <span :class="['status-tag', statusClass(row.status)]">{{ row.status }}</span>
            <em v-if="row['存量批次']" class="legacy-tag">存量回填</em>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row.id)">查看/验收</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="9" class="empty-state">暂无到货批次，可先登记一张送货单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条到货批次</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="message" class="ok-text">{{ message }}</span>
    </footer>

    <!-- 到货登记弹窗 -->
    <div v-if="registerOpen" class="modal-mask" @click.self="registerOpen = false">
      <div class="modal">
        <h3>登记到货批次</h3>
        <p class="modal-hint">同一到货批号重复登记时，只留最早那条，本次提交会并成补充记录。</p>
        <div class="form-grid">
          <label><span>到货批号 *</span><input v-model="regForm['到货批号']" placeholder="如 ARR-202610-01" /></label>
          <label><span>送货单号</span><input v-model="regForm['送货单号']" placeholder="如 DN-1001" /></label>
          <label><span>备件编号 *</span><input v-model="regForm['备件编号']" placeholder="对应备件编号，用于存量与待办联动" /></label>
          <label><span>备件名称</span><input v-model="regForm['备件名称']" /></label>
          <label><span>规格型号</span><input v-model="regForm['规格型号']" /></label>
          <label><span>供应商</span><input v-model="regForm['供应商']" /></label>
          <label><span>承运方</span><input v-model="regForm['承运方']" /></label>
          <label><span>接收人</span><input v-model="regForm['接收人']" placeholder="设备到货后谁去开箱" /></label>
          <label><span>送货数量 *</span><input v-model.number="regForm['送货数量']" type="number" min="1" /></label>
          <label><span>送货日期 *</span><input v-model="regForm['送货日期']" type="date" /></label>
          <label><span>质保月数</span><input v-model.number="regForm['质保月数']" type="number" min="1" /></label>
        </div>
        <div class="modal-foot">
          <button class="btn" type="button" @click="registerOpen = false">取消</button>
          <button class="btn primary" type="button" :disabled="saving" @click="submitRegister">
            {{ saving ? '提交中…' : '登记' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批次详情抽屉：与列表读同一份数据 -->
    <div v-if="detail" class="drawer-mask" @click.self="closeDetail">
      <aside class="drawer">
        <header class="drawer-head">
          <div>
            <h3>{{ detail['到货批号'] }}</h3>
            <p>
              送货单 {{ detail['送货单号'] || '—' }} ·
              <span :class="['status-tag', statusClass(detail.status)]">{{ detail.status }}</span>
              <em v-if="detail['存量批次']" class="legacy-tag">存量回填（沿用历史判定）</em>
            </p>
          </div>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>

        <section class="detail-step">
          <h4>状态流转</h4>
          <ol class="step-bar">
            <li v-for="(s, idx) in statuses" :key="s" :class="{ done: stepIndex(detail.status) >= idx, current: detail.status === s }">
              <span>{{ idx + 1 }}</span>{{ s }}
            </li>
          </ol>
        </section>

        <section class="detail-block">
          <h4>批次信息</h4>
          <div class="kv-grid">
            <span><b>备件</b>{{ detail['备件编号'] }} · {{ detail['备件名称'] }}（{{ detail['规格型号'] || '—' }}）</span>
            <span><b>供应商 / 承运</b>{{ detail['供应商'] || '—' }} / {{ detail['承运方'] || '—' }}</span>
            <span><b>接收人</b>{{ detail['接收人'] || '—' }}</span>
            <span><b>送货数量</b>{{ detail['送货数量'] }}</span>
            <span><b>送货日期</b>{{ detail['送货日期'] }}</span>
            <span><b>质保期限</b>{{ detail['质保月数'] }} 个月</span>
            <span><b>入库数量</b>{{ detail['入库数量'] || 0 }}</span>
            <span><b>入库日期</b>{{ detail['入库日期'] || '—' }}</span>
            <span><b>质保起算日</b>{{ detail['质保起算日'] || '入库后按入库当日起算' }}</span>
            <span><b>质保截止日</b>{{ detail['质保截止日'] || '—' }}</span>
          </div>
        </section>

        <section class="detail-block">
          <h4>开箱记录</h4>
          <template v-if="canEditUnboxing">
            <div class="form-grid">
              <label><span>开箱人 *</span><input v-model="unboxingForm['开箱人']" /></label>
              <label><span>开箱日期 *</span><input v-model="unboxingForm['开箱日期']" type="date" /></label>
              <label>
                <span>外观检查 *</span>
                <select v-model="unboxingForm['外观检查']">
                  <option value="">请选择</option>
                  <option>完好</option><option>破损</option><option>受潮</option>
                </select>
              </label>
              <label>
                <span>附件核对 *</span>
                <select v-model="unboxingForm['附件核对']">
                  <option value="">请选择</option>
                  <option>一致</option><option>短缺</option><option>错发</option>
                </select>
              </label>
              <label class="full"><span>开箱备注</span><input v-model="unboxingForm['开箱备注']" /></label>
            </div>
            <button class="btn primary" type="button" :disabled="saving" @click="saveUnboxing">保存开箱记录</button>
          </template>
          <table v-else-if="hasUnboxing" class="mini-table">
            <tbody>
              <tr v-for="f in unboxingFields" :key="f">
                <th>{{ f }}</th><td>{{ detail['开箱记录'][f] || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted-text">存量批次沿用历史验收判定，未补开箱记录。</p>
        </section>

        <section class="detail-block">
          <h4>验收结论</h4>
          <template v-if="detail.status === '验收中' && unboxingComplete">
            <div class="form-grid">
              <label>
                <span>结论 *</span>
                <select v-model="conclusionForm['结论']">
                  <option value="">请选择</option>
                  <option>合格</option><option>不合格</option>
                </select>
              </label>
              <label><span>验收人 *</span><input v-model="conclusionForm['验收人']" /></label>
              <label><span>验收日期</span><input v-model="conclusionForm['验收日期']" type="date" /></label>
              <label v-if="conclusionForm['结论'] === '合格'">
                <span>合格数量（≤{{ detail['送货数量'] }}）</span>
                <input v-model.number="conclusionForm['合格数量']" type="number" min="1" :max="detail['送货数量']" />
              </label>
              <label v-if="conclusionForm['结论'] === '不合格'" class="full">
                <span>处理方式 *（退货 / 换货 / 索赔）</span>
                <input v-model="conclusionForm['处理方式']" placeholder="如：退货并索赔" />
              </label>
              <label class="full"><span>结论说明</span><input v-model="conclusionForm['结论说明']" /></label>
            </div>
            <button class="btn primary" type="button" :disabled="saving" @click="saveConclusion">提交验收结论</button>
          </template>
          <table v-else-if="hasConclusion" class="mini-table">
            <tbody>
              <tr v-for="f in conclusionFields" :key="f">
                <th>{{ f }}</th><td>{{ detail['验收结论'][f] || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted-text">
            {{ !unboxingComplete ? '开箱记录没填完，暂不能下结论或入库。' : '尚未填写验收结论。' }}
          </p>
        </section>

        <section class="detail-block">
          <h4>入库与质保</h4>
          <template v-if="canStockIn">
            <div class="form-grid">
              <label>
                <span>入库数量（≤{{ qualifiedQty }}）</span>
                <input v-model.number="stockForm['入库数量']" type="number" min="1" :max="qualifiedQty" />
              </label>
              <label>
                <span>入库日期</span>
                <input v-model="stockForm['入库日期']" type="date" />
              </label>
            </div>
            <p class="muted-text">质保自实际入库当日起算（不是送货日）；入库数量会累加到备件当前存量。</p>
            <button class="btn primary" type="button" :disabled="saving" @click="confirmStockIn">确认入库</button>
          </template>
          <p v-else class="muted-text">
            {{ detail.status === '验收中' ? '开箱记录与合格结论齐备后才能确认入库。' : '该批次当前状态无需入库操作。' }}
          </p>
        </section>

        <section class="detail-block">
          <h4>可执行动作</h4>
          <div class="action-row">
            <button
              v-for="action in availableActions(detail.status)"
              :key="action"
              class="btn"
              :class="{ primary: action === '质保生效' }"
              type="button"
              :disabled="saving"
              @click="runStatusAction(action)"
            >
              {{ action }}
            </button>
          </div>
        </section>

        <section class="detail-block">
          <h4>补充记录</h4>
          <ul v-if="detail['补充记录'] && detail['补充记录'].length" class="note-list">
            <li v-for="(note, i) in detail['补充记录']" :key="i">
              <time>{{ note['时间'] }}</time>{{ note['内容'] }}
            </li>
          </ul>
          <p v-else class="muted-text">暂无补充记录。</p>
          <div class="inline-add">
            <input v-model="supplementText" placeholder="追加一条补充说明（不改动主记录判定）" />
            <button class="btn" type="button" :disabled="saving || !supplementText.trim()" @click="addSupplement">追加</button>
          </div>
        </section>

        <section class="detail-block">
          <h4>流转记录</h4>
          <ol class="timeline">
            <li v-for="(log, i) in detail['流转记录']" :key="i">
              <time>{{ log['时间'] }}</time>
              <b>{{ log['动作'] }}</b>
              <span>{{ log['说明'] }}</span>
            </li>
          </ol>
        </section>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, any>

const ENDPOINT = '/api/arrival'
const statuses = ['待验收', '验收中', '已入库', '质保生效'] as const
const statusActions: Record<string, string[]> = {
  待验收: ['开始验收'],
  验收中: [],
  已入库: ['再验收', '质保生效'],
  质保生效: ['再验收'],
}
const unboxingFields = ['开箱人', '开箱日期', '外观检查', '附件核对', '开箱备注']
const conclusionFields = ['结论', '验收人', '验收日期', '合格数量', '不合格数量', '处理方式', '结论说明']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const message = ref('')
const saving = ref(false)
const filters = reactive({ keyword: '', status: '' })

const registerOpen = ref(false)
const detail = ref<Row | null>(null)
const supplementText = ref('')

const today = () => new Date().toISOString().slice(0, 10)

const regForm = reactive<Record<string, any>>({
  到货批号: '', 送货单号: '', 备件编号: '', 备件名称: '', 规格型号: '',
  供应商: '', 承运方: '', 接收人: '', 送货数量: undefined, 送货日期: today(), 质保月数: 12,
})
const unboxingForm = reactive<Record<string, string>>({
  开箱人: '', 开箱日期: '', 外观检查: '', 附件核对: '', 开箱备注: '',
})
const conclusionForm = reactive<Record<string, any>>({
  结论: '', 验收人: '', 验收日期: '', 合格数量: undefined, 不合格数量: 0, 处理方式: '', 结论说明: '',
})
const stockForm = reactive<Record<string, any>>({ 入库数量: undefined, 入库日期: today() })

const stats = computed(() => {
  const waiting = rows.value.filter((r) => r.status === '待验收').length
  const inspecting = rows.value.filter((r) => r.status === '验收中').length
  const stocked = rows.value.filter((r) => r.status === '已入库' || r.status === '质保生效').length
  return [
    { label: '待验收批次', value: waiting },
    { label: '验收中批次', value: inspecting },
    { label: '已入库批次', value: stocked },
    { label: '批次总数', value: total.value },
  ]
})

const hasUnboxing = computed(() => {
  const rec = detail.value?.['开箱记录']
  return !!rec && typeof rec === 'object' && Object.keys(rec as object).length > 0
})
const unboxingComplete = computed(() =>
  unboxingFields.slice(0, 4).every((f) => String((detail.value?.['开箱记录'] as Row | undefined)?.[f] ?? '').trim()),
)
const hasConclusion = computed(() => {
  const rec = detail.value?.['验收结论']
  return !!rec && typeof rec === 'object' && Object.keys(rec as object).length > 0
})
const canEditUnboxing = computed(() => {
  const s = detail.value?.status
  return s === '待验收' || s === '验收中'
})
const qualifiedQty = computed(() => Number((detail.value?.['验收结论'] as Row | undefined)?.['合格数量'] ?? detail.value?.['送货数量'] ?? 0))
const canStockIn = computed(() => detail.value?.status === '验收中' && unboxingComplete.value && hasConclusion.value
  && (detail.value?.['验收结论'] as Row | undefined)?.['结论'] === '合格')

function stepIndex(status: any): number {
  return statuses.indexOf(status as typeof statuses[number])
}
function statusClass(status: any): string {
  return `st-${stepIndex(status)}`
}
function availableActions(status: any): string[] {
  return statusActions[String(status)] ?? []
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export/all`, '_blank')
}

function openRegister() {
  registerOpen.value = true
}

async function submitRegister() {
  errorMessage.value = ''
  saving.value = true
  try {
    const response = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values: { ...regForm } }) })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '到货登记失败')
    }
    registerOpen.value = false
    message.value = payload.message
    await reload()
    if (payload.entry) {
      await openDetail((payload.entry as Row).id as number)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '到货登记失败'
  } finally {
    saving.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.status) params.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) throw new Error('到货列表读取失败')
    const payload = await response.json()
    rows.value = (payload.items ?? []) as Row[]
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '到货列表读取失败'
  }
}

async function openDetail(id: number) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) throw new Error('批次详情读取失败')
    detail.value = (await response.json()) as Row
    hydrateForms()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批次详情读取失败'
  }
}

function closeDetail() {
  detail.value = null
}

function hydrateForms() {
  if (!detail.value) return
  const unboxing = (detail.value['开箱记录'] ?? {}) as Row
  for (const f of unboxingFields) unboxingForm[f] = String(unboxing[f] ?? '')
  const conclusion = (detail.value['验收结论'] ?? {}) as Row
  conclusionForm['结论'] = String(conclusion['结论'] ?? '')
  conclusionForm['验收人'] = String(conclusion['验收人'] ?? '')
  conclusionForm['验收日期'] = String(conclusion['验收日期'] ?? today())
  conclusionForm['合格数量'] = (conclusion['合格数量'] as number) ?? Number(detail.value['送货数量'])
  conclusionForm['处理方式'] = String(conclusion['处理方式'] ?? '')
  conclusionForm['结论说明'] = String(conclusion['结论说明'] ?? '')
  stockForm['入库数量'] = (conclusion['合格数量'] as number) ?? Number(detail.value['送货数量'])
  stockForm['入库日期'] = today()
}

async function postAction(body: Record<string, unknown>, successHint: string) {
  if (!detail.value) return
  saving.value = true
  errorMessage.value = ''
  try {
    const id = detail.value.id
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '操作未生效')
    }
    message.value = payload.message || successHint
    await reload()
    await openDetail(id as number)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作未生效'
  } finally {
    saving.value = false
  }
}

function saveUnboxing() {
  void postAction({ values: { action: '填写开箱记录', ...unboxingForm } }, '开箱记录已保存')
}
function saveConclusion() {
  void postAction({ values: { action: '填写验收结论', ...conclusionForm } }, '验收结论已提交')
}
function confirmStockIn() {
  void postAction({ values: { action: '确认入库', ...stockForm } }, '已确认入库')
}
function runStatusAction(action: string) {
  if (action === '再验收') {
    const ok = window.confirm('再验收会把批次退回验收中，并回滚此前已入库存与质保起算日，确定继续？')
    if (!ok) return
  }
  void postAction({ values: { action } }, `${action}已生效`)
}

async function addSupplement() {
  if (!detail.value || !supplementText.value.trim()) return
  saving.value = true
  try {
    const id = detail.value.id
    const response = await request(`${ENDPOINT}/${id}/supplements`, {
      method: 'POST',
      body: JSON.stringify({ values: { content: supplementText.value.trim() } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) throw new Error(payload.message || '补充记录追加失败')
    supplementText.value = ''
    message.value = payload.message
    await reload()
    await openDetail(id as number)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '补充记录追加失败'
  } finally {
    saving.value = false
  }
}

onMounted(reload)
</script>

<style scoped>
.ok-text { color: #087443; }
.status-tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-style: normal; font-size: 12px; }
.st-0 { background: #e8eefc; color: #1f4db8; }
.st-1 { background: #fdf0d8; color: #b45309; }
.st-2 { background: #dcf5e7; color: #087443; }
.st-3 { background: #e3f2fd; color: #0f5e9c; }
.legacy-tag { color: var(--muted); font-size: 12px; margin-left: 6px; }
.filter-item select { padding: 4px 6px; }
.modal-mask, .drawer-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 41, 0.45);
  z-index: 20; display: flex; align-items: center; justify-content: center;
}
.modal { background: #fff; border-radius: 10px; padding: 18px 20px; width: 720px; max-height: 88vh; overflow: auto; }
.modal h3, .drawer h3 { margin: 0 0 4px; }
.modal-hint { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; margin-bottom: 12px; }
.form-grid label span, .form-grid .full { display: block; }
.form-grid label span { font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.form-grid input, .form-grid select { width: 100%; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; }
.form-grid .full { grid-column: 1 / -1; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; }
.drawer-mask { justify-content: flex-end; }
.drawer {
  background: #fff; width: 620px; max-width: 96vw; height: 100%; overflow: auto;
  padding: 16px 20px; box-shadow: -8px 0 24px rgba(15, 23, 41, 0.18);
}
.drawer-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.drawer-head p { margin: 6px 0 0; font-size: 13px; color: var(--muted); }
.detail-block, .detail-step { border-top: 1px solid var(--border); padding: 12px 0; }
.detail-block h4, .detail-step h4 { margin: 0 0 8px; font-size: 14px; }
.kv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 14px; font-size: 13px; }
.kv-grid b { display: block; color: var(--muted); font-weight: normal; font-size: 12px; }
.step-bar { list-style: none; display: flex; margin: 0; padding: 0; gap: 0; }
.step-bar li { flex: 1; position: relative; text-align: center; font-size: 12px; color: var(--muted); padding-top: 22px; }
.step-bar li span {
  position: absolute; top: 0; left: 50%; transform: translateX(-50%);
  width: 20px; height: 20px; border-radius: 50%; background: #e2e8f0; color: #64748b;
  display: flex; align-items: center; justify-content: center; font-size: 12px;
}
.step-bar li.done { color: #087443; }
.step-bar li.done span { background: #087443; color: #fff; }
.step-bar li.current span { outline: 3px solid #b6e3c8; }
.mini-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.mini-table th, .mini-table td { border: 1px solid var(--border); padding: 5px 8px; text-align: left; }
.mini-table th { width: 110px; background: #f8fafc; color: var(--muted); font-weight: normal; }
.muted-text { color: var(--muted); font-size: 12px; }
.action-row { display: flex; gap: 8px; flex-wrap: wrap; }
.note-list, .timeline { margin: 0; padding: 0; list-style: none; }
.note-list li, .timeline li { font-size: 13px; padding: 4px 0; border-bottom: 1px dashed #eef2f7; }
.note-list time, .timeline time { color: var(--muted); font-size: 12px; margin-right: 8px; }
.timeline b { margin-right: 8px; font-weight: 600; }
.inline-add { display: flex; gap: 8px; margin-top: 8px; }
.inline-add input { flex: 1; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; }
</style>
