<template>
  <div id="app">
    <router-view v-slot="{ Component, route }">
      <transition name="page" :css="!routeTransitionActive">
        <component :is="Component" :key="route.path" />
      </transition>
    </router-view>
  </div>
</template>

<script setup>
import { routeTransitionActive } from '@/composables/useRouteTransition'
</script>

<style lang="scss">
// 全局样式已在 main.js 中导入
</style>
