declare module 'vitest' {
  export const describe: (...args: unknown[]) => void
  export const it: (...args: unknown[]) => void
  export const expect: (...args: unknown[]) => {
    toBe: (...args: unknown[]) => void
    toEqual: (...args: unknown[]) => void
  }
}
