<template>
  <a-config-provider :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
import { theme } from 'ant-design-vue'

const themeConfig = {
  token: {
    colorPrimary: '#1F4E79',
    borderRadius: 6,
    colorBgContainer: '#ffffff',
  },
  algorithm: theme.defaultAlgorithm,
}
</script>
