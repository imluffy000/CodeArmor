import { useEffect, useRef, useState } from 'react'

/**
 * Which of `ids` the reader is currently in, for marking a nav item current.
 *
 * Shared by the landing nav in the topbar and the dashboard sidebar, because
 * the tricky part is worth writing once: the IntersectionObserver callback
 * only reports sections whose visibility CHANGED, so the set of visible ones
 * has to be kept across calls. Deciding from `entries` alone picks whichever
 * section happened to cross the line last, which is not the same thing as the
 * one being read.
 */
export function useCurrentSection(ids, enabled = true) {
  const [current, setCurrent] = useState(null)
  const onscreen = useRef(new Set())

  // Depend on a string, not the array: callers build a fresh array every
  // render, and depending on its identity would tear down and rebuild the
  // observer on every render.
  const key = ids.join(',')

  useEffect(() => {
    if (!enabled || typeof IntersectionObserver === 'undefined') return undefined

    const list = key ? key.split(',') : []
    const nodes = list.map((id) => document.getElementById(id)).filter(Boolean)
    if (nodes.length === 0) return undefined

    // Measured rather than hardcoded: this has to clear the sticky bar, and a
    // constant here silently goes stale the next time the bar is resized.
    const bar = document.querySelector('.topbar')
    const offset = Math.round(bar ? bar.getBoundingClientRect().height : 64) + 8

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) onscreen.current.add(entry.target.id)
          else onscreen.current.delete(entry.target.id)
        })
        // `list` is in document order, so the first hit is the topmost one.
        const hit = list.find((id) => onscreen.current.has(id))
        if (hit) setCurrent(hit)
      },
      // The bottom margin stops a section counting as current the instant its
      // first pixel appears from below.
      { rootMargin: `-${offset}px 0px -55% 0px` }
    )

    nodes.forEach((node) => observer.observe(node))
    return () => {
      observer.disconnect()
      onscreen.current.clear()
    }
  }, [key, enabled])

  return current
}
