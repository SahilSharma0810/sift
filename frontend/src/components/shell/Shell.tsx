import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Inbox, Search } from 'lucide-react'

import { cn } from '@/utils/cn'

// Top-level app shell. Holds the global keyboard cheat-sheet trigger and
// the Cmd+K command palette mount point (wired in a later pass).
export function Shell() {
  const location = useLocation()
  return (
    <div className="flex h-screen flex-col">
      <header className="border-b">
        <div className="container flex h-14 items-center gap-6">
          <Link to="/inbox" className="font-semibold tracking-tight">
            Sift
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <NavLink
              to="/inbox"
              className={({ isActive }) =>
                cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors',
                  isActive
                    ? 'bg-accent text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )
              }
            >
              <Inbox className="h-4 w-4" />
              Inbox
            </NavLink>
            <NavLink
              to="/search"
              className={({ isActive }) =>
                cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 transition-colors',
                  isActive
                    ? 'bg-accent text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )
              }
            >
              <Search className="h-4 w-4" />
              Search
            </NavLink>
          </nav>
          <div className="ml-auto text-xs text-muted-foreground">
            <kbd className="rounded border bg-muted px-1.5 py-0.5">Cmd</kbd>{' '}
            <kbd className="rounded border bg-muted px-1.5 py-0.5">K</kbd> to
            search ·{' '}
            <kbd className="rounded border bg-muted px-1.5 py-0.5">?</kbd> for
            shortcuts
          </div>
        </div>
      </header>
      <main key={location.pathname} className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
