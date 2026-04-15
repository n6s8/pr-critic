import { memo } from 'react'

const STACK = ['FastAPI', 'React', 'TypeScript', 'LangGraph', 'Vite', 'TailwindCSS']

const LINKS = [
  {
    href: 'https://www.linkedin.com/in/nurzhan-sultanov/',
    label: 'LinkedIn',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-current">
        <path d="M6.94 8.5H3.56V20h3.38V8.5ZM5.25 3C4.17 3 3.3 3.9 3.3 5.01S4.17 7 5.25 7c1.1 0 1.96-.88 1.96-1.99C7.21 3.9 6.35 3 5.25 3Zm14.45 9.84c0-3.45-1.84-5.05-4.3-5.05-1.98 0-2.87 1.1-3.37 1.87V8.5H8.65V20h3.38v-6.28c0-.34.02-.68.13-.92.27-.68.88-1.38 1.9-1.38 1.34 0 1.87 1.04 1.87 2.56V20h3.37l.01-7.16Z" />
      </svg>
    ),
  },
  {
    href: 'https://github.com/n6s8',
    label: 'GitHub',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-current">
        <path d="M12 2C6.48 2 2 6.58 2 12.22c0 4.5 2.87 8.31 6.84 9.66.5.1.68-.22.68-.49 0-.24-.01-1.05-.01-1.9-2.78.62-3.37-1.21-3.37-1.21-.46-1.18-1.11-1.5-1.11-1.5-.91-.64.07-.63.07-.63 1 .08 1.53 1.05 1.53 1.05.9 1.56 2.35 1.11 2.92.85.09-.67.35-1.11.63-1.36-2.22-.26-4.56-1.14-4.56-5.06 0-1.12.39-2.04 1.03-2.75-.1-.26-.45-1.3.1-2.72 0 0 .85-.28 2.78 1.05A9.45 9.45 0 0 1 12 6.85c.85 0 1.7.12 2.5.35 1.93-1.33 2.78-1.05 2.78-1.05.55 1.42.2 2.46.1 2.72.64.71 1.03 1.63 1.03 2.75 0 3.93-2.35 4.8-4.59 5.05.36.32.69.94.69 1.9 0 1.37-.01 2.47-.01 2.81 0 .27.18.6.69.49A10.08 10.08 0 0 0 22 12.22C22 6.58 17.52 2 12 2Z" />
      </svg>
    ),
  },
  {
    href: 'https://t.me/sultanovnurzhan',
    label: 'Telegram',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-current">
        <path d="M20.67 3.33 2.86 10.2c-1.21.48-1.2 1.15-.22 1.45l4.57 1.43 10.58-6.72c.5-.3.96-.14.58.2l-8.57 7.74-.32 4.82c.47 0 .68-.22.94-.48l2.3-2.25 4.78 3.58c.88.49 1.5.24 1.72-.81l3.03-14.28c.33-1.29-.49-1.87-1.38-1.55Z" />
      </svg>
    ),
  },
]

function DeveloperFooterComponent() {
  return (
    <footer className="surface-panel developer-footer shrink-0 rounded-2xl px-5 py-4">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="developer-avatar-shell">
            <img
              src="/Ava.jpg"
              alt="Nurzhan Sultanov"
              className="h-14 w-14 rounded-[1.15rem] object-cover"
              loading="lazy"
              decoding="async"
            />
          </div>

          <div className="max-w-xl">
            <p className="section-label">Built by Nurzhan Sultanov</p>
            <h2 className="mt-1.5 text-lg font-semibold text-white">
              Software Engineer - Backend &amp; AI Systems
            </h2>
            <p className="mt-2 text-xs leading-6 text-slate-400">
              Focused on backend systems, code analysis, and AI-assisted developer tools.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3 xl:items-end">
          <div className="flex flex-wrap gap-1.5">
            {STACK.map(item => (
              <span key={item} className="developer-badge">
                {item}
              </span>
            ))}
          </div>

          <div className="flex items-center gap-2.5">
            {LINKS.map(link => (
              <a
                key={link.label}
                href={link.href}
                target="_blank"
                rel="noreferrer"
                className="developer-link"
                aria-label={link.label}
                title={link.label}
              >
                {link.icon}
                <span className="sr-only">{link.label}</span>
              </a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  )
}

export const DeveloperFooter = memo(DeveloperFooterComponent)
