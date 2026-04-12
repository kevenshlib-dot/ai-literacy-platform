import { ref } from 'vue'
import { message } from 'ant-design-vue'
import request from '@/utils/request'

const llmStatus = ref<any>(null)
const checked = ref(false)

/**
 * Check if a specific LLM module is configured.
 * Shows a warning message if not configured.
 * Returns true if configured, false if not.
 */
export async function checkLLMModule(moduleKey: string, moduleName: string): Promise<boolean> {
  if (!checked.value) {
    try {
      llmStatus.value = await request.get('/system/llm-status')
      checked.value = true
    } catch {
      // Non-admin or network error — assume configured to avoid blocking
      return true
    }
  }

  const mod = llmStatus.value?.modules?.[moduleKey]
  if (mod && !mod.configured) {
    message.warning(
      `"${moduleName}"功能需要配置大模型才能正常工作，当前将使用规则降级模式（结果可能不准确）。请前往"系统配置"页面设置模型。`,
      6,
    )
    return false
  }
  return true
}

/**
 * Reset cached status (call after config changes).
 */
export function resetLLMStatusCache() {
  checked.value = false
  llmStatus.value = null
}
