import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: () => import('../components/AppLayout.vue'),
    meta: { requiresAuth: true },
    redirect: '/chat',
    children: [
      { path: '/chat', name: 'Chat', component: () => import('../views/Chat.vue') },
      { path: '/inspection', name: 'Inspection', component: () => import('../views/Inspection.vue') },
      { path: '/history', name: 'History', component: () => import('../views/History.vue') },
      { path: '/feedback', name: 'FeedbackAdmin', component: () => import('../views/FeedbackAdmin.vue'), meta: { adminOnly: true } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to, from, next) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.token) return next('/login')
  if (to.meta.adminOnly && !auth.isAdmin) return next('/chat')
  if (to.path === '/login' && auth.token) return next('/chat')
  next()
})

export default router
