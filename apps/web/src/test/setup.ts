// jsdom no implementa matchMedia ni ResizeObserver, que Carbon y el tema usan.
if (typeof window.matchMedia !== 'function') {
  window.matchMedia = (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  })
}

if (typeof window.ResizeObserver !== 'function') {
  window.ResizeObserver = class ResizeObserver {
    observe() {
      return undefined
    }
    unobserve() {
      return undefined
    }
    disconnect() {
      return undefined
    }
  }
}
