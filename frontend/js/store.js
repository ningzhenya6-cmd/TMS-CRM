/**
 * TMS 全局响应式 Store
 * 使用 Vue 3 响应式 API，消除 window.__ 全局变量
 */
(function () {
  const TMSStore = Vue.reactive({
    leadId: null,       // 当前查看的线索/学生 ID
    fromView: null,     // 导航来源（用于返回）
    growthLeadId: null, // 成长档案预选学生 ID（从客户详情跳转时传入）
    leadsPage: 1,       // 资源列表当前页码
    leadsList: [],      // 资源列表当前页的线索（用于上下条导航）
    leadsTotal: 0,      // 资源列表总条数
    leadsFilters: {},   // 资源列表当前筛选条件
    overdueCount: 0,    // 超期跟进数量（侧边栏角标用）
  });

  // 导出到全局
  window.TMSStore = TMSStore;
})();
