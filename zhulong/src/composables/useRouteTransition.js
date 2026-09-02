import { nextTick, ref } from 'vue'

export const routeTransitionActive = ref(false)

const prefersReducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const preloadRouteComponents = async (router, location) => {
  const matched = router.resolve(location).matched
  const loaders = matched.flatMap((record) => Object.values(record.components || {}))
    .filter((component) => typeof component === 'function')
    .map((loader) => loader())

  if (loaders.length) await Promise.all(loaders)
}

export const navigateWithTransition = async (router, location) => {
  if (!document.startViewTransition || prefersReducedMotion()) {
    return router.push(location)
  }

  await preloadRouteComponents(router, location)

  const root = document.documentElement
  routeTransitionActive.value = true
  root.classList.add('is-route-transitioning')
  await nextTick()

  const target = typeof location === 'string'
    ? location.split('/').filter(Boolean).pop()
    : location?.name?.toString().toLowerCase()

  const transition = document.startViewTransition(async () => {
    if (target) root.dataset.routeTransitionTarget = target
    await router.push(location)
  })

  try {
    await transition.finished
  } finally {
    root.classList.remove('is-route-transitioning')
    delete root.dataset.routeTransitionTarget
    routeTransitionActive.value = false
  }
}

export const navigateWithoutTransition = async (router, location) => {
  routeTransitionActive.value = true
  await nextTick()

  try {
    await router.push(location)
    await nextTick()
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  } finally {
    routeTransitionActive.value = false
  }
}
