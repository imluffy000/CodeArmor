import React from 'react'
import { Boxes, History, Lock, Plus } from 'lucide-react'
import { SkeletonRows, StatusIcon } from './primitives'
import { useCurrentSection } from '../lib/useCurrentSection'

// The dashboard nav. It replaces the two topbar links, which were a thin use
// of a wide bar, and it earns the space by carrying the connected
// repositories as well - the list you actually navigate by.
const NAV = [
  ['repositories', 'Repositories', Boxes],
  ['reviews', 'Recent reviews', History],
]

// Reuses the console's status vocabulary, so a syncing repository looks the
// same here as it does in the row it points at.
const SYNC_STATUS = {
  pending: 'pending',
  syncing: 'active',
  synced: 'pass',
  failed: 'fail',
}

export default function Sidebar({ repos, onSelectRepo }) {
  const current = useCurrentSection(NAV.map(([id]) => id))

  const jump = (id) => (event) => {
    event.preventDefault()
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  const openRepo = (id) => {
    onSelectRepo(id)
    document.getElementById('repositories')?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <aside className="sidebar" aria-label="Dashboard">
      <nav className="sidenav">
        {NAV.map(([id, label, Icon]) => (
          <a
            key={id}
            className="sidenav__item"
            href={`#${id}`}
            aria-current={current === id ? 'true' : undefined}
            onClick={jump(id)}
          >
            <Icon size={17} strokeWidth={1.75} aria-hidden="true" />
            <span>{label}</span>
          </a>
        ))}
      </nav>

      <div className="sidebar__group">
        <div className="sidebar__group-head">
          <span className="legend">connected</span>
          {Array.isArray(repos) && repos.length > 0 && (
            <span className="sidebar__count mono">{repos.length}</span>
          )}
        </div>

        {!Array.isArray(repos) ? (
          <SkeletonRows rows={3} bare label="Loading connected repositories" />
        ) : repos.length === 0 ? (
          <p className="sidebar__empty">
            Nothing connected yet. Add a repository to start reviewing.
          </p>
        ) : (
          <div className="siderepos">
            {repos.map((repo) => (
              // A button, not a link: it expands the row in the list rather
              // than navigating anywhere.
              <button
                key={repo.id}
                type="button"
                className="siderepo"
                title={repo.full_name}
                onClick={() => openRepo(repo.id)}
              >
                <StatusIcon status={SYNC_STATUS[repo.sync_status] || 'pending'} size={12} />
                <span className="siderepo__name mono">{repo.full_name}</span>
                {repo.private && (
                  <Lock size={11} strokeWidth={2} aria-hidden="true" className="siderepo__lock" />
                )}
                {repo.sync_status === 'synced' && (
                  <span className="siderepo__count mono" title="Open pull requests as of the last sync">
                    {repo.open_prs}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="sidebar__foot">
        <a
          className="sidenav__item sidenav__item--action"
          href="#repositories"
          onClick={jump('repositories')}
        >
          <Plus size={16} strokeWidth={2.25} aria-hidden="true" />
          <span>Add a repository</span>
        </a>
      </div>
    </aside>
  )
}
