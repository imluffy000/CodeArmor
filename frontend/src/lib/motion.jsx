import React from 'react'
import { LazyMotion, domAnimation, m, useReducedMotion } from 'motion/react'

// LazyMotion + the `m` component instead of the full `motion` component.
// Importing `motion` pulls the whole feature set into the main bundle - about
// 160 kB for what this app uses, which is a few fades and a row transition.
// `domAnimation` covers transforms, opacity and layout, loaded once here.

export function MotionProvider({ children }) {
  return (
    <LazyMotion features={domAnimation} strict>
      {children}
    </LazyMotion>
  )
}

export { m, useReducedMotion }
export { AnimatePresence } from 'motion/react'

// Motion here confirms a state change and nothing more - the design direction
// is the subtle tier, 120-320ms, and every variant collapses to a plain cut
// when the viewer has asked for reduced motion.
export const EASE = [0.32, 0.72, 0, 1]

export function useVariants() {
  const reduced = useReducedMotion()

  if (reduced) {
    const none = { initial: false, animate: {}, exit: {}, transition: { duration: 0 } }
    return { fade: none, riseIn: none, popIn: none, reduced }
  }

  return {
    reduced,
    fade: {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.16, ease: EASE },
    },
    riseIn: {
      initial: { opacity: 0, y: 6 },
      animate: { opacity: 1, y: 0 },
      exit: { opacity: 0, y: -4 },
      transition: { duration: 0.2, ease: EASE },
    },
    // For a stage row the moment its agent reports in: a brief lift, so the
    // eye catches which of the six just finished without re-reading the list.
    popIn: {
      initial: { opacity: 0.6, scale: 0.97 },
      animate: { opacity: 1, scale: 1 },
      transition: { duration: 0.22, ease: EASE },
    },
  }
}
