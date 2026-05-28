/**
 * TMS — Vue 3 主应用
 * 所有组件通过 props 通信
 */
/* eslint-disable no-unused-vars */

/* ─── 工具函数 ─── */
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

/* ─── 菜单项 ─── */
const ROLE_MENU = [
  { id: 'dashboard', label: '工作台', icon: 'bi-grid-1x2-fill', roles: '*', view: 'dashboard' },
  { id: 'leads', label: '资源管理', icon: 'bi-people-fill', roles: ['admin', 'supervisor', 'cs', 'consultant'], view: 'leads' },
  { id: 'quick-add', label: '快速录入', icon: 'bi-plus-circle-fill', roles: ['cs', 'consultant', 'admin', 'supervisor'], view: 'quick-add' },
  { id: 'followup-plan', label: '跟进计划', icon: 'bi-calendar-check', roles: ['cs', 'consultant', 'academic', 'admin', 'supervisor'], view: 'followup-plan' },
  { id: 'divider1', divider: true },
  { id: 'coordinator', label: '教班主任台', icon: 'bi-speedometer2', roles: ['coordinator', 'admin', 'supervisor'], view: 'coordinator' },
  { id: 'assignment', label: '分配工作台', icon: 'bi-diagram-3-fill', roles: ['admin', 'supervisor'], view: 'assignment' },
  { id: 'schedules', label: '排课管理', icon: 'bi-calendar-week', roles: ['coordinator', 'admin', 'supervisor'], view: 'schedules' },
  { id: 'packages', label: '课时包管理', icon: 'bi-box-seam', roles: ['coordinator', 'academic', 'admin', 'supervisor'], view: 'packages' },
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
      loading: false,
      loginForm: { username: '', password: '' },
      loginError: '',
    };
  },
  computed: {
    menuItems() { return ROLE_MENU; },
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
          { label: '待分配资源', value: s.pending_unassigned ?? 0, sub: '点击分配线索', icon: 'bi-people', view: 'leads' },
          { label: '今日排课', value: s.today_followups ?? 0, sub: '查看课程安排', icon: 'bi-calendar-week', view: 'schedules' },
          { label: '待跟进', value: s.overdue ?? 0, sub: '查看跟进计划', icon: 'bi-chat-dots', view: 'followup-plan' },
          { label: '公海池', value: s.pool_count ?? 0, sub: '查看公海线索', icon: 'bi-water', view: 'pool' },
        ];
      } else if (role === 'cs' || role === 'consultant') {
        return [
          { label: '我的资源', value: s.my_total ?? 0, sub: '点击管理线索', icon: 'bi-people', view: 'leads' },
          { label: '跟进中', value: s.my_following ?? 0, sub: '正在跟进', icon: 'bi-chat-dots', view: 'leads' },
          { label: '已签约', value: s.my_enrolled ?? 0, sub: '查看签约学生', icon: 'bi-trophy', view: 'leads' },
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
      this.stats = res.data;
      this.overdueCount = res.data.overdue || 0;
      const lr = await API.get('/leads?page=1&page_size=5');
      if (!lr.error) this.recentLeads = lr.data?.items || [];
    },
    openLead(id) { window.__leadId = id; this.switchView('lead-detail'); },
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
      search: '', filters: { status: 'all', source: 'all' },
      selectedIds: [], showCreate: false, showAssign: false,
      creating: false, assignTarget: '', users: [],
      createForm: { name: '', phone: '', wechat: '', source: '其他', country: '', grade: '', remark: '' },
      sourceOptions: ['抖音', '小红书', '视频号', '转介绍', '线下活动', '线上', '其他'],
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
  },
  methods: {
    async load() {
      const p = `?page=${this.page}&page_size=${this.pageSize}&status=${this.filters.status}&source=${this.filters.source}${this.search ? '&search=' + encodeURIComponent(this.search) : ''}`;
      const res = await API.get('/leads' + p);
      if (res.error) return;
      this.list = res.data?.items || [];
      this.total = res.data?.total || 0;
    },
    debounceSearch() {
      clearTimeout(this.searchTimer);
      this.searchTimer = setTimeout(() => { this.page = 1; this.load(); }, 300);
    },
    goPage(p) { if (p < 1 || p > this.totalPages || p === '...') return; this.page = p; this.load(); },
    toggleAll(e) { this.selectedIds = e.target.checked ? this.list.map(l => l.id) : []; },
    openLead(id, ev) { if (ev?.target?.type === 'checkbox') return; window.__leadId = id; this.switchView('lead-detail'); },
    openCreate() { this.createForm = { name: '', phone: '', wechat: '', source: '其他', country: '', grade: '', remark: '' }; this.showCreate = true; },
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
    return { lead: null, followContent: '', nextAction: '', nextDate: '' };
  },
  computed: {
    canFollow() { return this.user && ['cs', 'consultant', 'coordinator', 'admin', 'supervisor'].includes(this.user.role); },
  },
  methods: {
    async load() {
      const id = window.__leadId;
      if (!id) return;
      const res = await API.get('/leads/' + id);
      if (res.error) { toast(res.error, 'error'); return; }
      this.lead = res.data;
    },
    async submitFollow() {
      if (!this.followContent.trim()) return;
      const res = await API.post('/followups', { lead_id: this.lead.id, content: this.followContent, next_action: this.nextAction, next_date: this.nextDate });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('跟进记录已保存', 'success');
      this.followContent = ''; this.nextAction = ''; this.nextDate = '';
      this.load();
    },
    goBack() { this.switchView('leads'); },
  },
  created() { this.load(); },
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
    openLead(id) { window.__leadId = id; this.switchView('lead-detail'); },
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
      tutors: [], leads: [],
      showModal: false, editId: null, saving: false,
      loading: false,
      form: { lead_id: '', tutor_id: '', subject: '', start_time: '', end_time: '', status: 'pending', remark: '' },
      statusMap: { pending: '待上课', completed: '已完成', cancelled: '已取消', in_progress: '进行中' },
    };
  },
  computed: {
    scheduleGroups() {
      const groups = {};
      for (const s of this.list) {
        const d = (s.start_time || '').slice(0, 10);
        if (!groups[d]) groups[d] = { date: d, dateLabel: this._dateLabel(d), items: [] };
        groups[d].items.push(s);
      }
      return Object.values(groups).sort((a, b) => a.date < b.date ? -1 : 1);
    },
  },
  methods: {
    _dateLabel(d) {
      const today = new Date().toISOString().slice(0, 10);
      const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
      if (d === today) return '今天 · ' + d;
      const dt = new Date(d + 'T00:00:00');
      const diff = (new Date(today + 'T00:00:00') - dt) / 86400000;
      if (diff === -1) return '明天 · ' + d;
      if (diff === -2) return '后天 · ' + d;
      return (dt.getMonth() + 1) + '月' + dt.getDate() + '日 周' + weekdays[dt.getDay()] + ' · ' + d;
    },
    async load() {
      this.loading = true;
      const params = new URLSearchParams();
      if (this.dateFrom) params.set('date_from', this.dateFrom);
      if (this.dateTo) params.set('date_to', this.dateTo);
      if (this.filterTutor) params.set('tutor_id', this.filterTutor);
      if (this.filterStatus) params.set('status', this.filterStatus);
      const res = await API.get('/schedules?' + params.toString());
      if (!res.error) { this.list = res.data?.items || []; this.total = res.data?.total || 0; }
      this.loading = false;
    },
    async loadTutors() {
      const res = await API.get('/auth/users');
      if (!res.error) { this.tutors = (res.data || []).filter(u => u.role === 'tutor' || u.active); }
    },
    async loadLeads() {
      const res = await API.get('/leads?page=1&page_size=200');
      if (!res.error) { this.leads = res.data?.items || []; }
    },
    openCreate() {
      this.editId = null;
      this.form = { lead_id: '', tutor_id: '', subject: '', start_time: '', end_time: '', status: 'pending', remark: '' };
      this.showModal = true;
    },
    openDetail(s) {
      this.editId = s.id;
      this.form = {
        lead_id: s.lead_id || '',
        tutor_id: s.tutor_id || '',
        subject: s.subject || '',
        start_time: s.start_time ? s.start_time.slice(0, 16) : '',
        end_time: s.end_time ? s.end_time.slice(0, 16) : '',
        status: s.status || 'pending',
        remark: s.remark || '',
      };
      this.showModal = true;
    },
    closeModal() { this.showModal = false; this.editId = null; },
    async submitSave() {
      if (!this.form.lead_id) { toast('请选择学生', 'error'); return; }
      if (!this.form.start_time || !this.form.end_time) { toast('请选择时间', 'error'); return; }
      this.saving = true;
      let res;
      if (this.editId) {
        res = await API.put('/schedules/' + this.editId, this.form);
      } else {
        res = await API.post('/schedules', this.form);
      }
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast(this.editId ? '排课已更新' : '排课已创建', 'success');
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
  },
  created() { this.loadTutors(); this.loadLeads(); this.load(); },
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
    openLead(id) { window.__leadId = id; this.switchView('lead-detail'); },
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
    return { stats: {}, todaySchedules: [], pendingSchedules: [] };
  },
  methods: {
    async load() {
      const res = await API.get('/dashboard');
      if (!res.error) this.stats = res.data;

      const today = new Date().toISOString().slice(0, 10);
      // Today's schedules
      const todayRes = await API.get('/schedules?date_from=' + today + '&date_to=' + today + '&page_size=20');
      if (!todayRes.error) this.todaySchedules = todayRes.data?.items || [];

      // Pending schedules
      const pendRes = await API.get('/schedules?status=pending&page_size=10');
      if (!pendRes.error) this.pendingSchedules = pendRes.data?.items || [];

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
      unassignedLeads: [], selectedIds: [],
      assignTarget: '', assignUsers: [],
    };
  },
  methods: {
    async load() {
      const [leadsRes, usersRes] = await Promise.all([
        API.get('/leads?page=1&page_size=200&status=pending'),
        API.get('/auth/users'),
      ]);
      if (!leadsRes.error) this.unassignedLeads = leadsRes.data?.items || [];
      if (!usersRes.error) this.assignUsers = (usersRes.data || []).filter(u => ['cs', 'consultant'].includes(u.role));
    },
    async submitAssign() {
      if (!this.assignTarget || this.selectedIds.length === 0) { toast('请选择线索和跟进人', 'error'); return; }
      const res = await API.post('/leads/batch/assign', { lead_ids: this.selectedIds, assignee_id: parseInt(this.assignTarget) });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('分配成功', 'success');
      this.selectedIds = [];
      this.load();
    },
  },
  created() { this.load(); },
});

/* ════════════════════════════════════════
   Packages 课时包管理组件
   ════════════════════════════════════════ */
app.component('include-packages', {
  props: ['user', 'switchView', 'roleLabel', 'statusBadge'],
  template: '#tpl-packages',
  data() {
    return {
      contracts: [], leads: [], loading: false,
      expandedId: null,
      useHours: {},
      showContractModal: false, showPackageModal: false,
      saving: false,
      contractForm: { lead_id: '', contract_no: '', total_amount: 0, signed_at: '', remark: '' },
      packageForm: { contract_id: null, name: '', total_hours: 0, price_per_hour: 0, remark: '' },
    };
  },
  methods: {
    async load() {
      this.loading = true;
      const [cRes, lRes] = await Promise.all([
        API.get('/contracts?page_size=50'),
        API.get('/leads?page=1&page_size=200'),
      ]);
      if (!cRes.error) this.contracts = cRes.data?.items || [];
      if (!lRes.error) this.leads = lRes.data?.items || [];
      this.loading = false;
    },
    async loadPackages(contractId) {
      const res = await API.get('/packages?contract_id=' + contractId);
      if (!res.error) {
        const c = this.contracts.find(c => c.id === contractId);
        if (c) c._packages = res.data || [];
      }
    },
    toggleExpand(id) {
      if (this.expandedId === id) { this.expandedId = null; return; }
      this.expandedId = id;
      this.loadPackages(id);
    },
    openCreateContract() {
      this.contractForm = { lead_id: '', contract_no: '', total_amount: 0, signed_at: '', remark: '' };
      this.showContractModal = true;
    },
    async submitContract() {
      if (!this.contractForm.lead_id) { toast('请选择学生', 'error'); return; }
      this.saving = true;
      const res = await API.post('/contracts', this.contractForm);
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('合同创建成功', 'success');
      this.showContractModal = false;
      this.load();
    },
    openAddPackage(c) {
      this.packageForm = { contract_id: c.id, name: '', total_hours: 0, price_per_hour: 0, remark: '' };
      this.showPackageModal = true;
    },
    async submitPackage() {
      if (!this.packageForm.total_hours || this.packageForm.total_hours <= 0) { toast('请输入总课时', 'error'); return; }
      this.saving = true;
      const res = await API.post('/packages', this.packageForm);
      this.saving = false;
      if (res.error) { toast(res.error, 'error'); return; }
      toast('课时包已添加', 'success');
      this.showPackageModal = false;
      this.loadPackages(this.packageForm.contract_id);
    },
    async usePackageHours(pkgId) {
      const hours = this.useHours[pkgId];
      if (!hours || hours <= 0) { toast('请输入有效课时', 'error'); return; }
      const res = await API.post('/packages/' + pkgId + '/use', { hours });
      if (res.error) { toast(res.error, 'error'); return; }
      toast('课时已记录', 'success');
      this.useHours[pkgId] = 0;
      // Reload packages
      const c = this.contracts.find(c => c._packages?.some(p => p.id === pkgId));
      if (c) this.loadPackages(c.id);
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
