/**
 * TMS 全局响应式 Store
 * 使用 Vue 3 响应式 API，消除 window.__ 全局变量
 */
(function () {
  const TMSStore = Vue.reactive({
    leadId: null,       // 当前查看的线索/学生 ID
    fromView: null,     // 导航来源（用于返回）
  });

  // 导出到全局
  window.TMSStore = TMSStore;
})();
