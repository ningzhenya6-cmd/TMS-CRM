/**
 * TMS — Vue 3 主应用
 * 所有组件通过 props 通信
 */
/* eslint-disable no-unused-vars */

/* ─── 工具函数 ─── */
const downloadCSV = async (url, filename) => {
  const res = await API.getRaw(url);
  if (!res) { toast('导出失败', 'error'); return; }
  const blob = new Blob([res], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename || 'export.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
};
const esc = (s) => s || '-';
const statusBadge = (s) => {
  const m = {
    pending: ['bg-yellow-100 text-yellow-800', '待分配'],
    assigned: ['bg-blue-100 text-blue-800', '已分配'],
    following: ['bg-indigo-100 text-indigo-800', '跟进中'],
    trial: ['bg-purple-100 text-purple-800', '试听中'],
    enrolled: ['bg-green-100 text-green-800', '已签约'],
    closed: ['bg-gray-100 text-gray-600', '已关闭'],
    lost: ['bg-red-100 text-red-800', '已流失'],
  };
  const [cls, label] = m[s] || ['bg-gray-100 text-gray-600', s];
  return `<span class="inline-block px-2.5 py-0.5 rounded-full text-[.7rem] font-medium ${cls}">${label}</span>`;
};
const roleLabel = (r) => ({
  admin: '管理员', supervisor: '超级主管', cs: '课程顾问',
  consultant: '高级顾问', coordinator: '教班主任', academic: '学管师', tutor: '老师',
}[r] || r);

const _stripTS = (s) => (s || '').replace(/\[\d{1,2}:\d{2}(?::\d{2})?(?:-\d{1,2}:\d{2}(?::\d{2})?)?\]/g, '').replace(/\s{2,}/g, ' ').trim();
const toast = (msg, type) => {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  const bg = type === 'error' ? 'bg-red-50 text-red-700 border-l-4 border-red-500'
    : type === 'success' ? 'bg-green-50 text-green-700 border-l-4 border-green-500'
    : 'bg-white text-gray-800 border-l-4 border-indigo-500';
  el.className = 'toast-msg ' + bg;
  el.innerHTML = msg;
  c.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
};

/* ─── 前端权限辅助 ─── */
const CAN = {
  'lead:create':       ['cs', 'consultant', 'admin', 'supervisor'],
  'lead:edit':         ['cs', 'consultant', 'admin', 'supervisor'],
  'lead:edit_any':     ['admin', 'supervisor'],
  'lead:delete':       ['admin', 'supervisor'],
  'lead:assign':       ['admin', 'supervisor', 'cs'],
  'lead:batch_op':     ['admin', 'supervisor'],
  'schedule:manage':   ['coordinator', 'admin', 'supervisor'],
  'trial:manage':      ['coordinator', 'admin', 'supervisor'],
  'trial:feedback':    ['cs', 'consultant', 'admin', 'supervisor'],
  'contract:manage':   ['coordinator', 'admin', 'supervisor'],
  'package:manage':    ['coordinator', 'academic', 'admin', 'supervisor'],
  'teacher:manage':    ['coordinator', 'admin', 'supervisor'],
  'user:manage':       ['admin', 'supervisor'],
  'finance:view':      ['admin', 'supervisor', 'cs', 'consultant'],
  'lead:adjust_coordinator': ['admin', 'supervisor', 'cs', 'consultant'],
  'consulting:view':  ['cs', 'consultant', 'academic', 'admin', 'supervisor'],
  'consulting:create': ['cs', 'consultant', 'academic', 'admin', 'supervisor'],
};
function canUser(role, permission) {
  const allowed = CAN[permission] || [];
  if (allowed === '*') return true;
  return allowed.includes(role);
}

/* ─── 菜单项 ─── */
const ROLE_MENU = [
  { id: 'dashboard', label: '工作台', icon: 'bi-grid-1x2-fill', roles: '*', view: 'dashboard' },
  { id: 'leads', label: '资源管理', icon: 'bi-people-fill', roles: ['admin', 'supervisor', 'cs', 'consultant'], view: 'leads' },
  { id: 'quick-add', label: '快速录入', icon: 'bi-plus-circle-fill', roles: ['cs', 'consultant', 'admin', 'supervisor'], view: 'quick-add' },
  { id: 'followup-plan', label: '跟进计划', icon: 'bi-calendar-check', roles: ['cs', 'consultant', 'academic', 'admin', 'supervisor'], view: 'followup-plan' },
  { id: 'divider1', divider: true },
  { id: 'trials', label: '试听管理', icon: 'bi-ear', roles: ['coordinator', 'admin', 'supervisor', 'cs', 'consultant'], view: 'trials' },
  { id: 'coordinator', label: '教班主任台', icon: 'bi-speedometer2', roles: ['coordinator', 'admin', 'supervisor'], view: 'coordinator' },
  { id: 'assignment', label: '分配工作台', icon: 'bi-diagram-3-fill', roles: ['admin', 'supervisor', 'cs', 'consultant'], view: 'assignment' },
  { id: 'schedules', label: '排课管理', icon: 'bi-calendar-week', roles: ['coordinator', 'admin', 'supervisor'], view: 'schedules' },
  { id: 'signing', label: '签约管理', icon: 'bi-journal-check', roles: ['coordinator', 'cs', 'consultant', 'academic', 'admin', 'supervisor'], view: 'signing' },
  { id: 'consulting', label: '学业分析', icon: 'bi-clipboard-data', roles: ['cs', 'consultant', 'academic', 'admin', 'supervisor'], view: 'consulting' },
  { id: 'teachers', label: '师资管理', icon: 'bi-person-video3', roles: ['coordinator', 'admin', 'supervisor'], view: 'teachers' },
  { id: 'divider2', divider: true },
  { id: 'pool', label: '公海池', icon: 'bi-water', roles: ['admin', 'supervisor', 'cs', 'consultant'], view: 'pool' },
  { id: 'finance', label: '财务管理', icon: 'bi-currency-dollar', roles: ['admin', 'supervisor'], view: 'finance' },
];

/* ════════════════════════════════════════
   根组件 — 登录状态、侧边栏、路由
   ════════════════════════════════════════ */
const app = Vue.createApp({
  data() {
    return {
      user: JSON.parse(localStorage.getItem('tms_user') || 'null'),
      currentView: 'dashboard',
      sidebarOpen: false,
      loading: false,
      loginForm: { username: '', password: '' },
      loginError: '',
    };
  },
  computed: {
    menuItems() { return ROLE_MENU; },
    currentViewTitle() {
      const item = ROLE_MENU.find(m => m.view === this.currentView);
      return item ? item.label : 'TMS 学管系统';
    },
  },
  methods: {
    hasRole(roles) {
      if (!this.user) return false;
      if (roles === '*') return true;
      return roles.includes(this.user.role);
    },
    roleLabel(r) { return roleLabel(r); },
    statusBadge(s) { return statusBadge(s); },
    switchView(view) { this.currentView = view; },
    async handleLogin() {
      this.loginError = '';
      this.loading = true;
      const res = await API.post('/auth/login', this.loginForm);
      this.loading = false;
      if (res.error) { this.loginError = res.error; return; }
      const token = res.data.token;
      const user = res.data.user;
      localStorage.setItem('tms_token', token);
      localStorage.setItem('tms_user', JSON.stringify(user));
      this.user = user;
      toast('登录成功，欢迎回来', 'success');
    },
    handleLogout() {
      localStorage.removeItem('tms_token');
      localStorage.removeItem('tms_user');
      this.user = null;
      this.currentView = 'dashboard';
    },
  },
  created() {
    const token = localStorage.getItem('tms_token');
    if (token && this.user) {
      API.get('/auth/me').then(res => {
        if (res.error) {
          localStorage.removeItem('tms_token');
          localStorage.removeItem('tms_user');
          this.user = null;
        }
      });
    }
  },
});

/* ════════════════════════════════════════
   Dashboard 组件
   ════════════════════════════════════════ */
app.component('include-dashboard', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-dashboard',
  data() {
    return { stats: {}, recentLeads: [], overdueCount: 0 };
  },
  computed: {
    statCards() {
      const s = this.stats || {};
      const role = this.user?.role;
      if (role === 'admin' || role === 'supervisor') {
        return [
          { label: '待分配资源', value: s.pending_unassigned ?? 0, sub: '点击分配线索', icon: 'bi-people', view: 'assignment' },
          { label: '今日排课', value: s.today_followups ?? 0, sub: '查看课程安排', icon: 'bi-calendar-week', view: 'schedules' },
          { label: '待跟进', value: s.overdue ?? 0, sub: '查看跟进计划', icon: 'bi-chat-dots', view: 'followup-plan' },
          { label: '公海池', value: s.pool_count ?? 0, sub: '查看公海线索', icon: 'bi-water', view: 'pool' },
        ];
      } else if (role === 'cs' || role === 'consultant') {
        return [
          { label: '我的资源', value: s.my_total ?? 0, sub: '点击管理线索', icon: 'bi-people', view: 'leads' },
          { label: '跟进中', value: s.my_following ?? 0, sub: '正在跟进', icon: 'bi-chat-dots', view: 'leads' },
          { label: '已签约', value: s.my_enrolled ?? 0, sub: '查看签约学生', icon: 'bi-mortarboard-fill', view: 'signing' },
          { label: '逾期跟进', value: s.overdue ?? 0, sub: '需要尽快处理', icon: 'bi-exclamation-triangle', view: 'followup-plan' },
        ];
      } else if (role === 'academic') {
        return [
          { label: '我的学生', value: s.my_enrolled ?? 0, sub: '查看签约学生', icon: 'bi-mortarboard-fill', view: 'signing' },
          { label: '待续费', value: s.need_renewal ?? 0, sub: '课时即将用完', icon: 'bi-exclamation-triangle', view: 'signing' },
          { label: '跟进中', value: s.my_following ?? 0, sub: '正在跟进', icon: 'bi-chat-dots', view: 'leads' },
          { label: '逾期跟进', value: s.overdue ?? 0, sub: '需要尽快处理', icon: 'bi-exclamation-triangle', view: 'followup-plan' },
        ];
      }
      return [];
    },
  },
  methods: {
    async load() {
      const res = await API.get('/dashboard');
      if (res.error) return;
      this.stats = res.data || {};
      this.overdueCount = res.data?.overdue || 0;
      this.pendingContact = res.data?.pending_contact || 0;
      const lr = await API.get('/leads?page=1&page_size=5');
      if (!lr.error) this.recentLeads = lr.data?.items || [];
    },
    openLead(id) { TMSStore.leadId = id; TMSStore.fromView = this.currentView; this.switchView('lead-detail'); },
  },
  created() { this.load(); },
});

/* ════════════════════════════════════════
   Leads 列表组件（含分页）
   ════════════════════════════════════════ */
app.component('include-leads', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-leads',
  data() {
    return {
      list: [], total: 0, page: 1, pageSize: 15,
      search: '', filters: { status: 'all', source: 'all', dateFrom: '', dateTo: '' },
      selectedIds: [], showCreate: false, showAssign: false,
      creating: false, assignTarget: '', users: [],
      createForm: { name: '', phone: '', wechat: '', source: '其他', country: '', grade: '', remark: '' },
      sourceOptions: ['抖音', '小红书', '视频号', '转介绍', '线下活动', '线上', '其他'],
      searchTimer: null,
      deleteConfirm: { show: false, title: '', message: '', type: '', id: null, loading: false },
    };
  },
  computed: {
    totalPages() { return Math.max(1, Math.ceil(this.total / this.pageSize)); },
    pageNumbers() {
      const tp = this.totalPages, p = this.page, pages = [];
      if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i); }
      else {
        pages.push(1);
        if (p > 3) pages.push('...');
        for (let i = Math.max(2, p - 1); i <= Math.min(tp - 1, p + 1); i++) pages.push(i);
        if (p < tp - 2) pages.push('...');
        pages.push(tp);
      }
      return pages;
    },
  },
  methods: {
    async load() {
      if (TMSStore.leadsPage && TMSStore.leadsPage > 1) { this.page = TMSStore.leadsPage; TMSStore.leadsPage = 1; }
      let p = `?page=${this.page}&page_size=${this.pageSize}&status=${this.filters.status}&source=${this.filters.source}`;
      if (this.filters.dateFrom) p += `&date_from=${this.filters.dateFrom}`;
      if (this.filters.dateTo) p += `&date_to=${this.filters.dateTo}`;
      if (this.search) p += '&search=' + encodeURIComponent(this.search);
      const res = await API.get('/leads' + p);
      if (res.error) return;
      this.list = res.data?.items || [];
      this.total = res.data?.total || 0;
    },
    debounceSearch() {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => { this.page = 1; this.load(); }, 300);
    },
    onDateChange() { this.page = 1; this.load(); },
    goPage(p) { if (p < 1 || p > this.totalPages || p === '...') return; this.page = p; this.load(); },
    toggleAll(e) { this.selectedIds = e.target.checked ? this.list.map(l => l.id) : []; },
    openLead(id, ev) { if (ev?.target?.type === 'checkbox') return; TMSStore.leadId = id; TMSStore.fromView = this.currentView; TMSStore.leadsPage = this.page; TMSStore.leadsList = this.list.map(l => l.id); this.switchView('lead-detail'); },
    openCreate() { this.createForm = { name: '', phone: '', wechat: '', source: '其他', country: '', grade: '', remark: '' }; this.showCreate = true; },
    downloadCSV() {
      const params = new URLSearchParams();
      if (this.filters.status !== 'all') params.set('status', this.filters.status);
      if (this.filters.source !== 'all') params.set('source', this.filters.source);
      if (this.filters.dateFrom) params.set('date_from', this.filters.dateFrom);
      if (this.filters.dateTo) params.set('date_to', this.filters.dateTo);
      if (this.search) params.set('search', this.search);
      downloadCSV('/leads/export?' + params.toString(), '线索导出.csv');
    },
    async submitCreate() {
      if (!this.createForm.name) { toast('请输入姓名', 'error'); return; }
      this.creating = true;
      const res = await API.post('/leads', this.createForm);
      this.creating = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('创建成功', 'success');
      this.showCreate = false;
      this.page = 1; this.load();
    },
    async batchAssign() {
      const res = await API.get('/auth/users');
      if (res.error) return;
      this.users = res.data || [];
      this.showAssign = true;
    },
    async submitAssign() {
      if (!this.assignTarget) { toast('请选择跟进人', 'error'); return; }
      const res = await API.post('/leads/batch/assign', { lead_ids: this.selectedIds, assignee_id: parseInt(this.assignTarget) });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('分配成功', 'success');
      this.showAssign = false; this.selectedIds = []; this.load();
    },
    async batchPool() {
      if (!confirm('确定将这些线索回公海？')) return;
      const res = await API.post('/leads/batch/assign', { lead_ids: this.selectedIds, assignee_id: null });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('已回公海', 'success');
      this.selectedIds = []; this.load();
    },
    openEditLead(l) {
      this.leadEditForm = { id: l.id, name: l.name, phone: l.phone || '', wechat: l.wechat || '', source: l.source || '', country: l.country || '', grade: l.grade || '', remark: l.remark || '', created_at: (l.created_at || '').slice(0,10), lead_rank: l.lead_rank || '' };
      this.leadEditSaving = false;
      this.showLeadEdit = true;
    },
    async submitLeadEdit() {
      this.leadEditSaving = true;
      const res = await API.put('/leads/' + this.leadEditForm.id, this.leadEditForm);
      this.leadEditSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('线索已更新', 'success');
      this.showLeadEdit = false;
      this.load();
    },
    confirmDeleteLead(l) {
      this.deleteConfirm = {
        show: true, loading: false,
        title: '删除线索',
        message: `确定删除线索「${l.name}」？将同时删除关联的合同、课时包、付款记录、排课、跟进等所有数据，此操作不可恢复！`,
        type: 'lead', id: l.id,
      };
    },
    async executeDelete() {
      const dc = this.deleteConfirm;
      if (!dc.type || !dc.id) return;
      dc.loading = true;
      let res;
      if (dc.type === 'lead') {
        res = await API.del('/leads/' + dc.id);
      }
      dc.loading = false;
      dc.show = false;
      if (res && res.error) { toast(res.error, 'error'); return; }
      toast('已删除', 'success');
      this.load();
    },
  },
  created() { this.load(); },
});

/* ════════════════════════════════════════
   Lead Detail 组件
   ════════════════════════════════════════ */
app.component('include-lead-detail', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-lead-detail',
  data() {
    return {
      lead: null, followContent: '', followupType: '', nextAction: '', nextDate: '',
      showLostModal: false, lostReason: '',
      followupTypeOptions: ['电话沟通', '微信沟通', '到访面谈', '试听反馈', '续费沟通', '其他'],
      followupRank: '',
      contactStatus: '',
      lostReasonOptions: ['价格因素', '已选择其他机构', '时间安排冲突', '需求变更', '联系不上', '其他'],
      // 学业分析
      showConsultingCreate: false,
      showConsultingView: false,
      consultingTab: 'risk',
      consultingForm: { target_country: '', target_school: '', target_major: '', current_school: '', current_grade: '', gpa: '', language_scores: '', additional_info: '', report_type: 'unified', program_url: '', program_courses: '' },
      consultingSaving: false,
      consultingGenActive: false,
      consultingGenStatus: '',
      consultingGenStep: '',
      consultingGenProgress: 0,
      consultingGenPollTimer: null,
      consultingGenPollStart: 0,
      consultingGenReportId: null,
      consultingReport: null,
      // 删除确认
      deleteConfirm: { show: false, title: '', message: '', type: '', id: null, loading: false },
      // 编辑线索
      showEditModal: false,
      editForm: {},
      editSaving: false,
      // 整体学情报告
      overallReport: null,
      overallReportStatus: '',
      overallReportProgress: 0,
      overallReportStep: '',
      overallReportPollTimer: null,
      showOverallReportModal: false,
      reportEditData: {},
      reportSaving: false,
      homeworkList: [],
      uploadProgress: 0,
      uploading: false,
      uploadStep: '',
      dragOver: false,
    };
  },
  computed: {
    canFollow() { return this.user && ['cs', 'consultant', 'coordinator', 'admin', 'supervisor'].includes(this.user.role); },
    canMarkLost() { return this.user && ['cs', 'consultant', 'admin', 'supervisor'].includes(this.user.role); },
    canRestore() { return this.user && ['admin', 'supervisor'].includes(this.user.role); },
    overdueDays() {
      if (!this.lead || !this.lead.next_followup_at) return 0;
      const next = new Date(this.lead.next_followup_at.slice(0, 10));
      const today = new Date();
      today.setHours(0, 0, 0, 0);
      const diff = Math.floor((today - next) / 86400000);
      return diff > 0 ? diff : 0;
    },
    canDelete() { return this.user && ['admin', 'supervisor'].includes(this.user.role); },
    curLeadIndex() { return TMSStore.leadsList.indexOf(this.lead?.id); },
    hasPrevLead() { return this.curLeadIndex > 0; },
    hasNextLead() { return this.curLeadIndex >= 0 && this.curLeadIndex < TMSStore.leadsList.length - 1; },
    canManageContract() { return this.user && ['coordinator', 'academic', 'admin', 'supervisor'].includes(this.user.role); },
  },
  methods: {
    async load() {
      const id = TMSStore.leadId;
      if (!id) return;
      const res = await API.get('/leads/' + id);
      if (res.error) { toast(res.error, 'error'); return; }
      this.lead = res.data;
      this.loadHomework();
      this.loadOverallReport();
    },
    async loadOverallReport() {
      if (!this.lead || !this.lead.id) return;
      const res = await API.get('/growth/' + this.lead.id + '/overall-report');
      if (!res.error && res.data && res.data.report_title) {
        this.overallReport = res.data;
        this.overallReportStatus = 'done';
      }
    },
    async submitFollow() {
      if (!this.followContent.trim()) return;
      const res = await API.post('/followups', {
        lead_id: this.lead.id,
        content: this.followContent,
        followup_type: this.followupType,
        next_action: this.nextAction,
        next_date: this.nextDate,
      });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('跟进记录已保存', 'success');
      this.followContent = ''; this.followupType = ''; this.followupRank = ''; this.nextAction = ''; this.nextDate = '';
      this.load();
    },
    // ── 删除操作 ──
    confirmDeleteContract(c) {
      this.deleteConfirm = {
        show: true, loading: false,
        title: '删除合同',
        message: `确定删除合同「${c.contract_no || '—'}」？将同时删除关联的课时包和付款记录。`,
        type: 'contract', id: c.id,
      };
    },
    confirmDeletePackage(p) {
      this.deleteConfirm = {
        show: true, loading: false,
        title: '删除课时包',
        message: `确定删除课时包「${p.name || '—'}」？`,
        type: 'package', id: p.id,
      };
    },
    confirmDeletePayment(cId, p) {
      this.deleteConfirm = {
        show: true, loading: false,
        title: '删除付款记录',
        message: `确定删除 ¥${Math.abs(p.amount || 0).toFixed(2)} 的付款记录？合同已收金额将同步调整。`,
        type: 'payment', id: p.id, contractId: cId,
      };
    },
    confirmDeleteFollowup(f) {
      this.deleteConfirm = {
        show: true, loading: false,
        title: '删除跟进记录',
        message: '确定删除此跟进记录？',
        type: 'followup', id: f.id,
      };
    },
    async executeDelete() {
      const dc = this.deleteConfirm;
      if (!dc.type || !dc.id) return;
      dc.loading = true;
      let res;
      if (dc.type === 'contract') {
        res = await API.del('/contracts/' + dc.id);
      } else if (dc.type === 'package') {
        res = await API.del('/packages/' + dc.id);
      } else if (dc.type === 'payment') {
        res = await API.del('/contracts/' + dc.contractId + '/payments/' + dc.id);
      } else if (dc.type === 'followup') {
        res = await API.del('/followups/' + dc.id);
      }
      dc.loading = false;
      dc.show = false;
      if (res && res.error) { toast(res.error, 'error'); return; }
      toast('已删除', 'success');
      this.load();
    },
    // 标记流失
    openLostModal() {
      this.lostReason = '';
      this.showLostModal = true;
    },
    async submitLost() {
      if (!this.lostReason) { toast('请选择流失原因', 'error'); return; }
      const res = await API.put('/leads/' + this.lead.id, { status: 'lost', lost_reason: this.lostReason });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('已标记为流失', 'success');
      this.showLostModal = false;
      this.load();
    },
    // 从流失中恢复
    async restoreFromLost() {
      if (!confirm('确定将此线索从流失状态恢复为跟进中？')) return;
      const res = await API.put('/leads/' + this.lead.id, { status: 'following' });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('已恢复跟进', 'success');
      this.load();
    },
    goBack() { const v = TMSStore.fromView || 'leads'; this.switchView(v); },
    goPrevLead() {
      const idx = this.curLeadIndex;
      if (idx > 0) {
        this.lead = null;
        TMSStore.leadId = TMSStore.leadsList[idx - 1];
        this.load();
        this.loadHomework();
      }
    },
    updateContactStatus() {
      if (!this.lead || !this.lead.id) return;
      const val = this.lead.contact_status || '';
      API.put('/leads/' + this.lead.id, { contact_status: val });
    },
    goNextLead() {
      const idx = this.curLeadIndex;
      if (idx >= 0 && idx < TMSStore.leadsList.length - 1) {
        this.lead = null;
        TMSStore.leadId = TMSStore.leadsList[idx + 1];
        this.load();
        this.loadHomework();
      }
    },

    // ── 整体学情报告 ──
    async generateOverallReport() {
      if (!this.lead || !this.lead.id) return;
      if (this.overallReportPollTimer) clearTimeout(this.overallReportPollTimer);
      this.overallReport = null;
      this.overallReportStatus = 'generating';
      this.overallReportProgress = 0;
      this.overallReportStep = '正在发起生成...';
      const res = await API.post('/growth/' + this.lead.id + '/overall-report');
      if (res.error) { toast(res.error, 'error'); this.overallReportStatus = ''; return; }
      this.pollOverallReport();
    },
    pollOverallReport() {
      if (!this.lead || !this.lead.id) return;
      this.overallReportPollTimer = setTimeout(async () => {
        const pr = await API.get('/growth/' + this.lead.id + '/overall-report/progress');
        if (pr.error) { this.overallReportStatus = ''; return; }
        const st = pr.data || {};
        this.overallReportProgress = st.progress || 0;
        this.overallReportStep = st.step || '';
        if (st.status === 'done' && st.result) {
          this.overallReport = st.result;
          this.overallReportStatus = 'done';
          toast('✅ 学情报告已生成', 'success');
        } else if (st.status === 'error') {
          this.overallReportStatus = 'error';
        } else if (st.status === 'generating') {
          this.pollOverallReport();
        } else {
          this.overallReportStatus = '';
        }
      }, 2000);
    },
    viewOverallReport() {
      this.showOverallReportModal = true;
      this.reportEditData = JSON.parse(JSON.stringify(this.overallReport || {}));
    },
    onEdit(event, field, idx) {
      const val = event.target.innerText.trim();
      if (idx !== undefined) {
        if (!this.reportEditData[field]) this.reportEditData[field] = [];
        this.reportEditData[field][idx] = val;
      } else {
        this.reportEditData[field] = val;
      }
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    onEditStudentInfo(event, key) {
      const val = event.target.innerText.trim();
      if (!this.reportEditData.student_info) this.reportEditData.student_info = {};
      this.reportEditData.student_info[key] = val;
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    onEditArray(event, field, idx, sub) {
      const val = event.target.innerText.trim().replace(/[：:]$/,'');
      if (!this.reportEditData[field]) this.reportEditData[field] = [];
      if (!this.reportEditData[field][idx]) this.reportEditData[field][idx] = {};
      this.reportEditData[field][idx][sub] = val;
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    onEditDim(event, key, sub) {
      const val = event.target.innerText.trim();
      if (!this.reportEditData.dimensions) this.reportEditData.dimensions = {};
      if (!this.reportEditData.dimensions[key]) this.reportEditData.dimensions[key] = {};
      this.reportEditData.dimensions[key][sub] = val;
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    async saveOverallReport() {
      if (!this.reportEditData) return;
      this.reportSaving = true;
      const res = await API.put('/growth/' + this.lead.id + '/overall-report', { data: this.reportEditData });
      this.reportSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('报告已保存', 'success');
    },
    async downloadOverallReport(format) {
      if (!this.lead || !this.lead.id) return;
      const token = localStorage.getItem('tms_token') || '';
      const a = document.createElement('a');
      a.href = '/api/growth/' + this.lead.id + '/overall-report/download?format=' + format + '&token=' + token;
      a.download = '';
      a.click();
    },
    downloadReportTxt() {
      const d = this.reportEditData || this.overallReport;
      if (!d) return;
      let txt = d.report_title + '\n\n';
      if (d.baseline) txt += '【入学前基础概况】\n' + d.baseline + '\n\n';
      if (d.learning_summary) txt += '【学习历程总结】\n' + d.learning_summary + '\n\n';
      if (d.progress) txt += '【进步方面】\n' + d.progress.map(p => '· ' + p.aspect + '：' + p.detail).join('\n') + '\n\n';
      if (d.weaknesses) txt += '【待改进方面】\n' + d.weaknesses.map(w => '· ' + w.aspect + '：' + w.detail).join('\n') + '\n\n';
      if (d.overall_assessment) txt += '【综合评估】\n' + d.overall_assessment + '\n\n';
      if (d.recommendations) txt += '【后续建议】\n' + d.recommendations.map((r,i) => (i+1) + '. ' + r).join('\n');
      const blob = new Blob([txt], {type: 'text/plain;charset=utf-8'});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (d.report_title || '学情报告') + '.txt';
      a.click();
      URL.revokeObjectURL(a.href);
    },
    async loadHomework() {
      if (!this.lead || !this.lead.id) return;
      const res = await API.get('/leads/' + this.lead.id + '/homework');
      if (!res.error) this.homeworkList = res.data || [];
    },
    handleDrop(event) {
      this.dragOver = false;
      const files = event.dataTransfer?.files;
      if (files?.length) {
        // Upload first file
        const dt = new DataTransfer();
        dt.items.add(files[0]);
        const inputEvent = { target: { files: dt.files } };
        this.uploadHomework(inputEvent);
      }
    },
    uploadHomework(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      this.uploadFileWithProgress(file);
      event.target.value = '';
    },
    uploadFileWithProgress(file) {
      const formData = new FormData();
      formData.append('file', file);
      const token = localStorage.getItem('tms_token') || '';
      this.uploadProgress = 0;
      this.uploading = true;
      this.uploadStep = '上传中...';
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/leads/' + this.lead.id + '/homework');
      xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 98);
          this.uploadProgress = Math.min(pct, 98);
        }
      };
      xhr.onload = () => {
        this.uploadProgress = 100;
        this.uploadStep = '处理中...';
        setTimeout(() => {
          this.uploading = false;
          this.uploadProgress = 0;
          this.uploadStep = '';
          if (xhr.status >= 200 && xhr.status < 300) {
            toast('作业已上传', 'success');
            this.loadHomework();
          } else {
            let msg = '上传失败';
            try { const d = JSON.parse(xhr.responseText); msg = d.error || msg; } catch(e) {}
            toast(msg, 'error');
          }
        }, 500);
      };
      xhr.onerror = () => { this.uploading = false; this.uploadProgress = 0; this.uploadStep = ''; toast('网络错误', 'error'); };
      xhr.send(formData);
    },
    async deleteHomework(fileId) {
      if (!confirm('确定删除这份作业？')) return;
      const res = await API.get('/homework/' + fileId + '/delete');
      if (res.error) { toast(res.error, 'error'); return; }
      toast('作业已删除', 'success');
      this.loadHomework();
    },
    async downloadHomework(fileId) {
      const token = localStorage.getItem('tms_token') || '';
      const a = document.createElement('a');
      a.href = '/api/homework/' + fileId + '/download?token=' + token;
      a.target = '_blank';
      a.click();
    },

    openLeadEdit() {
      this.editForm = {
        id: this.lead.id,
        name: this.lead.name || '',
        phone: this.lead.phone || '',
        wechat: this.lead.wechat || '',
        source: this.lead.source || '',
        country: this.lead.country || '',
        grade: this.lead.grade || '',
        remark: this.lead.remark || '',
        created_at: (this.lead.created_at || '').slice(0,10),
        lead_rank: this.lead.lead_rank || '',
      };
      this.editSaving = false;
      this.showEditModal = true;
    },
    async saveLeadEdit() {
      this.editSaving = true;
      const res = await API.put('/leads/' + this.editForm.id, this.editForm);
      this.editSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('线索已更新', 'success');
      this.showEditModal = false;
      this.load();
    },
    // ── 学业分析报告 ──
    canConsulting() {
      return this.user && ['cs', 'consultant', 'academic', 'admin', 'supervisor'].includes(this.user.role);
    },
    openConsultingCreate(type) {
      const lead = this.lead;
      this.consultingForm = {
        target_country: lead.country || '',
        target_school: '',
        target_major: '',
        current_school: '',
        current_grade: lead.grade || '',
        gpa: '',
        language_scores: '',
        additional_info: lead.remark || '',
        target_level: '',
        report_type: 'unified',
        program_url: '',
        program_courses: '',
      };
      this.consultingGenActive = false;
      this.consultingGenProgress = 0;
      this.consultingGenStep = '';
      this.showConsultingCreate = true;
    },
    closeConsultingCreate() {
      this.showConsultingCreate = false;
      this.consultingGenActive = false;
      if (this.consultingGenPollTimer) { clearTimeout(this.consultingGenPollTimer); this.consultingGenPollTimer = null; }
    },
    async submitConsultingCreate() {
      const f = this.consultingForm;
      if (!f.additional_info.trim()) {
        toast('请描述学生情况', 'error'); return;
      }
      this.consultingSaving = true;
      const payload = {
        target_country: f.target_country,
        target_school: f.target_school,
        target_major: f.target_major,
        current_school: f.current_school,
        current_grade: f.current_grade,
        gpa: f.gpa,
        language_scores: f.language_scores,
        additional_info: f.additional_info,
        target_level: f.target_level,
        report_type: 'unified',
      };
      const res = await API.post('/leads/' + this.lead.id + '/consulting', payload);
      this.consultingSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      const report = res.data;
      toast('报告已创建，正在生成分析...', 'success');
      // 2. 触发 AI 生成
      await this.startConsultingGen(report.id);
    },
    async startConsultingGen(reportId) {
      this.consultingGenActive = true;
      this.consultingGenReportId = reportId;
      this.consultingGenStatus = '';
      this.consultingGenStep = '启动分析引擎...';
      this.consultingGenProgress = 0;
      this.consultingGenPollStart = Date.now();
      const genRes = await API.post('/leads/' + this.lead.id + '/consulting/' + reportId + '/generate');
      if (genRes.error) {
        // researching 状态不算错误
        if (genRes.data && genRes.data.status === 'researching') {
          this.consultingGenStatus = 'researching';
          this.consultingGenStep = genRes.data.step || '正在联网搜索院校录取要求...';
          this.consultingGenProgress = genRes.data.progress || 5;
        } else {
          this.consultingGenActive = false;
          toast(genRes.error, 'error');
          return;
        }
      }
      // 3. 轮询进度
      this.pollConsultingProgress(reportId);
    },
    async pollConsultingProgress(reportId) {
      this.consultingGenPollTimer = setTimeout(async () => {
        const pr = await API.get('/leads/' + this.lead.id + '/consulting/' + reportId + '/progress');
        if (pr.error) { this.consultingGenActive = false; toast(pr.error, 'error'); return; }
        const st = pr.data;
        this.consultingGenProgress = st.progress || 0;
        this.consultingGenStep = st.step || '';
        this.consultingGenStatus = st.status || '';
        if (st.status === 'done') {
          this.consultingGenActive = false;
          toast('✅ 学业分析报告已生成！', 'success');
          this.showConsultingCreate = false;
          this.load();
        } else if (st.status === 'error') {
          this.consultingGenActive = false;
          toast('❌ ' + (st.error || '生成失败'), 'error');
        } else if (st.status === 'researching') {
          // researching 状态：继续轮询，等待 Claude 提交课程数据
          // 如果超过 30 秒仍无进展，自动切换为直接生成（跳过联网）
          const elapsed = (Date.now() - this.consultingGenPollStart) / 1000;
          if (elapsed > 30) {
            this.consultingGenStep = '联网超时，正在跳过联网直接生成...';
            await this.skipResearch(reportId);
          } else {
            this.pollConsultingProgress(reportId);
          }
        } else if (st.status && st.status !== 'idle') {
          this.pollConsultingProgress(reportId);
        } else {
          this.consultingGenActive = false;
        }
      }, 2000);
    },
    async skipResearch(reportId) {
      if (this.consultingGenPollTimer) {
        clearTimeout(this.consultingGenPollTimer);
        this.consultingGenPollTimer = null;
      }
      this.consultingGenStatus = 'generating';
      this.consultingGenStep = '正在生成分析...';
      this.consultingGenProgress = 10;
      const genRes = await API.post('/leads/' + this.lead.id + '/consulting/' + reportId + '/generate?force=1');
      if (genRes.error) { this.consultingGenActive = false; toast(genRes.error, 'error'); return; }
      this.consultingGenPollStart = Date.now();
      this.pollConsultingProgress(reportId);
    },
    async viewConsultingReport(reportId) {
      this.consultingReport = null;
      this.showConsultingView = true;
      const res = await API.get('/leads/' + this.lead.id + '/consulting/' + reportId);
      if (res.error) { toast(res.error, 'error'); return; }
      this.consultingReport = res.data;
    },
    async deleteConsultingReport(reportId) {
      if (!confirm('确定要删除这份学业分析报告吗？')) return;
      const res = await API.del('/leads/' + this.lead.id + '/consulting/' + reportId);
      if (res.error) { toast(res.error, 'error'); return; }
      toast('报告已删除', 'success');
      this.load();
    },
    filteredConsultingReports(type) {
      if (!this.lead || !this.lead.consulting_reports) return [];
      if (type === 'unified') {
        return this.lead.consulting_reports.filter(r => r.report_type === 'unified' || r.report_type === 'risk' || r.report_type === 'preparation');
      }
      return this.lead.consulting_reports.filter(r => r.report_type === type);
    },
    downloadConsultingReport(reportId, format) {
      // 直接导航到 API URL，浏览器原生处理下载（兼容移动端）
      const token = localStorage.getItem('tms_token') || '';
      const url = '/api/leads/' + this.lead.id + '/consulting/' + reportId + '/download?format=' + format + '&token=' + encodeURIComponent(token);
      const link = document.createElement('a');
      link.href = url;
      const name = (this.lead?.name || '').trim();
      link.download = (name ? name + '-' : '') + '学业风险与规划报告.' + (format === 'docx' ? 'docx' : 'pdf');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },
  },
  created() { this.load(); },
  unmounted() { if (this.consultingGenPollTimer) clearTimeout(this.consultingGenPollTimer); },
});

/* ════════════════════════════════════════
   Quick Add 组件
   ════════════════════════════════════════ */
app.component('include-quick-add', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-quick-add',
  data() {
    return {
      form: { name: '', phone: '', wechat: '', source: '其他', country: '', grade: '', remark: '' },
      submitting: false, success: false,
      sourceOptions: ['抖音', '小红书', '视频号', '转介绍', '线下活动', '线上', '其他'],
    };
  },
  methods: {
    async submit() {
      if (!this.form.name) { toast('请输入姓名', 'error'); return; }
      this.submitting = true; this.success = false;
      const res = await API.post('/leads', this.form);
      this.submitting = false;
      if (res.error) { toast(res.error, 'error'); return; }
      this.success = true;
      this.form = { name: '', phone: '', wechat: '', source: '其他', country: '', grade: '', remark: '' };
      toast('线索创建成功', 'success');
    },
  },
});

/* ════════════════════════════════════════
   Follow-up Plan 组件
   ════════════════════════════════════════ */
app.component('include-followup-plan', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-followup-plan',
  data() {
    return {
      activeTab: 'overdue', followups: [],
      tabs: [
        { key: 'overdue', label: '逾期跟进' },
        { key: 'today', label: '今日跟进' },
        { key: 'upcoming', label: '未来计划' },
      ],
    };
  },
  computed: {
    activeTabLabel() {
      const t = this.tabs.find(t => t.key === this.activeTab);
      return t ? t.label : '';
    },
  },
  methods: {
    async load() {
      const res = await API.get('/leads?page=1&page_size=50');
      if (res.error) return;
      let items = res.data?.items || [];
      const today = new Date().toISOString().slice(0, 10);
      const todayDate = new Date(today);
      // 计算逾期天数
      items = items.map(l => {
        if (l.next_followup_at) {
          const next = new Date(l.next_followup_at.slice(0, 10));
          const diff = Math.floor((todayDate - next) / (86400000));
          l.overdue_days = diff > 0 ? diff : 0;
        } else {
          l.overdue_days = 0;
        }
        return l;
      });
      if (this.activeTab === 'overdue') {
        items = items.filter(l => l.next_followup_at && l.next_followup_at < today && !['enrolled', 'closed', 'lost'].includes(l.status));
      } else if (this.activeTab === 'today') {
        items = items.filter(l => l.next_followup_at && l.next_followup_at.slice(0, 10) === today);
      } else {
        items = items.filter(l => l.next_followup_at && l.next_followup_at.slice(0, 10) > today);
      }
      this.followups = items;
    },
    switchTab(key) { this.activeTab = key; this.load(); },
    openLead(id) { TMSStore.leadId = id; TMSStore.fromView = this.currentView; this.switchView('lead-detail'); },
  },
  created() { this.load(); },
});

/* ════════════════════════════════════════
   Schedules 排课管理组件
   ════════════════════════════════════════ */
app.component('include-schedules', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-schedules',
  data() {
    return {
      list: [], total: 0,
      dateFrom: '', dateTo: '', filterTutor: '', filterStatus: '',
      filterLeadName: '',
      teachers: [], leads: [],
      showModal: false, editId: null, saving: false,
      loading: false,
      form: { lead_id: '', tutor_id: '', subject: '', start_time: '', end_time: '', status: 'pending', remark: '', tutoring_form: '', actual_duration_minutes: '', repeat_count: 4, repeat_enabled: false },
      statusMap: { pending: '待上课', completed: '已完成', cancelled: '已取消', in_progress: '进行中' },
      hoursPopup: null,
      // 课后反馈
      showFeedbackModal: false,
      feedbackScheduleId: null,
      feedbackStudentName: '',
      feedbackSubject: '',
      feedbackTeacher: '',
      feedbackDate: '',
      feedbackDuration: '',
      feedbackForm: { classin_link: '', content_covered: '', student_performance: '', difficulties: '', homework_completion: '', teacher_notes: '', next_focus: '' },
      feedbackSaving: false,
      feedbackPackageInfo: {},
      genStatus: { progress: 0, step: '' },
      selectedScheduleIds: [],
    };
  },
  computed: {
    allSelected() {
      const allIds = this.list.map(s => s.id);
      return allIds.length > 0 && allIds.every(id => this.selectedScheduleIds.includes(id));
    },
    scheduleGroups() {
      const groups = {};
      for (const s of this.list) {
        const d = (s.start_time || '').slice(0, 10);
        if (!groups[d]) groups[d] = { date: d, dateLabel: this.dateLabel(d), items: [] };
        groups[d].items.push(s);
      }
      return Object.values(groups).sort((a, b) => a.date < b.date ? -1 : 1);
    },
    aiGenerating() {
      const s = this.genStatus.status;
      return s && s !== 'idle' && s !== 'done' && s !== 'error';
    },
    genStage() {
      const stages = [
        { max: 4,  emoji: '🥱', label: '小书僮准备开工...', anim: 'float' },
        { max: 19, emoji: '🔍', label: '正在潜入课堂找视频...', anim: 'search' },
        { max: 34, emoji: '🎧', label: '竖起耳朵听课ing...', anim: 'listen' },
        { max: 54, emoji: '📝', label: '奋笔疾书记笔记...', anim: 'write' },
        { max: 64, emoji: '🤔', label: '小脑瓜飞快思考...', anim: 'think' },
        { max: 79, emoji: '✨', label: '整理成报告ing...', anim: 'work' },
        { max: 89, emoji: '🎯', label: '最后润色检查...', anim: 'polish' },
        { max: 99, emoji: '💪', label: '装订存档...', anim: 'save' },
        { max: 100,emoji: '🎉', label: '完成啦！', anim: 'celebrate' },
      ];
      const p = this.genStatus.progress;
      for (const s of stages) { if (p <= s.max) return s; }
      return stages[stages.length - 1];
    },
  },
  methods: {
    dateLabel(d) {
      const today = new Date().toISOString().slice(0, 10);
      const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
      const dt = new Date(d + 'T00:00:00');
      const weekday = '周' + weekdays[dt.getDay()];
      if (d === today) return `今天 · ${weekday} · ${d}`;
      const diff = (new Date(today + 'T00:00:00') - dt) / 86400000;
      if (diff === -1) return `明天 · ${weekday} · ${d}`;
      if (diff === -2) return `后天 · ${weekday} · ${d}`;
      return `${dt.getMonth() + 1}月${dt.getDate()}日 ${weekday} · ${d}`;
    },
    timeLabel(s) {
      return (s.start_time || '').slice(11, 16) + ' - ' + (s.end_time || '').slice(11, 16);
    },
    durationHint(s) {
      if (s.actual_duration_minutes) return `${s.actual_duration_minutes}min(实际)`;
      return `${s.duration_minutes || '-'}min`;
    },
    async load() {
      this.loading = true;
      const params = new URLSearchParams();
      if (this.dateFrom) params.set('date_from', this.dateFrom);
      if (this.dateTo) params.set('date_to', this.dateTo);
      if (this.filterTutor) params.set('teacher_id', this.filterTutor);
      if (this.filterStatus) params.set('status', this.filterStatus);
      if (this.filterLeadName) params.set('search', this.filterLeadName);
      const res = await API.get('/schedules?' + params.toString());
      if (!res.error) { this.list = res.data?.items || []; this.total = res.data?.total || 0; }
      this.loading = false;
    },
    async loadTeachers() {
      const res = await API.get('/teachers?page_size=200');
      if (!res.error) { this.teachers = res.data?.items || []; }
    },
    async loadLeads() {
      const res = await API.get('/leads?page=1&page_size=200');
      if (!res.error) { this.leads = res.data?.items || []; }
    },
    openCreate() {
      this.editId = null;
      this.form = { lead_id: '', teacher_id: '', subject: '', start_time: '', end_time: '', status: 'pending', remark: '', tutoring_form: '', actual_duration_minutes: '', repeat_count: 4, repeat_enabled: false };
      this.showModal = true;
    },
    openDetail(s) {
      this.editId = s.id;
      this.form = {
        lead_id: s.lead_id || '',
        teacher_id: s.teacher_id || '',
        subject: s.subject || '',
        start_time: s.start_time ? s.start_time.slice(0, 16) : '',
        end_time: s.end_time ? s.end_time.slice(0, 16) : '',
        status: s.status || 'pending',
        remark: s.remark || '',
        tutoring_form: s.tutoring_form || '',
        actual_duration_minutes: s.actual_duration_minutes || '',
      };
      this.showModal = true;
    },
    closeModal() { this.showModal = false; this.editId = null; },
    async submitSave() {
      if (!this.form.lead_id) { toast('请选择学生', 'error'); return; }
      if (!this.form.start_time || !this.form.end_time) { toast('请选择时间', 'error'); return; }
      this.saving = true;
      let res;
      const payload = { ...this.form };
      // 处理老师选择：如果选中的是师资表老师，映射到 teacher_id
      if (payload.tutor_id) {
        const sel = this.tutors.find(t => t.id == payload.tutor_id && t.type === 'teacher');
        if (sel) {
          payload.teacher_id = payload.tutor_id;
          delete payload.tutor_id;
        } else if (payload.teacher_id && !payload.tutor_id) {
          // teacher_id already set, keep it
        }
      }
      if (payload.actual_duration_minutes === '') {
        delete payload.actual_duration_minutes;
      } else if (payload.actual_duration_minutes) {
        payload.actual_duration_minutes = parseInt(payload.actual_duration_minutes);
      }
      // 每周重复：仅在创建时生效
      if (this.editId || !payload.repeat_enabled) {
        delete payload.repeat_count;
      }
      delete payload.repeat_enabled;
      if (this.editId) {
        res = await API.put('/schedules/' + this.editId, payload);
      } else {
        res = await API.post('/schedules', payload);
      }
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast(this.editId ? '排课已更新' : (res.data?.count ? `已创建 ${res.data.count} 个排课` : '排课已创建'), 'success');
      this.closeModal();
      this.load();
    },
    async deleteItem() {
      if (!confirm('确定删除此排课？')) return;
      const res = await API.del('/schedules/' + this.editId);
      if (res.error) { toast(res.error, 'error'); return; }
      toast('已删除', 'success');
      this.closeModal();
      this.load();
    },
    showHoursPopup(s) {
      this.hoursPopup = s;
    },
    closeHoursPopup() {
      this.hoursPopup = null;
    },
    toggleAllGroups() {
      if (this.allSelected) {
        this.selectedScheduleIds = [];
      } else {
        this.selectedScheduleIds = this.list.map(s => s.id);
      }
    },
    confirmBatchDelete() {
      if (this.selectedScheduleIds.length === 0) { toast('请选择要删除的排课', 'error'); return; }
      if (!confirm('确定删除选中的 ' + this.selectedScheduleIds.length + ' 条排课？将同时恢复对应课时消耗。')) return;
      this.batchDelete();
    },
    async batchDelete() {
      const res = await API.post('/schedules/batch_delete', { ids: this.selectedScheduleIds });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('已删除 ' + this.selectedScheduleIds.length + ' 条排课', 'success');
      this.selectedScheduleIds = [];
      this.load();
    },
    downloadCSV() {
      const params = new URLSearchParams();
      if (this.dateFrom) params.set('date_from', this.dateFrom);
      if (this.dateTo) params.set('date_to', this.dateTo);
      if (this.filterTutor) params.set('teacher_id', this.filterTutor);
      if (this.filterStatus) params.set('status', this.filterStatus);
      if (this.filterLeadName) params.set('search', this.filterLeadName);
      downloadCSV('/schedules/export?' + params.toString(), '排课导出.csv');
    },
    // ── 课后反馈 ──
    openFeedback(s) {
      this.feedbackScheduleId = s.id;
      this.feedbackStudentName = s.lead_name || '';
      this.feedbackSubject = s.subject || '';
      this.feedbackTeacher = s.teacher_name || '';
      this.feedbackDate = (s.start_time || '').slice(0, 10);
      this.feedbackDuration = s.actual_duration_minutes || s.duration_minutes || '';
      this.feedbackForm = { classin_link: s.classin_link || '', content_covered: '', student_performance: '', difficulties: '', homework_completion: '', teacher_notes: '', next_focus: '' };
      this.genStatus = { progress: 0, step: '' };
      // 加载已有反馈
      this.loadFeedback();
      this.showFeedbackModal = true;
    },
    closeFeedback() {
      this.showFeedbackModal = false;
      this.feedbackScheduleId = null;
    },
    async loadFeedback() {
      const res = await API.get('/schedules/' + this.feedbackScheduleId + '/feedback');
      if (!res.error && res.data) {
        const fb = res.data.feedback || res.data;
        if (fb.id) {
          this.feedbackForm = {
            classin_link: fb.classin_link || '',
            content_covered: fb.content_covered || '',
            student_performance: fb.student_performance || '',
            difficulties: fb.difficulties || '',
            homework_completion: fb.homework_completion || '',
            teacher_notes: fb.teacher_notes || '',
            next_focus: fb.next_focus || '',
          };
        }
        this.feedbackPackageInfo = res.data.package_info || {};
      }
    },
    async submitFeedback() {
      this.feedbackSaving = true;
      const res = await API.post('/schedules/' + this.feedbackScheduleId + '/feedback', this.feedbackForm);
      this.feedbackSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('反馈已保存', 'success');
      this.closeFeedback();
      this.load();
    },
    async deleteFeedback() {
      toast('删除中...', 'success');
      try {
        const res = await API.del('/schedules/' + this.feedbackScheduleId + '/feedback');
        if (res.error) { toast('删除失败: ' + res.error, 'error'); return; }
        toast('✅ 反馈已删除', 'success');
        this.closeFeedback();
        this.load();
      } catch(e) {
        toast('删除异常: ' + e.message, 'error');
      }
    },
    async generateFeedback() {
      const link = this.feedbackForm.classin_link;
      if (!link) { toast('请先粘贴 ClassIn 链接', 'error'); return; }
      this.genStatus = { progress: 0, step: '启动中...', status: 'starting' };
      const res = await API.post('/schedules/' + this.feedbackScheduleId + '/feedback/generate', { classin_link: link });
      if (res.error) { toast(res.error, 'error'); this.genStatus = { progress: 0, step: '', status: 'idle' }; return; }
      // 轮询进度
      const poll = async () => {
        while (true) {
          await new Promise(r => setTimeout(r, 2000));
          const pr = await API.get('/schedules/' + this.feedbackScheduleId + '/feedback/generate/progress');
          const st = pr.data || {};
          this.genStatus = { progress: st.progress || 0, step: st.step || '', status: st.status || 'idle' };
          if (st.status === 'done' && st.result) {
            const fb = st.result.feedback || {};
            const tr = st.result.time_range || '';
            const lc = st.result.line_count || 0;
            this.feedbackForm = {
              classin_link: link,
              content_covered: fb.content_covered || '',
              student_performance: fb.student_performance || '',
              difficulties: fb.difficulties || '',
              homework_completion: fb.homework_completion || '',
              teacher_notes: fb.teacher_notes || '',
              next_focus: fb.next_focus || '',
            };
            toast('✅ 完成' + (lc ? '（' + lc + '段' + (tr ? ' ' + tr : '') + '）' : ''), 'success');
            break;
          }
          if (st.status === 'error') {
            toast(st.error || '生成失败', 'error');
            break;
          }
          if (st.status === 'idle' || !st.status) break;
        }
      };
      poll();
    },
    // ── 一键复制反馈 ──
    copyFeedback(includeInternal) {
      const student = this.feedbackStudentName || '';
      const subject = this.feedbackSubject || '';
      const teacher = this.feedbackTeacher || '';
      const date = this.feedbackDate || '';
      const duration = this.feedbackDuration ? `(${this.feedbackDuration}min)` : '';
      const fb = this.feedbackForm;

      let text = '━━━ 课后反馈 ━━━\n';
      text += `👤 学生: ${student}  📚 ${subject}  👨‍🏫 ${teacher}\n`;
      text += `📅 ${date} ${duration}\n`;
      if (this.feedbackPackageInfo && 'total_hours' in this.feedbackPackageInfo) {
        const p = this.feedbackPackageInfo;
        text += `📦 报名 ${p.total_hours}h · 已用 ${p.used_hours}h · 剩余 ${p.remaining_hours}h\n`;
      }
      text += '\n';
      text += '📖 授课内容\n';
      text += `▸ ${_stripTS(fb.content_covered) || '未填写'}\n\n`;

      text += '🙋 课堂表现\n';
      text += `▸ ${_stripTS(fb.student_performance) || '未填写'}\n\n`;

      text += '⚠️ 薄弱环节\n';
      text += `▸ ${_stripTS(fb.difficulties) || '未填写'}\n\n`;

      text += '📝 作业情况\n';
      text += `▸ ${_stripTS(fb.homework_completion) || '未填写'}\n`;

      if (includeInternal) {
        if (fb.teacher_notes) {
          text += `\n📌 教师观察\n▸ ${_stripTS(fb.teacher_notes)}\n`;
        }
        if (fb.next_focus) {
          text += `\n💡 后续建议\n▸ ${_stripTS(fb.next_focus)}\n`;
        }
      }

      text += '\n━━━ 来自 TMS 教务系统 ━━━';

      navigator.clipboard.writeText(text).then(() => {
        toast(includeInternal ? '✅ 完整版已复制到剪贴板' : '✅ 家长版已复制到剪贴板', 'success');
      }).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        toast(includeInternal ? '✅ 完整版已复制到剪贴板' : '✅ 家长版已复制到剪贴板', 'success');
      });
    },
  },
  created() { this.loadTeachers(); this.loadLeads(); this.load(); },
});

/* ════════════════════════════════════════
   签约管理组件（合并 课时包管理 + 签约学生）
   ════════════════════════════════════════ */
app.component('include-signing', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-signing',
  data() {
    return {
      // Tab
      tab: 'records',
      tabs: [{ key: 'records', label: '收款记录' }, { key: 'students', label: '学生总览' }],
      // Payments
      allPayments: [], loading: false,
      filterDateFrom: '', filterDateTo: '', filterSearch: '',
      // Students
      studentsList: [], studentsTotal: 0, studentPage: 1, studentPageSize: 20,
      studentSearch: '', studentSearchTimer: null, studentsLoading: false,
      // All leads (for signing form)
      allLeads: [],
      // Modals
      showSigningModal: false, showAddPaymentModal: false,
      showAssignModal: false, saving: false,
      signingForm: { lead_id: '', signed_at: '', contract_no: '', package_name: '', total_hours: 0, price_per_hour: 0, payment_amount: 0, payment_method: '', payment_date: '', remark: '' },
      addPaymentForm: { amount: '', method: '', note: '', payment_date: '' },
      addPaymentContractId: null, addPaymentStudentName: '',
      // Assign
      assignLeadId: null, assignLeadName: '', assignCoordinatorId: '',
      coordinators: [],
      // Delete
      deleteConfirm: { show: false, title: '', message: '', paymentId: null, contractId: null, loading: false },
    };
  },
  computed: {
    filteredPayments() {
      let rows = this.allPayments;
      if (this.filterDateFrom) {
        rows = rows.filter(p => (p.payment_date || '').slice(0,10) >= this.filterDateFrom);
      }
      if (this.filterDateTo) {
        rows = rows.filter(p => (p.payment_date || '').slice(0,10) <= this.filterDateTo);
      }
      if (this.filterSearch) {
        const q = this.filterSearch.toLowerCase();
        rows = rows.filter(p => (p.lead_name || '').toLowerCase().includes(q));
      }
      return rows;
    },
    statsThisMonth() {
      const now = new Date();
      const ym = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
      const monthRows = this.allPayments.filter(p => (p.payment_date || '').startsWith(ym));
      const studentSet = new Set(monthRows.map(p => p.lead_id).filter(Boolean));
      return {
        total: monthRows.length,
        students: studentSet.size,
        hours: monthRows.reduce((s,p) => s + (p.total_hours || 0), 0),
        amount: monthRows.reduce((s,p) => s + (p.amount || 0), 0),
        newCount: monthRows.filter(p => p.sign_type === 'new').length,
        renewalCount: monthRows.filter(p => p.sign_type === 'renewal').length,
      };
    },
    studentTotalPages() { return Math.max(1, Math.ceil(this.studentsTotal / this.studentPageSize)); },
    studentPageNumbers() {
      const tp = this.studentTotalPages, p = this.studentPage, pages = [];
      if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i); }
      else {
        pages.push(1);
        if (p > 3) pages.push('...');
        for (let i = Math.max(2, p - 1); i <= Math.min(tp - 1, p + 1); i++) pages.push(i);
        if (p < tp - 2) pages.push('...');
        pages.push(tp);
      }
      return pages;
    },
    canManage() {
      return ['coordinator', 'admin', 'supervisor'].includes(this.user?.role);
    },
    canAssignCoordinator() {
      return ['admin', 'supervisor', 'consultant', 'cs'].includes(this.user?.role);
    },
  },
  methods: {
    // ── Load ──
    async loadPayments() {
      this.loading = true;
      const params = new URLSearchParams();
      if (this.filterDateFrom) params.set('date_from', this.filterDateFrom);
      if (this.filterDateTo) params.set('date_to', this.filterDateTo);
      if (this.filterSearch) params.set('search', this.filterSearch);
      const res = await API.get('/payments/list?' + params.toString());
      if (!res.error) this.allPayments = res.data || [];
      this.loading = false;
    },
    async loadStudents() {
      this.studentsLoading = true;
      const params = new URLSearchParams();
      params.set('page', this.studentPage);
      params.set('page_size', this.studentPageSize);
      if (this.studentSearch) params.set('search', this.studentSearch);
      const res = await API.get('/students?' + params.toString());
      if (!res.error) { this.studentsList = res.data?.items || []; this.studentsTotal = res.data?.total || 0; }
      this.studentsLoading = false;
    },
    async loadAllLeads() {
      const res = await API.get('/leads?page=1&page_size=100000');
      if (!res.error) this.allLeads = res.data?.items || [];
    },
    debounceStudentSearch() {
      clearTimeout(this.studentSearchTimer);
      this.studentSearchTimer = setTimeout(() => { this.studentPage = 1; this.loadStudents(); }, 300);
    },
    clearFilters() {
      this.filterDateFrom = '';
      this.filterDateTo = '';
      this.filterSearch = '';
      this.loadPayments();
    },
    goStudentPage(p) { if (p < 1 || p > this.studentTotalPages || p === '...') return; this.studentPage = p; this.loadStudents(); },
    openLead(id) { TMSStore.leadId = id; TMSStore.fromView = 'signing'; this.switchView('lead-detail'); },
    // ── New Signing ──
    openNewSigning() {
      this.signingForm = { lead_id: '', signed_at: new Date().toISOString().slice(0,10), contract_no: '', package_name: '标准课时包', total_hours: 0, price_per_hour: 0, payment_amount: 0, payment_method: '', payment_date: new Date().toISOString().slice(0,10), remark: '' };
      this.showSigningModal = true;
      if (!this.allLeads.length) this.loadAllLeads();
    },
    async submitSigning() {
      if (!this.signingForm.lead_id) { toast('请选择学生', 'error'); return; }
      if (!this.signingForm.total_hours || this.signingForm.total_hours <= 0) { toast('请输入总课时', 'error'); return; }
      if (!this.signingForm.payment_amount || this.signingForm.payment_amount <= 0) { toast('请输入收款金额', 'error'); return; }
      this.saving = true;
      const res = await API.post('/signing', this.signingForm);
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('签约成功', 'success');
      this.showSigningModal = false;
      this.loadPayments();
    },
    // ── Add Payment ──
    openAddPayment(s) {
      const c = s.contract;
      if (!c) { toast('该学生暂无合同', 'error'); return; }
      this.addPaymentContractId = c.id;
      this.addPaymentStudentName = s.name;
      this.addPaymentForm = { amount: '', method: '', note: '', payment_date: new Date().toISOString().slice(0,10) };
      this.showAddPaymentModal = true;
    },
    async submitAddPayment() {
      if (!this.addPaymentForm.amount || parseFloat(this.addPaymentForm.amount) <= 0) { toast('请输入有效金额', 'error'); return; }
      this.saving = true;
      const res = await API.post('/contracts/' + this.addPaymentContractId + '/payments', this.addPaymentForm);
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('收款成功', 'success');
      this.showAddPaymentModal = false;
      this.loadPayments();
      this.loadStudents();
    },
    // ── Delete Payment ──
    confirmDeletePayment(contractId, paymentId, amount) {
      this.deleteConfirm = {
        show: true, loading: false,
        title: '删除收款记录',
        message: `确定删除 ¥${Math.abs(amount || 0).toFixed(2)} 的收款记录？合同已收金额将同步调整。`,
        contractId, paymentId,
      };
    },
    async executeDelete() {
      const dc = this.deleteConfirm;
      if (!dc.paymentId || !dc.contractId) return;
      dc.loading = true;
      const res = await API.del('/contracts/' + dc.contractId + '/payments/' + dc.paymentId);
      dc.loading = false;
      dc.show = false;
      if (res && res.error) { toast(res.error, 'error'); return; }
      toast('已删除', 'success');
      this.loadPayments();
    },
    // ── Assign Coordinator ──
    async openAssignCoordinator(s) {
      this.assignLeadId = s.id;
      this.assignLeadName = s.name;
      this.assignCoordinatorId = s.coordinator_id || '';
      const res = await API.get('/auth/users');
      if (!res.error) {
        this.coordinators = (res.data || []).filter(u =>
          ['coordinator', 'admin', 'supervisor'].includes(u.role)
        );
      }
      this.showAssignModal = true;
    },
    async submitAssignCoordinator() {
      if (!this.assignCoordinatorId) { toast('请选择教务班主任', 'error'); return; }
      const res = await API.put('/leads/' + this.assignLeadId, { coordinator_id: parseInt(this.assignCoordinatorId) });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('教务班主任已分配', 'success');
      this.showAssignModal = false;
      this.loadStudents();
    },
    downloadStudentCSV() {
      const params = new URLSearchParams();
      if (this.studentSearch) params.set('search', this.studentSearch);
      downloadCSV('/students/export?' + params.toString(), '签约学生导出.csv');
    },
  },
  watch: {
    filterDateFrom() { this.loadPayments(); },
    filterDateTo() { this.loadPayments(); },
    filterSearch() { this.loadPayments(); },
    tab(newVal) {
      if (newVal === 'students' && !this.studentsList.length) this.loadStudents();
    },
  },
  created() {
    this.loadPayments();
    this.loadAllLeads();
  },
});

/* ════════════════════════════════════════
   SearchableSelect 可搜索下拉组件
   ════════════════════════════════════════ */
/* ════════════════════════════════════════
   Teachers 师资管理组件
   ════════════════════════════════════════ */
app.component('include-teachers', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-teachers',
  data() {
    return {
      list: [], total: 0, page: 1, pageSize: 20,
      search: '', filterLevel: '',
      levels: [], searchTimer: null,
      loading: false,
      showModal: false, editId: null, saving: false,
      form: { name: '', academic_background: '', highest_degree: '', subjects: '',
              teaching_direction: '', tools: '', teaching_style: '', level: '',
              pay_rate: '', payment_method: '', notes: '', phone: '' },
      detailId: null, detailTeacher: null,
    };
  },
  computed: {
    totalPages() { return Math.max(1, Math.ceil(this.total / this.pageSize)); },
    pageNumbers() {
      const tp = this.totalPages, p = this.page, pages = [];
      if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i); }
      else {
        pages.push(1);
        if (p > 3) pages.push('...');
        for (let i = Math.max(2, p - 1); i <= Math.min(tp - 1, p + 1); i++) pages.push(i);
        if (p < tp - 2) pages.push('...');
        pages.push(tp);
      }
      return pages;
    },
    canEdit() { return ['coordinator', 'admin', 'supervisor'].includes(this.user?.role); },
  },
  methods: {
    async load() {
      this.loading = true;
      const params = new URLSearchParams();
      params.set('page', this.page);
      params.set('page_size', this.pageSize);
      if (this.search) params.set('search', this.search);
      if (this.filterLevel) params.set('level', this.filterLevel);
      const res = await API.get('/teachers?' + params.toString());
      if (!res.error) { this.list = res.data?.items || []; this.total = res.data?.total || 0; }
      this.loading = false;
    },
    async loadLevels() {
      const res = await API.get('/teachers/levels');
      if (!res.error) this.levels = res.data || [];
    },
    debounceSearch() {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => { this.page = 1; this.load(); }, 300);
    },
    goPage(p) { if (p < 1 || p > this.totalPages || p === '...') return; this.page = p; this.load(); },
    async showDetail(t) {
      this.detailId = t.id;
      this.detailTeacher = null;
      const res = await API.get('/teachers/' + t.id);
      if (!res.error) this.detailTeacher = res.data;
    },
    closeDetail() { this.detailId = null; this.detailTeacher = null; },
    openCreate() {
      this.editId = null;
      this.form = { name: '', academic_background: '', highest_degree: '', subjects: '',
                    teaching_direction: '', tools: '', teaching_style: '', level: '',
                    pay_rate: '', payment_method: '', notes: '', phone: '' };
      this.showModal = true;
    },
    openEdit(t) {
      this.editId = t.id;
      this.form = {
        name: t.name || '',
        academic_background: t.academic_background || '',
        highest_degree: t.highest_degree || '',
        subjects: t.subjects || '',
        teaching_direction: t.teaching_direction || '',
        tools: t.tools || '',
        teaching_style: t.teaching_style || '',
        level: t.level || '',
        pay_rate: t.pay_rate || '',
        payment_method: t.payment_method || '',
        notes: t.notes || '',
        phone: t.phone || '',
      };
      this.showModal = true;
    },
    closeModal() { this.showModal = false; this.editId = null; },
    async submitSave() {
      if (!this.form.name) { toast('请输入老师姓名', 'error'); return; }
      this.saving = true;
      let res;
      if (this.editId) {
        res = await API.put('/teachers/' + this.editId, this.form);
      } else {
        res = await API.post('/teachers', this.form);
      }
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast(this.editId ? '老师信息已更新' : '老师已添加', 'success');
      this.closeModal();
      this.load();
    },
  },
  created() { this.load(); this.loadLevels(); },
});

app.component('searchable-select', {
  props: {
    items: Array,
    labelKey: { type: String, default: 'name' },
    subLabelKey: { type: String, default: '' },
    valueKey: { type: String, default: 'id' },
    placeholder: { type: String, default: '请选择...' },
    modelValue: [String, Number],
    disabled: Boolean,
  },
  emits: ['update:modelValue'],
  template: '#tpl-searchable-select',
  data() {
    return {
      searchText: '',
      isOpen: false,
      highlightIdx: 0,
    };
  },
  computed: {
    selectedLabel() {
      if (!this.modelValue || !this.items) return '';
      const item = this.items.find(i => i[this.valueKey] === this.modelValue);
      return item ? (item[this.labelKey] || '') : '';
    },
    filteredItems() {
      if (!this.searchText) return this.items || [];
      const q = this.searchText.toLowerCase();
      return (this.items || []).filter(item => {
        const label = String(item[this.labelKey] || '').toLowerCase();
        const sub = this.subLabelKey ? String(item[this.subLabelKey] || '').toLowerCase() : '';
        return label.includes(q) || sub.includes(q);
      });
    },
  },
  watch: {
    searchText() { this.highlightIdx = 0; },
    isOpen(val) { if (val) this.highlightIdx = 0; },
  },
  methods: {
    select(item) {
      if (!item) return;
      this.$emit('update:modelValue', item[this.valueKey]);
      this.searchText = '';
      this.isOpen = false;
    },
    selectFirst() {
      if (this.filteredItems.length > 0) this.select(this.filteredItems[0]);
    },
    highlightNext() {
      if (this.highlightIdx < this.filteredItems.length - 1) this.highlightIdx++;
    },
    highlightPrev() {
      if (this.highlightIdx > 0) this.highlightIdx--;
    },
    clear() {
      this.$emit('update:modelValue', null);
      this.searchText = '';
      this.$nextTick(() => { this.isOpen = true; });
    },
    close() {
      setTimeout(() => { this.isOpen = false; }, 150);
    },
  },
});

app.mount("#app");

/* ════════════════════════════════════════
   Pool 公海池组件
   ════════════════════════════════════════ */
app.component('include-pool', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-pool',
  data() {
    return {
      list: [], total: 0, page: 1, pageSize: 15,
      search: '', filterSource: 'all',
      sourceOptions: ['抖音', '小红书', '视频号', '转介绍', '线下活动', '线上', '其他'],
      showAssign: false, assignTarget: '', assignUsers: [], assignLeadId: null, assignLeadName: '',
      searchTimer: null,
    };
  },
  computed: {
    totalPages() { return Math.max(1, Math.ceil(this.total / this.pageSize)); },
    pageNumbers() {
      const tp = this.totalPages, p = this.page, pages = [];
      if (tp <= 7) { for (let i = 1; i <= tp; i++) pages.push(i); }
      else {
        pages.push(1);
        if (p > 3) pages.push('...');
        for (let i = Math.max(2, p - 1); i <= Math.min(tp - 1, p + 1); i++) pages.push(i);
        if (p < tp - 2) pages.push('...');
        pages.push(tp);
      }
      return pages;
    },
    canClaim() { return ['cs', 'consultant'].includes(this.user?.role); },
    canAssign() { return ['admin', 'supervisor'].includes(this.user?.role); },
  },
  methods: {
    async load() {
      const p = `?page=${this.page}&page_size=${this.pageSize}&status=pending&source=${this.filterSource}${this.search ? '&search=' + encodeURIComponent(this.search) : ''}`;
      const res = await API.get('/leads' + p);
      if (!res.error) { this.list = res.data?.items || []; this.total = res.data?.total || 0; }
    },
    debounceSearch() {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => { this.page = 1; this.load(); }, 300);
    },
    goPage(p) { if (p < 1 || p > this.totalPages || p === '...') return; this.page = p; this.load(); },
    openLead(id) { TMSStore.leadId = id; TMSStore.fromView = this.currentView; this.switchView('lead-detail'); },
    async claimLead(id) {
      const res = await API.put('/leads/' + id, { assignee_id: this.user.id, status: 'assigned' });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('认领成功，请尽快跟进', 'success');
      this.load();
    },
    async showAssignLead(l) {
      const res = await API.get('/auth/users');
      if (res.error) return;
      this.assignUsers = (res.data || []).filter(u => ['cs', 'consultant'].includes(u.role));
      this.assignLeadId = l.id;
      this.assignLeadName = l.name;
      this.assignTarget = '';
      this.showAssign = true;
    },
    async submitAssign() {
      if (!this.assignTarget) { toast('请选择跟进人', 'error'); return; }
      const res = await API.put('/leads/' + this.assignLeadId, { assignee_id: parseInt(this.assignTarget), status: 'assigned' });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('分配成功', 'success');
      this.showAssign = false;
      this.load();
    },
  },
  created() { this.load(); },
});

/* ════════════════════════════════════════
   Coordinator 教班主任台组件
   ════════════════════════════════════════ */
app.component('include-coordinator', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-coordinator',
  data() {
    return { stats: {}, todaySchedules: [], newlyAssignedStudents: [], myStudents: [] };
  },
  methods: {
    async load() {
      const res = await API.get('/dashboard');
      if (!res.error) {
        this.stats = res.data;
        this.newlyAssignedStudents = res.data?.newly_assigned_students || [];
      }

      const today = new Date().toISOString().slice(0, 10);

      // Today's schedules
      const todayRes = await API.get('/schedules?date_from=' + today + '&date_to=' + today + '&page_size=20');
      if (!todayRes.error) this.todaySchedules = todayRes.data?.items || [];

      // Count tutors
      const usersRes = await API.get('/auth/users');
      if (!usersRes.error) {
        const tutors = (usersRes.data || []).filter(u => u.role === 'tutor');
        this.stats.tutor_count = tutors.length;
      }

      // Weekly classes count
      const weekEnd = new Date();
      weekEnd.setDate(weekEnd.getDate() + 7);
      const weekEndStr = weekEnd.toISOString().slice(0, 10);
      const weekRes = await API.get('/schedules?date_from=' + today + '&date_to=' + weekEndStr + '&page_size=1');
      if (!weekRes.error) this.stats.weekly_classes = weekRes.data?.total || 0;

      // 我的学生（通过 coordinator_id 过滤）
      if (this.user?.id) {
        const studentRes = await API.get('/students?coordinator_id=' + this.user.id);
        if (!studentRes.error) this.myStudents = studentRes.data?.items || [];
      }
    },
    openLead(id) { TMSStore.leadId = id; TMSStore.fromView = this.currentView; this.switchView('lead-detail'); },
    remainingHours(s) {
      return Math.round((s.total_hours || 0) - (s.used_hours || 0) * 10) / 10;
    },
  },
  created() { this.load(); },
});

/* ════════════════════════════════════════
   Assignment 分配工作台组件
   ════════════════════════════════════════ */
app.component('include-assignment', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-assignment',
  data() {
    return {
      activeTab: 'leads',
      // 线索分配
      unassignedLeads: [], selectedIds: [],
      assignTarget: '', assignUsers: [],
      assignSearch: '',
      // 签约学生分配
      enrolledNoCoord: [], selectedEnrolledIds: [],
      coordTarget: '', coordinators: [],
    };
  },
  computed: {
    filteredAssignLeads() {
      if (!this.assignSearch) return this.unassignedLeads;
      const q = this.assignSearch.toLowerCase();
      return this.unassignedLeads.filter(l =>
        (l.name || '').toLowerCase().includes(q) || (l.phone || '').toLowerCase().includes(q)
      );
    },
    canAssignLeads() { return ['admin', 'supervisor'].includes(this.user?.role); },
    canAssignCoordinator() { return canUser(this.user?.role, 'lead:adjust_coordinator'); },
  },
  methods: {
    async load() {
      // 线索分配 — 仅 admin/supervisor
      if (this.canAssignLeads) {
        const [leadsRes, usersRes] = await Promise.all([
          API.get('/leads?page=1&page_size=100000&status=pending'),
          API.get('/auth/users'),
        ]);
        if (!leadsRes.error) this.unassignedLeads = leadsRes.data?.items || [];
        if (!usersRes.error) this.assignUsers = (usersRes.data || []).filter(u => ['cs', 'consultant'].includes(u.role));
      }
      // 签约学生分配 — cs/consultant/admin/supervisor
      if (this.canAssignCoordinator) {
        const [enrolledRes, usersRes2] = await Promise.all([
          API.get('/students?page=1&page_size=100000'),
          API.get('/auth/users'),
        ]);
        if (!enrolledRes.error) {
          this.enrolledNoCoord = (enrolledRes.data?.items || []).filter(s => !s.coordinator_id);
        }
        if (!usersRes2.error) {
          this.coordinators = (usersRes2.data || []).filter(u =>
            ['coordinator', 'admin', 'supervisor'].includes(u.role)
          );
        }
      }
    },
    // 线索分配
    async submitAssign() {
      if (!this.assignTarget || this.selectedIds.length === 0) { toast('请选择线索和跟进人', 'error'); return; }
      const res = await API.post('/leads/batch/assign', { lead_ids: this.selectedIds, assignee_id: parseInt(this.assignTarget) });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('分配成功', 'success');
      this.selectedIds = [];
      this.load();
    },
    // 签约学生分配
    async submitAssignCoordinator() {
      if (!this.coordTarget || this.selectedEnrolledIds.length === 0) { toast('请选择学生和班主任', 'error'); return; }
      const res = await API.post('/leads/batch/assign_coordinator', { lead_ids: this.selectedEnrolledIds, coordinator_id: parseInt(this.coordTarget) });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('班主任分配成功', 'success');
      this.selectedEnrolledIds = [];
      this.load();
    },
  },
  created() { this.load(); },
});


/* ════════════════════════════════════════
   Finance 财务管理组件
   ════════════════════════════════════════ */
app.component('include-finance', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-finance',
  data() {
    return {
      summary: {},
      contracts: [],
    };
  },
  computed: {
    utilization() {
      const sold = this.summary.total_hours_sold || 0;
      const used = this.summary.total_hours_used || 0;
      if (sold === 0) return 0;
      return (used / sold * 100).toFixed(1);
    },
  },
  methods: {
    async load() {
      const [sRes, cRes] = await Promise.all([
        API.get('/finance/summary'),
        API.get('/contracts?page_size=50'),
      ]);
      if (!sRes.error) this.summary = sRes.data || {};
      if (!cRes.error) this.contracts = cRes.data?.items || [];
    },
  },
  created() { this.load(); },
});

/* ════════════════════════════════════════
   Trials 试听管理组件
   ════════════════════════════════════════ */
app.component('include-trials', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-trials',
  data() {
    return {
      list: [], stats: { pending: 0, completed: 0, has_feedback: 0, this_month: 0, conversion_rate: 0 },
      activeTab: 'pending', search: '',
      leads: [], tutors: [],
      tabs: [
        { key: 'pending', label: '待试听' },
        { key: 'today', label: '今日试听' },
        { key: 'nofb', label: '待反馈' },
        { key: 'all', label: '全部' },
      ],
      showModal: false, editId: null, saving: false,
      loading: false, searchTimer: null,
      form: { lead_id: '', tutor_id: '', subject: '试听课', start_time: '', end_time: '', classin_link: '', remark: '' },
      feedbackForm: {},
      feedbackAction: {},
      feedbackNext: {},
      feedbackLostReason: {},
      statusMap: { pending: '待上课', completed: '已完成', cancelled: '已取消' },
    };
  },
  computed: {
    canSchedule() { return ['coordinator', 'admin', 'supervisor'].includes(this.user?.role); },
    canFeedback() { return ['cs', 'consultant', 'admin', 'supervisor'].includes(this.user?.role); },
  },
  methods: {
    _buildParams() {
      const p = new URLSearchParams();
      if (this.activeTab === 'pending') p.set('status', 'pending');
      else if (this.activeTab === 'today') {
        const today = new Date().toISOString().slice(0, 10);
        p.set('date_from', today);
        p.set('date_to', today);
      } else if (this.activeTab === 'nofb') p.set('fb', 'pending');
      if (this.search) p.set('search', this.search);
      return p.toString();
    },
    async load() {
      this.loading = true;
      const params = this._buildParams();
      const [lRes, sRes] = await Promise.all([
        API.get('/trials?' + params),
        API.get('/trials/stats'),
      ]);
      if (!lRes.error) { this.list = lRes.data?.items || []; }
      if (!sRes.error) { this.stats = sRes.data || {}; }
      this.loading = false;
    },
    async loadOptions() {
      const [leadsRes, teachersRes] = await Promise.all([
        API.get('/leads?page=1&page_size=200'),
        API.get('/teachers?page_size=500'),
      ]);
      if (!leadsRes.error) this.leads = leadsRes.data?.items || [];
      if (!teachersRes.error) this.tutors = (teachersRes.data?.items || []).map(t => ({
        id: t.id,
        display_name: t.name,
        type: 'teacher',
      }));
    },
    debounceSearch() {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => { this.load(); }, 300);
    },
    switchTab(key) { this.activeTab = key; this.load(); },
    openCreate() {
      this.editId = null;
      this.form = { lead_id: '', tutor_id: '', teacher_id: '', subject: '试听课', start_time: '', end_time: '', classin_link: '', remark: '' };
      this.showModal = true;
    },
    openEdit(t) {
      this.editId = t.id;
      this.form = {
        lead_id: t.lead_id || '',
        tutor_id: t.tutor_id || '',
        teacher_id: t.teacher_id || '',
        subject: t.subject || '试听课',
        start_time: t.start_time ? t.start_time.slice(0, 16) : '',
        end_time: t.end_time ? t.end_time.slice(0, 16) : '',
        classin_link: t.classin_link || '',
        remark: t.remark || '',
      };
      this.showModal = true;
    },
    closeModal() { this.showModal = false; this.editId = null; },
    async submitSave() {
      if (!this.form.lead_id) { toast('请选择学生', 'error'); return; }
      const hasTutor = this.form.tutor_id || this.form.teacher_id || this.selectedTutorId;
      if (!hasTutor) { toast('请选择老师', 'error'); return; }
      if (!this.form.start_time || !this.form.end_time) { toast('请选择时间', 'error'); return; }
      if (!this.form.start_time || !this.form.end_time) { toast('请选择时间', 'error'); return; }
      this.saving = true;
      let res;
      if (this.editId) {
        res = await API.put('/trials/' + this.editId, this.form);
      } else {
        res = await API.post('/trials', this.form);
      }
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast(this.editId ? '试听已更新' : '试听已安排', 'success');
      this.closeModal();
      this.load();
    },
    async submitFeedback(id) {
      const content = this.feedbackForm[id];
      if (!content || !content.trim()) return;
      const payload = {
        feedback: content,
        lead_status: this.feedbackAction[id] || 'following',
        next_action: this.feedbackNext[id] || '',
      };
      if (payload.lead_status === 'lost') {
        const reason = this.feedbackLostReason[id];
        if (!reason) { toast('标记流失请选择流失原因', 'error'); return; }
        payload.lost_reason = reason;
      }
      const res = await API.post('/trials/' + id + '/feedback', payload);
      if (res.error) { toast(res.error, 'error'); return; }
      toast('试听反馈已提交', 'success');
      this.feedbackForm[id] = '';
      this.feedbackAction[id] = 'following';
      this.feedbackNext[id] = '';
      this.feedbackLostReason[id] = '';
      this.load();
    },
  },
  created() { this.loadOptions(); this.load(); },
});

/* ════════════════════════════════════════
   成长档案
   ════════════════════════════════════════ */
app.component('include-growth', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-growth',
  data() {
    return {
      students: [],
      selectedLeadId: null,
      growth: null,
      loading: false,
      searchQuery: '',
      // 反馈弹窗
      showFeedbackModal: false,
      feedbackScheduleId: null,
      feedbackForm: {
        classin_link: '',
        content_covered: '',
        student_performance: '',
        difficulties: '',
        homework_completion: '',
        teacher_notes: '',
        next_focus: '',
      },
      feedbackSaving: false,
      feedbackPackageInfo: {},
      aiGenerating: false,
      showLeadEdit: false,
      leadEditForm: {},
      leadEditSaving: false,
      overallReport: null,
      overallReportStatus: '',
      overallReportProgress: 0,
      overallReportStep: '',
      overallReportPollTimer: null,
      showOverallReportModal: false,
      reportEditData: {},
      reportSaving: false,
      homeworkList: [],
      uploadProgress: 0,
      uploading: false,
      uploadStep: '',
      dragOver: false,
      genStatus: { progress: 0, step: '' },
      genPollTimer: null,
      // 考试弹窗
      showExamModal: false,
      examForm: { exam_date: '', exam_type: '雅思', subject: '', score: null, total_score: null, notes: '' },
      examSaving: false,
      // 录取弹窗
      showAdmissionModal: false,
      admissionForm: { target_school: '', target_major: '', application_date: '', admission_status: 'pending', admitted_school: '', admitted_major: '', final_score: '', decision_date: '', notes: '' },
      admissionSaving: false,
      // 考试删除确认
      showDeleteExamConfirm: false,
      deleteExamId: null,
    };
  },
  computed: {
    filteredStudents() {
      if (!this.searchQuery) return this.students;
      const q = this.searchQuery.toLowerCase();
      return this.students.filter(s =>
        s.name.toLowerCase().includes(q) || (s.phone && s.phone.includes(q))
      );
    },
canManage() {
      return ['cs', 'consultant', 'academic', 'coordinator', 'admin', 'supervisor'].includes(this.user?.role);
    },
    canManageAdmission() {
      return ['admin', 'supervisor'].includes(this.user?.role);
    },
    // AI 生成可爱阶段映射
    genStage() {
      const p = this.genStatus.progress;
      if (!this.aiGenerating) return { emoji: '\u{1F4D6}', label: '', anim: '' };
      const stages = [
        { max: 4,  emoji: '\u{1F971}', label: '小书侨准备开工...', anim: 'float' },
        { max: 19, emoji: '\u{1F50D}', label: '正在潜入课堂找视频...', anim: 'search' },
        { max: 34, emoji: '\u{1F3A7}', label: '竖起耳朵听课ing...', anim: 'listen' },
        { max: 54, emoji: '\u{1F4DD}', label: '奋笔疾书记笔记...', anim: 'write' },
        { max: 64, emoji: '\u{1F914}', label: '小脑瓜飞快思考...', anim: 'think' },
        { max: 79, emoji: '✨', label: '整理成报告ing...', anim: 'work' },
        { max: 89, emoji: '\u{1F3AF}', label: '最后润色检查...', anim: 'polish' },
        { max: 99, emoji: '\u{1F4AA}', label: '装订存档...', anim: 'save' },
        { max: 100,emoji: '\u{1F389}', label: '完成啦！', anim: 'celebrate' },
      ];
      return stages.find(s => p <= s.max) || stages[0];
    },
  },
  methods: {
    async loadStudents() {
      const res = await API.get('/leads?page_size=500');
      if (res.error) { toast(res.error, 'error'); return; }
      this.students = (res.data.items || res.data || []);
    },
    async selectStudent(leadId) {
      this.selectedLeadId = leadId;
      this.loadOverallReport();
      this.loading = true;
      const res = await API.get('/growth/' + leadId);
      this.loading = false;
      if (res.error) { toast(res.error, 'error'); return; }
      this.growth = res.data;
    },
    // ── 课后反馈 ──
    openFeedback(scheduleId, existing) {
      if (this.genPollTimer) { clearTimeout(this.genPollTimer); this.genPollTimer = null; }
      this.aiGenerating = false;
      this.genStatus = { progress: 0, step: '' };
      this.feedbackScheduleId = scheduleId;
      this.feedbackPackageInfo = (this.growth && this.growth.package_info) || {};
      if (existing) {
        this.feedbackForm = {
          classin_link: existing.classin_link || '',
          content_covered: existing.content_covered || '',
          student_performance: existing.student_performance || '',
          difficulties: existing.difficulties || '',
          homework_completion: existing.homework_completion || '',
          teacher_notes: existing.teacher_notes || '',
          next_focus: existing.next_focus || '',
        };
      } else {
        this.feedbackForm = { classin_link: '', content_covered: '', student_performance: '', difficulties: '', homework_completion: '', teacher_notes: '', next_focus: '' };
        // 从排课信息预填 classin_link
        if (this.growth) {
          const sched = this.growth.schedules.find(s => s.id === scheduleId);
          if (sched && sched.classin_link) this.feedbackForm.classin_link = sched.classin_link;
        }
      }
      this.showFeedbackModal = true;
    },
    async submitFeedback() {
      if (!this.feedbackForm.content_covered) { toast('请填写教学内容', 'error'); return; }
      this.feedbackSaving = true;
      const res = await API.post('/schedules/' + this.feedbackScheduleId + '/feedback', this.feedbackForm);
      this.feedbackSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('课后反馈已保存', 'success');
      this.showFeedbackModal = false;
      this.selectStudent(this.selectedLeadId);
    },
    async deleteFeedback() {
      toast('删除中...', 'success');
      const res = await API.del('/schedules/' + this.feedbackScheduleId + '/feedback');
      if (res.error) { toast(res.error, 'error'); return; }
      toast('反馈已删除', 'success');
      this.showFeedbackModal = false;
      this.selectStudent(this.selectedLeadId);
    },
    async generateFeedback() {
      const link = this.feedbackForm.classin_link;
      if (!link || !link.trim()) { toast('请先输入 ClassIn 链接', 'error'); return; }
      this.aiGenerating = true;
      this.genStatus = { progress: 0, step: '启动中...' };

      // 触发后端生成
      const res = await API.post('/schedules/' + this.feedbackScheduleId + '/feedback/generate',
        { classin_link: link });
      if (res.error) { this.aiGenerating = false; toast(res.error, 'error'); return; }

      // 轮询进度
      const poll = () => {
        this.genPollTimer = setTimeout(async () => {
          const pr = await API.get('/schedules/' + this.feedbackScheduleId + '/feedback/generate/progress');
          if (pr.error) { this.aiGenerating = false; toast(pr.error, 'error'); return; }

          const st = pr.data;
          this.genStatus = { progress: st.progress || 0, step: st.step || '' };

          if (st.status === 'done' && st.result) {
            // 完成！
            this.aiGenerating = false;
            const fb = st.result.feedback || {};
            const tr = st.result.time_range || '';
            const lc = st.result.line_count || 0;
            this.feedbackForm = {
              classin_link: link,
              content_covered: fb.content_covered || '',
              student_performance: fb.student_performance || '',
              difficulties: fb.difficulties || '',
              homework_completion: fb.homework_completion || '',
              teacher_notes: fb.teacher_notes || '',
              next_focus: fb.next_focus || '',
            };
            toast('✅ AI 反馈已生成，请审核后保存', 'success');
          } else if (st.status === 'error') {
            this.aiGenerating = false;
            toast('❌ ' + (st.error || '生成失败'), 'error');
          } else if (st.status && st.status !== 'idle') {
            // 继续轮询
            poll();
          } else {
            this.aiGenerating = false;
          }
        }, 1500);
      };
      poll();
    },
    // ── 一键复制反馈 ──
    copyFeedback(includeInternal) {
      // 获取排课信息
      const sched = this.growth?.schedules?.find(s => s.id === this.feedbackScheduleId) || {};
      const student = this.growth?.lead?.name || '';
      const subject = sched.subject || '';
      const teacher = sched.teacher_name || '';
      const date = (sched.start_time || '').slice(0, 10);
      const dur = sched.actual_duration_minutes || sched.duration_minutes || '';
      const duration = dur ? `(${dur}min)` : '';
      const fb = this.feedbackForm;

      let text = '━━━ 课后反馈 ━━━\n';
      text += `👤 学生: ${student}  📚 ${subject}  👨‍🏫 ${teacher}\n`;
      text += `📅 ${date} ${duration}\n`;
      if (this.feedbackPackageInfo && 'total_hours' in this.feedbackPackageInfo) {
        const p = this.feedbackPackageInfo;
        text += `📦 报名 ${p.total_hours}h · 已用 ${p.used_hours}h · 剩余 ${p.remaining_hours}h\n`;
      }
      text += '\n';
      text += '📖 授课内容\n';
      text += `▸ ${_stripTS(fb.content_covered) || '未填写'}\n\n`;

      text += '🙋 课堂表现\n';
      text += `▸ ${_stripTS(fb.student_performance) || '未填写'}\n\n`;

      text += '⚠️ 薄弱环节\n';
      text += `▸ ${_stripTS(fb.difficulties) || '未填写'}\n\n`;

      text += '📝 作业情况\n';
      text += `▸ ${_stripTS(fb.homework_completion) || '未填写'}\n`;

      if (includeInternal) {
        if (fb.teacher_notes) {
          text += `\n📌 教师观察\n▸ ${_stripTS(fb.teacher_notes)}\n`;
        }
        if (fb.next_focus) {
          text += `\n💡 后续建议\n▸ ${_stripTS(fb.next_focus)}\n`;
        }
      }

      text += '\n━━━ 来自 TMS 教务系统 ━━━';

      navigator.clipboard.writeText(text).then(() => {
        toast(includeInternal ? '✅ 完整版已复制到剪贴板' : '✅ 家长版已复制到剪贴板', 'success');
      }).catch(() => {
        // fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        toast(includeInternal ? '✅ 完整版已复制到剪贴板' : '✅ 家长版已复制到剪贴板', 'success');
      });
    },
    // ── 编辑学生信息 ──
    openLeadEdit() {
      const lead = this.growth?.lead || {};
      this.leadEditForm = {
        name: lead.name || '',
        phone: lead.phone || '',
        wechat: lead.wechat || '',
        source: lead.source || '',
        country: lead.country || '',
        grade: lead.grade || '',
        remark: lead.remark || '',
      };
      this.showLeadEdit = true;
    },
    async saveLeadEdit() {
      this.leadEditSaving = true;
      const res = await API.put('/leads/' + this.growth.lead.id, this.leadEditForm);
      this.leadEditSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('学生信息已更新', 'success');
      this.showLeadEdit = false;
      this.selectStudent(this.selectedLeadId);
    },
    // ── 整体学情报告 ──
    async generateOverallReport() {
      toast('正在生成学情报告...', 'success');
      if (this.overallReportPollTimer) clearTimeout(this.overallReportPollTimer);
      this.overallReport = null;
      this.overallReportStatus = 'generating';
      const res = await API.post('/growth/' + this.selectedLeadId + '/overall-report');
      if (res.error) { toast(res.error, 'error'); this.overallReportStatus = ''; return; }
      this.pollOverallReport();
    },
    async pollOverallReport() {
      this.overallReportPollTimer = setTimeout(async () => {
        const pr = await API.get('/growth/' + this.selectedLeadId + '/overall-report/progress');
        if (pr.error) { this.overallReportStatus = ''; return; }
        const st = pr.data || {};
        this.overallReportProgress = st.progress || 0;
        this.overallReportStep = st.step || '';
        if (st.status === 'done' && st.result) {
          this.overallReport = st.result;
          this.overallReportStatus = 'done';
          toast('✅ 学情报告已生成', 'success');
        } else if (st.status === 'error') {
          this.overallReportStatus = 'error';
          toast('❌ ' + (st.step || '生成失败'), 'error');
        } else if (st.status === 'generating') {
          this.pollOverallReport();
        } else {
          this.overallReportStatus = '';
        }
      }, 2000);
    },
    viewOverallReport() {
      this.showOverallReportModal = true;
      this.reportEditData = JSON.parse(JSON.stringify(this.overallReport || {}));
    },
    onEdit(event, field, idx) {
      const val = event.target.innerText.trim();
      if (idx !== undefined) {
        if (!this.reportEditData[field]) this.reportEditData[field] = [];
        this.reportEditData[field][idx] = val;
      } else {
        this.reportEditData[field] = val;
      }
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    onEditStudentInfo(event, key) {
      const val = event.target.innerText.trim();
      if (!this.reportEditData.student_info) this.reportEditData.student_info = {};
      this.reportEditData.student_info[key] = val;
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    onEditArray(event, field, idx, sub) {
      const val = event.target.innerText.trim().replace(/[：:]$/,'');
      if (!this.reportEditData[field]) this.reportEditData[field] = [];
      if (!this.reportEditData[field][idx]) this.reportEditData[field][idx] = {};
      this.reportEditData[field][idx][sub] = val;
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    onEditDim(event, key, sub) {
      const val = event.target.innerText.trim();
      if (!this.reportEditData.dimensions) this.reportEditData.dimensions = {};
      if (!this.reportEditData.dimensions[key]) this.reportEditData.dimensions[key] = {};
      this.reportEditData.dimensions[key][sub] = val;
      this.overallReport = JSON.parse(JSON.stringify(this.reportEditData));
    },
    downloadReportTxt() {
      const d = this.reportEditData || this.overallReport;
      if (!d) return;
      let txt = d.report_title + '\n\n';
      if (d.baseline) txt += '【入学前基础概况】\n' + d.baseline + '\n\n';
      if (d.learning_summary) txt += '【学习历程总结】\n' + d.learning_summary + '\n\n';
      if (d.progress) txt += '【进步方面】\n' + d.progress.map(p => '· ' + p.aspect + '：' + p.detail).join('\n') + '\n\n';
      if (d.weaknesses) txt += '【待改进方面】\n' + d.weaknesses.map(w => '· ' + w.aspect + '：' + w.detail).join('\n') + '\n\n';
      if (d.overall_assessment) txt += '【综合评估】\n' + d.overall_assessment + '\n\n';
      if (d.recommendations) txt += '【后续建议】\n' + d.recommendations.map((r,i) => (i+1) + '. ' + r).join('\n');
      const blob = new Blob([txt], {type: 'text/plain;charset=utf-8'});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (d.report_title || '学情报告') + '.txt';
      a.click();
      URL.revokeObjectURL(a.href);
    },
    async loadHomework() {
      if (!this.lead || !this.lead.id) return;
      const res = await API.get('/leads/' + this.lead.id + '/homework');
      if (!res.error) this.homeworkList = res.data || [];
    },
    handleDrop(event) {
      this.dragOver = false;
      const files = event.dataTransfer?.files;
      if (files?.length) {
        // Upload first file
        const dt = new DataTransfer();
        dt.items.add(files[0]);
        const inputEvent = { target: { files: dt.files } };
        this.uploadHomework(inputEvent);
      }
    },
    uploadHomework(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      this.uploadFileWithProgress(file);
      event.target.value = '';
    },
    uploadFileWithProgress(file) {
      const formData = new FormData();
      formData.append('file', file);
      const token = localStorage.getItem('tms_token') || '';
      this.uploadProgress = 0;
      this.uploading = true;
      this.uploadStep = '上传中...';
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/leads/' + this.lead.id + '/homework');
      xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 98);
          this.uploadProgress = Math.min(pct, 98);
        }
      };
      xhr.onload = () => {
        this.uploadProgress = 100;
        this.uploadStep = '处理中...';
        setTimeout(() => {
          this.uploading = false;
          this.uploadProgress = 0;
          this.uploadStep = '';
          if (xhr.status >= 200 && xhr.status < 300) {
            toast('作业已上传', 'success');
            this.loadHomework();
          } else {
            let msg = '上传失败';
            try { const d = JSON.parse(xhr.responseText); msg = d.error || msg; } catch(e) {}
            toast(msg, 'error');
          }
        }, 500);
      };
      xhr.onerror = () => { this.uploading = false; this.uploadProgress = 0; this.uploadStep = ''; toast('网络错误', 'error'); };
      xhr.send(formData);
    },
    async deleteHomework(fileId) {
      if (!confirm('确定删除这份作业？')) return;
      const res = await API.get('/homework/' + fileId + '/delete');
      if (res.error) { toast(res.error, 'error'); return; }
      toast('作业已删除', 'success');
      this.loadHomework();
    },
    async downloadHomework(fileId) {
      const token = localStorage.getItem('tms_token') || '';
      const a = document.createElement('a');
      a.href = '/api/homework/' + fileId + '/download?token=' + token;
      a.target = '_blank';
      a.click();
    },
    clearOverallReport() {
      this.overallReport = null;
      this.overallReportStatus = '';
      this.overallReportProgress = 0;
      this.overallReportStep = '';
    },
    async loadOverallReport() {
      const res = await API.get('/growth/' + this.selectedLeadId + '/overall-report');
      if (!res.error && res.data && res.data.report_title) {
        this.overallReport = res.data;
        this.overallReportStatus = 'done';
      }
    },
    // ── 考试成绩 ──
    openExam() {
      const d = new Date();
      this.examForm = { exam_date: d.toISOString().slice(0,10), exam_type: '雅思', subject: '', score: null, total_score: 9, notes: '' };
      this.showExamModal = true;
    },
    async submitExam() {
      if (!this.examForm.exam_date || !this.examForm.exam_type) { toast('请填写考试信息', 'error'); return; }
      this.examSaving = true;
      const res = await API.post('/growth/' + this.selectedLeadId + '/exams', this.examForm);
      this.examSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('成绩已录入', 'success');
      this.showExamModal = false;
      this.selectStudent(this.selectedLeadId);
    },
    confirmDeleteExam(id) {
      this.deleteExamId = id;
      this.showDeleteExamConfirm = true;
    },
    async deleteExam() {
      if (!this.deleteExamId) return;
      const res = await API.del('/growth/' + this.selectedLeadId + '/exams/' + this.deleteExamId);
      this.showDeleteExamConfirm = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('成绩已删除', 'success');
      this.deleteExamId = null;
      this.selectStudent(this.selectedLeadId);
    },
    // ── 录取结果 ──
    openAdmission(existing) {
      if (existing) {
        this.admissionForm = {
          target_school: existing.target_school || '',
          target_major: existing.target_major || '',
          application_date: existing.application_date || '',
          admission_status: existing.admission_status || 'pending',
          admitted_school: existing.admitted_school || '',
          admitted_major: existing.admitted_major || '',
          final_score: existing.final_score || '',
          decision_date: existing.decision_date || '',
          notes: existing.notes || '',
        };
      } else {
        this.admissionForm = { target_school: '', target_major: '', application_date: '', admission_status: 'pending', admitted_school: '', admitted_major: '', final_score: '', decision_date: '', notes: '' };
      }
      this.showAdmissionModal = true;
    },
    async submitAdmission() {
      this.admissionSaving = true;
      const existing = this.growth?.admissions?.[0];
      const res = existing
        ? await API.put('/growth/' + this.selectedLeadId + '/admissions/' + existing.id, this.admissionForm)
        : await API.post('/growth/' + this.selectedLeadId + '/admissions', this.admissionForm);
      this.admissionSaving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('录取信息已保存', 'success');
      this.showAdmissionModal = false;
      this.selectStudent(this.selectedLeadId);
    },
    // ── 工具函数 ──
    subjectColor(subject) {
      const colors = { '写作': 'bg-rose-100 text-rose-700', '口语': 'bg-blue-100 text-blue-700', '阅读': 'bg-emerald-100 text-emerald-700', '听力': 'bg-amber-100 text-amber-700' };
      return colors[subject] || 'bg-gray-100 text-gray-700';
    },
    statusColor(status) {
      const map = { 'pending': 'bg-yellow-100 text-yellow-700', 'admitted': 'bg-green-100 text-green-700', 'rejected': 'bg-red-100 text-red-700', 'waiting': 'bg-blue-100 text-blue-700' };
      return map[status] || 'bg-gray-100 text-gray-700';
    },
    statusLabel(status) {
      const map = { 'pending': '申请中', 'admitted': '已录取', 'rejected': '未录取', 'waiting': '候补中' };
      return map[status] || status;
    },
    formatDate(d) { return d ? d.slice(0,10) : ''; },
  },
  created() { this.loadStudents(); },
  unmounted() { if (this.genPollTimer) clearTimeout(this.genPollTimer); },
});

/* ==========================================
   学业分析报告组件
   ========================================== */
app.component('include-consulting', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-consulting',
  data() {
    return {
      reports: [], total: 0, page: 1, pageSize: 15, searchQuery: '',
      reportTypeFilter: 'all',
      loading: false, showViewModal: false, viewReportData: null,
    };
  },
  computed: {
    totalPages() { return Math.ceil(this.total / this.pageSize) || 1; },
    pageNumbers() {
      const p = [], tp = this.totalPages;
      for (let i = 1; i <= tp; i++) {
        if (i === 1 || i === tp || (i >= this.page - 2 && i <= this.page + 2)) p.push(i);
        else if (p[p.length-1] !== '...') p.push('...');
      }
      return p;
    },
  },
  methods: {
    async load() {
      this.loading = true;
      const params = 'page=' + this.page + '&page_size=' + this.pageSize + (this.searchQuery ? '&search=' + encodeURIComponent(this.searchQuery) : '') + (this.reportTypeFilter !== 'all' ? '&report_type=' + this.reportTypeFilter : '');
      const res = await API.get('/consulting/list?' + params);
      this.loading = false;
      if (res.error) { toast(res.error, 'error'); return; }
      this.reports = res.data.items || [];
      this.total = res.data.total || 0;
    },
    goPage(p) { if (typeof p === 'number') { this.page = p; this.load(); } },
    async viewReport(report) {
      this.loading = true;
      const res = await API.get('/leads/' + report.lead_id + '/consulting/' + report.id);
      this.loading = false;
      if (res.error) { toast(res.error, 'error'); return; }
      this.viewReportData = res.data;
      this.showViewModal = true;
    },
    async downloadConsultingReport(report, format) {
      // 直接导航到 API URL，浏览器原生处理下载（兼容移动端）
      const token = localStorage.getItem('tms_token') || '';
      const url = '/api/leads/' + report.lead_id + '/consulting/' + report.id + '/download?format=' + format + '&token=' + encodeURIComponent(token);
      const link = document.createElement('a');
      link.href = url;
      const name = (report.lead_name || '').trim();
      link.download = (name ? name + '-' : '') + '学业风险与规划报告.' + (format === 'docx' ? 'docx' : 'pdf');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },
    switchReportTypeFilter(filter) {
      this.reportTypeFilter = filter;
      this.page = 1;
      this.load();
    },
    openLead(id) {
      TMSStore.leadId = id;
      TMSStore.fromView = this.currentView;
      this.switchView('lead-detail');
    },
  },
  watch: {
    searchQuery() {
      this.page = 1;
      this.load();
    },
  },
  created() { this.load(); },
});
