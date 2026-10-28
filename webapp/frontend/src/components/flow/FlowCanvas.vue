<script setup lang="ts">
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { VueFlow, useVueFlow, type Edge, type NodeMouseEvent } from '@vue-flow/core'
import { MiniMap } from '@vue-flow/minimap'
import { computed, nextTick, watch } from 'vue'

import FlowCard from '@/components/flow/FlowCard.vue'
import { focus, type CardNode } from '@/components/flow/graphs'

const props = defineProps<{ id: string; nodes: CardNode[]; edges: Edge[] }>()
const selected = defineModel<string | null>('selected', { default: null })

const { fitView } = useVueFlow(props.id)
const view = computed(() => focus(props.nodes, props.edges, selected.value))

// Re-fit when the graph's shape changes (new step results), not on selection.
watch(
  () => props.nodes.map((n) => n.id).join('|'),
  async () => {
    await nextTick()
    fitView({ padding: 0.08 })
  },
)

function onNodeClick({ node }: NodeMouseEvent) {
  if (node.id.startsWith('lane:')) return
  selected.value = selected.value === node.id ? null : node.id
}
</script>

<template>
  <VueFlow
    :id="id"
    :nodes="view.nodes"
    :edges="view.edges"
    :nodes-connectable="false"
    :min-zoom="0.15"
    fit-view-on-init
    class="h-full w-full"
    @node-click="onNodeClick"
    @pane-click="selected = null"
  >
    <template #node-card="{ data, id: nodeId }">
      <FlowCard :data="data" :selected="nodeId === selected" />
    </template>
    <Background :gap="20" pattern-color="#e4e3df" />
    <Controls :show-interactive="false" />
    <MiniMap pannable zoomable :node-color="(n) => (n.data as CardNode['data'])?.color ?? '#b8b7b1'" />
  </VueFlow>
</template>
