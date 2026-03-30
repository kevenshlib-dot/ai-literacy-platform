import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { requiresAuth: false, title: '注册' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Home',
        component: () => import('@/views/Home.vue'),
        meta: { title: '首页', roles: ['admin', 'organizer', 'reviewer'] },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '工作台', roles: ['admin', 'organizer', 'reviewer'] },
      },
      {
        path: 'materials',
        name: 'Materials',
        component: () => import('@/views/Materials.vue'),
        meta: { title: '素材管理', roles: ['admin'] },
      },
      {
        path: 'questions',
        name: 'Questions',
        component: () => import('@/views/Questions.vue'),
        meta: { title: '题库管理', roles: ['admin', 'organizer', 'reviewer'] },
      },
      {
        path: 'exams',
        name: 'Exams',
        component: () => import('@/views/Exams.vue'),
        meta: { title: '考试管理', roles: ['admin', 'organizer'] },
      },
      {
        path: 'exams/:examId/compose',
        name: 'ExamCompose',
        component: () => import('@/views/ExamCompose.vue'),
        meta: { title: '试卷编排', roles: ['admin', 'organizer'] },
      },
      {
        path: 'take-exam',
        name: 'TakeExam',
        component: () => import('@/views/TakeExam.vue'),
        meta: { title: '在线考试', roles: ['admin', 'organizer', 'reviewer', 'examinee'] },
      },
      {
        path: 'scores',
        name: 'Scores',
        component: () => import('@/views/Scores.vue'),
        meta: { title: '成绩管理', roles: ['admin', 'organizer', 'reviewer', 'examinee'] },
      },
      {
        path: 'scores/:scoreId/diagnostic',
        name: 'ScoreDiagnostic',
        component: () => import('@/views/ScoreDiagnostic.vue'),
        meta: { title: '诊断分析报告', roles: ['admin', 'organizer', 'reviewer', 'examinee'] },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Users.vue'),
        meta: { title: '用户管理', roles: ['admin'] },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')

  // No auth required (login, register)
  if (to.meta.requiresAuth === false) {
    next()
    document.title = `${to.meta.title || ''} - AI素养评测平台`
    return
  }

  // Not logged in → redirect to login
  if (!token) {
    next({ name: 'Login' })
    return
  }

  // Role-based access check
  const roles = to.meta.roles as string[] | undefined
  if (roles) {
    const savedUserInfo = localStorage.getItem('userInfo')
    const userRole = savedUserInfo ? JSON.parse(savedUserInfo).role : null
    if (userRole && !roles.includes(userRole)) {
      // Redirect to default page for their role
      const defaultRoute = userRole === 'examinee' ? 'TakeExam' : 'Dashboard'
      next({ name: defaultRoute })
      return
    }
  }

  next()
  document.title = `${to.meta.title || ''} - AI素养评测平台`
})

export default router
