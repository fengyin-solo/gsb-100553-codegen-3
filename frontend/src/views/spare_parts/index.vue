<template>
  <section class="page" data-module="spare_parts">
    <header class="page-head">
      <div>
        <h2>备品备件管理</h2>
        <p class="page-desc">维护备件物料，围绕备件编号、备件名称、规格型号、适用设备做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记备件物料</button>
        <button class="btn" type="button" @click="exportRows">导出备品备件清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="todo-panel">
      <header class="todo-head">
        <h3>验收联动待办</h3>
        <div class="todo-actions">
          <label class="todo-filter">
            <input type="checkbox" :checked="todoPendingOnly" @change="toggleTodoFilter" />
            只看待处理
          </label>
          <button class="btn" type="button" @click="reloadTodos">刷新待办</button>
        </div>
      </header>
      <table class="data-table todo-table">
        <thead>
          <tr><th>备件</th><th>到货批号</th><th>待办事项</th><th>触发环节</th><th>到期日</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="todo in todos" :key="String(todo.id)" :class="{ abnormal: todo.abnormal && todo.pending }">
            <td>{{ todo['备件编号'] }} · {{ todo['备件名称'] }}</td>
            <td>{{ todo['到货批号'] }}</td>
            <td>{{ todo['事项'] }}</td>
            <td>{{ todo['触发环节'] }}</td>
            <td>{{ todo['到期日'] || '—' }}</td>
            <td><span :class="['todo-state', todo.pending ? 'open' : 'done']">{{ todo['状态'] }}</span></td>
          </tr>
          <tr v-if="!todos.length">
            <td colspan="6" class="empty-state">暂无验收联动待办</td>
          </tr>
        </tbody>
      </table>
    </section>

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
          <td :colspan="columns.length + 1" class="empty-state">暂无备品备件数据，可先登记备件物料</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条备品备件记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/spare_parts'
const columns = ["备件编号", "备件名称", "规格型号", "适用设备", "安全存量", "当前存量", "存放位置", "备件状态"]
const actions = ["入库登记", "领用出库", "标记废弃"]
const statuses = ["存量充足", "低于安全量", "已用尽", "已废弃"]
const stats = [{"label": "备件种类数", "value": 0}, {"label": "低存量备件", "value": 0}, {"label": "本月领用数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

// 到货验收结论同步过来的待办：与验收台账同源，动作在到货验收页执行。
type Todo = Record<string, string | number | boolean | null>
const todos = ref<Todo[]>([])
const todoPendingOnly = ref(false)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function reloadTodos() {
  try {
    const suffix = todoPendingOnly.value ? '?pending_only=true' : ''
    const response = await request(`${ENDPOINT}/todos${suffix}`)
    if (!response.ok) throw new Error('验收待办读取失败')
    const payload = await response.json()
    todos.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '验收待办读取失败'
  }
}

function toggleTodoFilter(event: Event) {
  todoPendingOnly.value = (event.target as HTMLInputElement).checked
  void reloadTodos()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '备件物料登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('备品备件动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '备品备件操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('备件物料列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '备品备件列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadTodos()
})
</script>

<style scoped>
.todo-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.todo-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.todo-head h3 { margin: 0; font-size: 14px; }
.todo-actions { display: flex; align-items: center; gap: 10px; }
.todo-filter { font-size: 12px; color: var(--muted); display: flex; align-items: center; gap: 4px; }
.todo-table { margin-top: 4px; }
.todo-table tr.abnormal td { background: #fef3f2; }
.todo-state { padding: 1px 8px; border-radius: 10px; font-size: 12px; font-style: normal; }
.todo-state.open { background: #fdf0d8; color: #b45309; }
.todo-state.done { background: #dcf5e7; color: #087443; }
</style>
