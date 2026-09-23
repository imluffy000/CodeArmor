import React, { useEffect } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Boxes,
  Bug,
  Check,
  CheckCircle2,
  ChevronRight,
  Database,
  FileCode2,
  FlaskConical,
  GitMerge,
  GitPullRequest,
  Layers,
  Lock,
  MessageSquare,
  Scale,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Workflow,
  XCircle,
  Zap,
} from 'lucide-react'
import { GithubMark } from './BrandIcons'

const REPO = 'https://github.com/imluffy000/CodeArmor'

/* ==========================================================================
   The landing page explains the product with the product.

   Every diagram and mock on this page is built from the same primitives the
   console uses - the same rows, the same hairlines, the same status vocabulary
   of icon plus label, the same mono for every number and path. Nothing here
   is an illustration of CodeArmor; it is CodeArmor, at rest.

   The page is also deliberately NOT a run of equal card grids. Each section
   gets the composition its content actually wants: a split for the hero and
   the console, a dense multi-column panel for the capability system, an
   editorial lead for the use cases, a node chain for the architecture, a
   vertical trail for the data path, and an action list for contact.
   ========================================================================== */

/* --------------------------------------------------------------- mock data */

// One consistent pull request runs through the whole page: the same repo, the
// same number, the same head SHA, the same findings. A landing page that shows
// three different fake PRs reads as three unrelated screenshots.
const PR = {
  repo: 'acme/api',
  number: 482,
  title: 'feat: rotate API keys on revoke',
  head: 'feat/key-rotation',
  base: 'main',
  sha: '9f2c1ab',
  files: 14,
  added: 486,
  removed: 122,
}

const AGENT_RESULTS = [
  { agent: 'security', status: 'fail', result: '2 findings', severity: 'CRITICAL' },
  { agent: 'quality', status: 'warn', result: '1 finding', severity: 'MEDIUM' },
  { agent: 'performance', status: 'pass', result: 'clean' },
  { agent: 'testing', status: 'warn', result: '1 finding', severity: 'LOW' },
  { agent: 'architecture', status: 'pass', result: 'clean' },
  { agent: 'integration', status: 'fail', result: '2 findings', severity: 'HIGH' },
]

const GATES = [
  { gate: 'conflicts', status: 'pass', detail: 'clean against main' },
  { gate: 'ci', status: 'fail', detail: 'unit-tests, typecheck' },
  { gate: 'base drift', status: 'warn', detail: '3 commits behind' },
  { gate: 'schema', status: 'fail', detail: 'drops users.api_key' },
  { gate: 'contracts', status: 'warn', detail: '2 symbols removed' },
  { gate: 'dependencies', status: 'pass', detail: 'lockfile in sync' },
  { gate: 'config', status: 'warn', detail: '1 undocumented var' },
  { gate: 'coverage', status: 'warn', detail: '86% of diff read' },
]

const AFFECTED = [
  { path: 'app/services/key_service.py', count: 2 },
  { path: 'app/api/routes/keys.py', count: 1 },
  { path: 'migrations/0042_drop_api_key.py', count: 1 },
  { path: 'tests/test_keys.py', count: 1 },
]

const STATUS_ICON = { pass: CheckCircle2, warn: AlertTriangle, fail: XCircle }

/* ------------------------------------------------------------------ content */

const CAPABILITIES = [
  {
    icon: ShieldAlert,
    title: 'Security',
    body: 'Injection, authorization gaps, leaked secrets, unsafe deserialization, weak crypto.',
    signals: ['leaked secrets', 'injection', 'authorization gaps', 'weak crypto'],
  },
  {
    icon: Zap,
    title: 'Efficiency',
    body: 'N+1 queries, blocking I/O on async paths, unbounded memory, missing indexes.',
    signals: ['N+1 queries', 'blocking I/O', 'unbounded memory', 'missing indexes'],
  },
  {
    icon: Layers,
    title: 'Integration',
    body: 'Removed routes, unsafe migrations, dependency drift, undocumented config.',
    signals: ['removed routes', 'migrations', 'dependency drift', 'undocumented config'],
  },
  {
    icon: GitMerge,
    title: 'Merge gate',
    body: 'Ten deterministic gates, each reporting pass, check or fail with a reason.',
    signals: ['CI', 'contracts', 'conflicts', 'coverage'],
  },
]

const PRIMARY_USE = {
  icon: ShieldCheck,
  title: 'A gate before merge',
  body: 'Run it on an open pull request and read the verdict first. It ranks what has to be fixed rather than leaving thirty equally weighted comments to trawl through.',
}

const SUPPORTING_USES = [
  {
    icon: BookOpen,
    title: 'Code you did not write',
    body: 'On an outside contribution the integration agent is the one that earns its keep: routes removed from under live callers, destructive migrations, contracts quietly broken.',
  },
  {
    icon: Boxes,
    title: 'Dependency and config drift',
    body: 'Manifest and lockfile disagreeing, a major version bump arriving without a note, an environment variable added to the code but never to the example file.',
  },
  {
    icon: MessageSquare,
    title: 'Interrogating a result',
    body: 'Every review is stored with its findings and its trace, so it can be reopened later and asked why a finding matters or how to apply a suggested fix.',
  },
]

const ARCHITECTURE = [
  { label: 'GitHub', sub: 'OAuth, read scope' },
  { label: 'Pull request', sub: 'diff, checks, mergeability' },
  { label: 'CodeArmor', sub: 'scope and budget' },
  { label: 'Specialist agents', sub: 'six, in parallel' },
  { label: 'Evaluation', sub: 'scored against a baseline' },
  { label: 'Merge gate', sub: 'deterministic verdict' },
]

const PLATFORM = [
  {
    icon: Workflow,
    title: 'Multi-agent pipeline',
    foot: 'six agents, one verdict',
    body: 'A LangGraph fan-out to six specialists and a single reconciliation node. Per-agent progress streams to the console over server-sent events while the review is still running.',
  },
  {
    icon: Activity,
    title: 'Observability',
    foot: 'per-agent cost',
    body: 'One trace per review and one span per agent, recording model, latency, tokens, cost, findings kept and findings dropped in validation. A per-review spend ceiling stops a runaway.',
  },
  {
    icon: FlaskConical,
    title: 'Evaluation',
    foot: '85 offline checks',
    body: 'Golden fixtures with labelled expected findings, scored on every push and gated against a recorded baseline, so a prompt edit is a measured change rather than a hopeful one.',
  },
  {
    icon: Lock,
    title: 'Security engineering',
    foot: '161 tests',
    body: 'Encrypted tokens at rest, CSRF on every state-changing request, per-user scoping on every endpoint, and prompt-injection defences that treat diff content as data and never as instructions.',
  },
]

// The origin stage carries no policy of its own; the four that follow are the
// four policies, in the order your code actually moves through them.
const DATA_TRAIL = [
  {
    icon: FileCode2,
    stage: 'your code',
    title: 'A pull request you chose to connect',
    body: 'Nothing is read until you ask for a review, and only in repositories you connected yourself. You pick them one at a time; there is no organisation-wide grant.',
  },
  {
    icon: Database,
    stage: 'what leaves the system',
    title: 'The diff, to one model provider',
    body: 'Reviewing a pull request sends its diff to an AI model provider. That is the only place your code is transmitted, and CodeArmor does not keep a copy of it.',
  },
  {
    icon: Scale,
    stage: 'ai analysis',
    title: 'Analysis, not approval',
    body: 'Nothing is posted to GitHub unless you ask, and CodeArmor never submits an approval on your behalf. A clear verdict means nothing blocking was found, not that the change is correct. A human review is still required.',
  },
  {
    icon: ScrollText,
    stage: 'what is stored',
    title: 'Findings, not source',
    body: 'Your GitHub identity, the repositories you choose to connect, and the reviews you run - findings, summary and cost metadata. Access tokens are encrypted at rest, with a key held separately from the session secret.',
  },
  {
    icon: Trash2,
    stage: 'your data controls',
    title: 'Revoking and erasing',
    body: 'Deleting your account revokes CodeArmor access to GitHub and erases your connected repositories and every stored review. It is in the account menu, it takes one confirmation, and it cannot be undone.',
  },
]

const CONTACT = [
  {
    icon: ShieldAlert,
    title: 'Report a vulnerability',
    foot: 'private disclosure',
    body: 'Use GitHub private vulnerability reporting, so the details stay confidential until a fix ships. Please do not open a public issue for a security problem.',
    href: `${REPO}/security/advisories/new`,
    action: 'Open a private report',
  },
  {
    icon: Bug,
    title: 'Bugs and requests',
    foot: 'public tracker',
    body: 'A wrong finding, a missed one, or a gate that fired when it should not have. The repository language and the diff size are what make one reproducible.',
    href: `${REPO}/issues`,
    action: 'Open an issue',
  },
  {
    icon: GitPullRequest,
    title: 'Source and documentation',
    foot: 'read the code',
    body: 'The README documents the agent pipeline, the security model, the observability data and the evaluation harness, including the limits of each.',
    href: REPO,
    action: 'View the repository',
  },
]

/* --------------------------------------------------------------- fragments */

function SectionHead({ index, label, title, lede, align = 'left' }) {
  return (
    <header className={`shead${align === 'center' ? ' shead--center' : ''}`}>
      <span className="shead__label">
        <span className="shead__index">{index}</span>
        {label}
      </span>
      <h2>{title}</h2>
      {lede && <p>{lede}</p>}
    </header>
  )
}

function StatusCell({ status, size = 13 }) {
  const Icon = STATUS_ICON[status] || AlertTriangle
  return <Icon size={size} strokeWidth={2} className={`sig sig--${status}`} aria-hidden="true" />
}

/** The pull request as CodeArmor reports it. Used in the hero. */
function AnalysisMock() {
  return (
    <figure className="mock" aria-label={`CodeArmor report for ${PR.repo} pull request ${PR.number}`}>
      <div className="mock__bar">
        <span className="mock__crumbs mono">
          {PR.repo}
          <span className="mock__slash">/</span>
          <strong>#{PR.number}</strong>
        </span>
        <span className="tag tag--fail">blocked</span>
      </div>

      <div className="mock__pr">
        <p className="mock__title">{PR.title}</p>
        {/* Separate spans rather than one string with separators in it: the
            line wraps at this width, and a literal bullet strands itself at
            the start of the second line. */}
        <p className="mock__meta mono">
          <span>{PR.files} files</span>
          <span>
            <span className="mock__add">+{PR.added}</span>{' '}
            <span className="mock__del">-{PR.removed}</span>
          </span>
          <span>
            {PR.head} → {PR.base}
          </span>
        </p>
      </div>

      <div className="mock__group">
        <span className="legend">agents</span>
        <div className="mock__rows">
          {AGENT_RESULTS.map((a) => (
            <div key={a.agent} className="mrow">
              <StatusCell status={a.status} />
              <span className="mrow__name mono">{a.agent}</span>
              <span className="mrow__value mono">{a.result}</span>
              {a.severity ? (
                <span className={`tag tag--${a.severity.toLowerCase()}`}>{a.severity}</span>
              ) : (
                <span className="mrow__pad" />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mock__group">
        <span className="legend">merge gate</span>
        <div className="mock__gates">
          {GATES.map((g) => (
            <div key={g.gate} className="gcell">
              <StatusCell status={g.status} size={11} />
              <span className="gcell__name mono">{g.gate}</span>
              <span className="gcell__detail mono">{g.detail}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mock__verdict">
        <XCircle size={17} strokeWidth={2} className="sig sig--fail" aria-hidden="true" />
        <div>
          <strong>Not ready to merge</strong>
          <span>3 blocking findings and 1 failing check</span>
        </div>
      </div>
    </figure>
  )
}

/** The console as it looks once a review has finished. */
function ConsoleMock() {
  return (
    <figure className="mock" aria-label="The CodeArmor review console">
      <div className="mock__bar">
        <span className="mock__crumbs mono">
          {PR.repo}
          <span className="mock__slash">/</span>
          <strong>#{PR.number}</strong>
        </span>
        <span className="mock__bar-end">
          <span className="mono mock__loc">{PR.sha}</span>
          <span className="tag tag--fail">blocked</span>
        </span>
      </div>

      <div className="mock__readouts">
        {[
          ['42', 'score', 'needs work'],
          ['6', 'findings', '3 blocking'],
          ['4', 'files', 'with findings'],
          ['86%', 'diff read', 'of 14 files'],
        ].map(([value, label, hint]) => (
          <div key={label} className="mreadout">
            <span className="mreadout__value mono">{value}</span>
            <span className="legend">{label}</span>
            <span className="mreadout__hint">{hint}</span>
          </div>
        ))}
      </div>

      <div className="mock__group">
        <span className="legend">progress</span>
        <div className="mock__rows">
          {AGENT_RESULTS.map((a) => (
            <div key={a.agent} className="mrow">
              <CheckCircle2 size={13} strokeWidth={2} className="sig sig--pass" aria-hidden="true" />
              <span className="mrow__name mono">{a.agent}</span>
              <span className="mrow__value mono">{a.result}</span>
              <span className="mrow__pad mono">done</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mock__group">
        <span className="legend">affected files</span>
        <div className="mock__rows">
          {AFFECTED.map((f) => (
            <div key={f.path} className="mrow mrow--file">
              <FileCode2 size={12} strokeWidth={2} aria-hidden="true" />
              <span className="mrow__name mono">{f.path}</span>
              <span className="mrow__count mono">{f.count}</span>
            </div>
          ))}
        </div>
      </div>
    </figure>
  )
}

/** A single finding, rendered with the console's own finding component. */
function FindingMock() {
  return (
    <figure className="mock mock--finding" aria-label="A finding in detail">
      <div className="mock__bar">
        <span className="legend">finding 1 of 6</span>
        <span className="mono mock__loc">line 78</span>
      </div>

      <div className="finding finding--critical">
        <header className="finding__head">
          <span className="tag tag--critical">CRITICAL</span>
          <span className="tag">security</span>
          <span className="tag">2 agents agreed</span>
        </header>

        <p className="legend mono mock__path">app/services/key_service.py</p>

        <div className="finding__block">
          <h4>Problem</h4>
          <p className="finding__text">
            The revoked key is compared with <code>==</code>, which short-circuits on the first
            differing byte. The comparison time leaks the length and the prefix of the stored
            key, which is enough to recover it one byte at a time.
          </p>
        </div>

        <div className="finding__block">
          <h4>Current</h4>
          <div className="code-well code-well--del">
            <pre>if provided == stored_key:</pre>
          </div>
        </div>

        <div className="finding__block">
          <h4>Suggested fix</h4>
          <div className="code-well code-well--add">
            <pre>if hmac.compare_digest(provided, stored_key):</pre>
          </div>
        </div>
      </div>
    </figure>
  )
}

/* ------------------------------------------------------------------- page */

export default function Landing({ onLogin }) {
  // The browser tries to honour a hash before React has mounted anything, so
  // a cold load of /#policies finds no such element and stays at the top.
  // Repeat the jump once the sections actually exist.
  useEffect(() => {
    const id = window.location.hash.slice(1)
    if (!id) return
    const target = document.getElementById(id)
    if (target) target.scrollIntoView()
  }, [])

  return (
    <div className="lp">
      {/* ------------------------------------------------------------ hero */}
      <section className="hero">
        <div className="hero__copy">
          <div className="hero__eyebrow">
            <span className="dot dot--warn" aria-hidden="true" />
            <span className="legend">six agents, one verdict</span>
          </div>
          <h1>
            Know what breaks
            <br />
            <em>before</em> you merge.
          </h1>
          <p>
            Six specialist reviewers read your pull request in parallel. Then a deterministic
            gate tells you exactly what has to be fixed first - conflicts, failing checks,
            unsafe migrations, removed routes, dependency drift.
          </p>
          <div className="hero__actions">
            <button className="btn btn--primary" onClick={onLogin}>
              <GithubMark size={14} />
              Sign in with GitHub
            </button>
            <a className="btn" href="#capabilities">
              What it checks
              <ChevronRight size={13} strokeWidth={2} aria-hidden="true" />
            </a>
          </div>

          <dl className="hero__facts">
            {[
              ['6', 'specialist agents'],
              ['10', 'deterministic gates'],
              ['0', 'auto-approvals'],
            ].map(([value, label]) => (
              <div key={label}>
                <dt className="mono">{value}</dt>
                <dd className="legend">{label}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="hero__demo">
          <AnalysisMock />
        </div>
      </section>

      {/* ------------------------------------------- 01 product experience */}
      <section id="product" className="sect">
        <SectionHead
          index="01"
          label="the product"
          title="What a finished review looks like"
          lede="Not a summary you have to interpret. A verdict, the gates behind it, and every finding with the line it sits on, the reason it matters and the change that fixes it."
        />
        <div className="showcase">
          <div className="showcase__main">
            <ConsoleMock />
          </div>
          <div className="showcase__aside">
            <FindingMock />
            <p className="showcase__note">
              Severity, category and agreement are attached to every finding. Two agents reaching
              the same conclusion independently is recorded, because it is the difference between
              a guess and a corroborated one.
            </p>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ 02 what it checks */}
      <section id="capabilities" className="sect">
        <SectionHead
          index="02"
          label="coverage"
          title="What it checks"
          lede="Four questions asked of every pull request. Each is answered by a specialist with its own prompt, its own severity rubric and its own place in the report, rather than by one general pass that grades everything at once."
        />
        <div className="capsys">
          {CAPABILITIES.map(({ icon: Icon, title, body, signals }) => (
            <div key={title} className="capsys__row">
              <div className="capsys__id">
                <Icon size={17} strokeWidth={1.75} aria-hidden="true" />
                <h3>{title}</h3>
              </div>
              <p className="capsys__body">{body}</p>
              <ul className="capsys__signals">
                {signals.map((signal) => (
                  <li key={signal} className="signal mono">
                    {signal}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------- 03 where it fits */}
      <section id="uses" className="sect">
        <SectionHead
          index="03"
          label="uses"
          title="Where it fits"
          lede="CodeArmor is built for the minutes before a merge, on repositories you have explicitly connected. It is a second reader with a long attention span, not a replacement for the first one."
        />

        <div className="feature">
          <div className="feature__copy">
            <span className="legend">primary use</span>
            <h3>
              <PRIMARY_USE.icon size={18} strokeWidth={1.75} aria-hidden="true" />
              {PRIMARY_USE.title}
            </h3>
            <p>{PRIMARY_USE.body}</p>
            <ul className="feature__list">
              <li>
                <Check size={13} strokeWidth={2.5} aria-hidden="true" />
                One verdict, not a queue of equally weighted comments
              </li>
              <li>
                <Check size={13} strokeWidth={2.5} aria-hidden="true" />
                Blocking findings separated from advisory ones
              </li>
              <li>
                <Check size={13} strokeWidth={2.5} aria-hidden="true" />
                Nothing posted to the pull request unless you ask
              </li>
            </ul>
          </div>

          <div className="feature__visual">
            <div className="chain chain--compact" role="img" aria-label="A pull request passes through CodeArmor, which returns a verdict, before merge">
              <div className="chain__node">
                <span className="mono">open PR</span>
                <span className="legend">#{PR.number}</span>
              </div>
              <span className="chain__link" aria-hidden="true" />
              <div className="chain__node chain__node--active">
                <span className="mono">CodeArmor</span>
                <span className="legend">six agents, ten gates</span>
              </div>
              <span className="chain__link" aria-hidden="true" />
              <div className="chain__node">
                <span className="mono">verdict</span>
                <span className="legend">blocked · caution · clear</span>
              </div>
              <span className="chain__link chain__link--gated" aria-hidden="true" />
              <div className="chain__node chain__node--muted">
                <span className="mono">merge</span>
                <span className="legend">a human decides</span>
              </div>
            </div>
          </div>
        </div>

        <div className="strip">
          {SUPPORTING_USES.map(({ icon: Icon, title, body }) => (
            <div key={title}>
              <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
              <h3>{title}</h3>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ------------------------------------------ 04 inside the application */}
      <section id="platform" className="sect">
        <SectionHead
          index="04"
          label="architecture"
          title="Inside the application"
          lede="The parts that decide whether an AI review can be trusted are the ones nobody sees: what each agent cost, which findings were discarded before you saw them, and whether a prompt change made the output better or merely different."
          align="center"
        />

        <div className="chain" role="img" aria-label="GitHub to pull request to CodeArmor to specialist agents to evaluation to the deterministic merge gate">
          {ARCHITECTURE.map(({ label, sub }, i) => (
            <React.Fragment key={label}>
              {i > 0 && <span className="chain__link" aria-hidden="true" />}
              <div className={`chain__node${i === ARCHITECTURE.length - 1 ? ' chain__node--active' : ''}`}>
                <span className="mono">{label}</span>
                <span className="legend">{sub}</span>
              </div>
            </React.Fragment>
          ))}
        </div>

        <div className="specs">
          {PLATFORM.map(({ icon: Icon, title, body, foot }) => (
            <div key={title} className="specs__item">
              <div className="specs__head">
                <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
                <h3>{title}</h3>
                <span className="specs__foot mono">{foot}</span>
              </div>
              <p>{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ----------------------------------------------- 05 security and data */}
      <section id="policies" className="sect">
        <SectionHead
          index="05"
          label="security and data"
          title="Where your code goes"
          lede="Stated plainly, because a review tool asks for access to private source code. This is the path a pull request actually takes through the system, and the README documents the same behaviour endpoint by endpoint."
        />

        <ol className="trail">
          {DATA_TRAIL.map(({ icon: Icon, stage, title, body }) => (
            <li key={stage} className="trail__step">
              <span className="trail__marker" aria-hidden="true">
                <Icon size={14} strokeWidth={2} />
              </span>
              <div className="trail__body">
                <span className="trail__stage legend">{stage}</span>
                <h3>{title}</h3>
                <p>{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* -------------------------------------------------------- 06 contact */}
      <section id="contact" className="sect">
        <SectionHead
          index="06"
          label="contact"
          title="Three channels, all public"
          lede="Account and data requests need no conversation: revocation and erasure live in the account menu and take effect immediately."
        />

        <div className="contact">
          {CONTACT.map(({ icon: Icon, title, body, foot, href, action }) => (
            <a key={title} className="action" href={href} target="_blank" rel="noreferrer">
              <span className="action__icon">
                <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
              </span>
              <span className="action__text">
                <strong>{title}</strong>
                <span className="action__body">{body}</span>
                <span className="action__foot mono">{foot}</span>
              </span>
              <span className="action__go">
                {action}
                <ArrowRight size={13} strokeWidth={2} aria-hidden="true" />
              </span>
            </a>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- close */}
      <section id="start" className="closer">
        <div className="closer__copy">
          <h2>Connect GitHub</h2>
          <p>
            Reviewing a pull request sends its diff to an AI model provider. CodeArmor does not
            store your code, and never approves a pull request on your behalf.
          </p>
        </div>

        <ul className="closer__features">
          {[
            'You choose which repositories it can see',
            'Nothing is posted to GitHub unless you ask',
            'Revoke access and erase your data from the account menu',
          ].map((line) => (
            <li key={line}>
              <Check size={13} strokeWidth={2.5} aria-hidden="true" />
              <span>{line}</span>
            </li>
          ))}
        </ul>

        <button className="btn btn--primary" onClick={onLogin}>
          <GithubMark size={14} />
          Sign in with GitHub
        </button>
      </section>
    </div>
  )
}
