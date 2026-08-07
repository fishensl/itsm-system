<template>
  <div class="group-tree">
    <template v-for="node in nodes" :key="nodeKey(node)">
      <!-- 叶子行：完全由页面自定义渲染 -->
      <slot v-if="isLeaf(node)" name="leaf" :node="node" />
      <!-- 分组行：名称 + 徽标 + 展开 -->
      <div v-else class="tree-block">
        <div class="tree-row" @click="toggle(nodeKey(node))">
          <el-icon class="collapse-arrow" :class="{ expanded: isExpanded(nodeKey(node)) }">
            <ArrowRight />
          </el-icon>
          <el-icon :color="groupColor"><OfficeBuilding /></el-icon>
          <span class="tree-name">{{ node.name }}</span>
          <el-tag v-if="badge(node) > 0" size="small" type="info" class="tree-badge">{{ badge(node) }}</el-tag>
          <span class="row-actions" @click.stop>
            <slot name="actions" :node="node" />
          </span>
        </div>
        <div v-show="isExpanded(nodeKey(node))" class="tree-children">
          <GroupTree
            :nodes="node.children || []"
            :depth="depth + 1"
            :leaf-depth="leafDepth"
            :badge-key="badgeKey"
            :default-expanded="defaultExpanded"
          >
            <template #leaf="scope">
              <slot name="leaf" :node="scope.node" />
            </template>
            <template #actions="scope">
              <slot name="actions" :node="scope.node" />
            </template>
          </GroupTree>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ArrowRight, OfficeBuilding } from '@element-plus/icons-vue'

defineOptions({ name: 'GroupTree' })

defineSlots<{
  leaf(props: { node: any }): unknown
  actions(props: { node: any }): unknown
}>()

interface TreeNode {
  id?: number | null
  name: string
  children?: any[]
  [key: string]: unknown
}

const props = withDefaults(defineProps<{
  nodes: TreeNode[]
  /** 叶子节点所在深度（0 起：0=根分组…leafDepth=叶子） */
  leafDepth: number
  /** 分组行徽标字段名 */
  badgeKey?: string
  depth?: number
  /** 默认展开深度（0=全折叠） */
  defaultExpanded?: number
}>(), { depth: 0, badgeKey: '', defaultExpanded: 0 })

const expanded = ref<Set<string>>(new Set())

function nodeKey(node: TreeNode): string {
  return `${node.name}:${node.id ?? ''}:${props.depth}`
}

function isLeaf(node: TreeNode): boolean {
  return props.depth >= props.leafDepth
}

function isExpanded(key: string) {
  return expanded.value.has(key)
}

function toggle(key: string) {
  const next = new Set(expanded.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expanded.value = next
}

function badge(node: TreeNode): number {
  return props.badgeKey ? (Number(node[props.badgeKey]) || 0) : 0
}

const groupColor = '#2563eb'

watch(
  () => [props.nodes, props.defaultExpanded],
  () => {
    if (props.depth < props.defaultExpanded) {
      const next = new Set(expanded.value)
      for (const n of props.nodes) next.add(nodeKey(n))
      expanded.value = next
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.group-tree { min-height: 40px; }
.tree-block { border: 1px solid var(--itsm-border); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.tree-row {
  display: flex; align-items: center; gap: 8px; padding: 9px 12px;
  background: var(--el-fill-color-light); font-weight: 600; font-size: 13px;
  cursor: pointer;
}
.tree-row:hover { background: var(--el-fill-color); }
.collapse-arrow { transition: transform 0.2s; font-size: 13px; color: var(--itsm-text-muted); }
.collapse-arrow.expanded { transform: rotate(90deg); }
.tree-name { flex-shrink: 0; }
.tree-badge { margin-left: auto; }
.row-actions { margin-left: auto; display: flex; gap: 4px; align-items: center; }
.tree-children { padding: 4px 8px 4px 14px; }
</style>
