import type { FormEvent, ReactNode } from "react";
import { useId, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  BookOpenCheck,
  Database,
  FileText,
  FlaskConical,
  LayoutDashboard,
  Puzzle,
  ShieldCheck
} from "lucide-react";
import { BrowserRouter, Link, MemoryRouter, NavLink, Route, Routes, useLocation, useParams } from "react-router-dom";

import { ApiClientProvider } from "./api/ApiClientProvider";
import { type ApiClientLike, useApiClient } from "./api/context";
import type { RunDetailResponse } from "./api/types";

const navItems = [
  { label: "Dashboard", path: "/", icon: LayoutDashboard, end: true },
  { label: "Create", path: "/create", icon: Puzzle },
  { label: "Runs", path: "/runs", icon: Activity },
  { label: "Batches", path: "/batches", icon: Database },
  { label: "Experiments", path: "/experiments", icon: FlaskConical },
  { label: "Registries", path: "/registries", icon: BookOpenCheck },
  { label: "Reports", path: "/reports", icon: FileText },
  { label: "Admin", path: "/admin/readiness", icon: ShieldCheck }
];

export function App() {
  return (
    <ApiClientProvider>
      <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AppShell />
      </BrowserRouter>
    </ApiClientProvider>
  );
}

export function AppForTest({
  initialEntries = ["/"],
  apiClient
}: {
  initialEntries?: string[];
  apiClient?: ApiClientLike;
}) {
  return (
    <ApiClientProvider client={apiClient}>
      <MemoryRouter initialEntries={initialEntries} future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AppShell />
      </MemoryRouter>
    </ApiClientProvider>
  );
}

function AppShell() {
  const location = useLocation();
  const theme = location.pathname.startsWith("/puzzles/") ? "player" : "studio";

  return (
    <div className="app-shell" data-theme={theme}>
      <aside className="sidebar" aria-label="Primary">
        <NavLink className="brand" to="/" aria-label="CrosswordAI home">
          <Puzzle aria-hidden="true" size={24} />
          <span>CrosswordAI</span>
        </NavLink>
        <nav className="nav-list">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink className="nav-link" end={item.end} to={item.path} key={item.label}>
                <Icon aria-hidden="true" size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <main className="main-panel">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/create" element={<CreatePuzzlePage />} />
          <Route path="/runs" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/source-packs/:sourcePackId" element={<SourceReviewPage />} />
          <Route path="/puzzles/:puzzleId" element={<PuzzlePlayerPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/reports/:runId" element={<ReportDetailPage />} />
          <Route path="/batches" element={<BatchesPage />} />
          <Route path="/experiments" element={<ExperimentsPage />} />
          <Route path="/registries" element={<RegistriesPage />} />
          <Route path="/admin/readiness" element={<AdminReadinessPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </div>
  );
}

function PageHeader({
  eyebrow,
  title,
  children
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <section className="workspace-header" aria-labelledby="page-title">
      <p className="eyebrow">{eyebrow}</p>
      <h1 id="page-title">{title}</h1>
      {children ? <p>{children}</p> : null}
    </section>
  );
}

function DashboardPage() {
  return (
    <>
      <PageHeader eyebrow="Studio" title="Dashboard">
        Latest run health, review queues, budget, and publishing status.
      </PageHeader>
      <section className="status-grid" aria-label="Dashboard metrics">
        <MetricCard label="Publishable" value="0" detail="No local runs loaded" status="succeeded" />
        <MetricCard label="Needs Review" value="0" detail="No quarantine queue" status="quarantined" />
        <MetricCard label="Model Cost" value="$0.00" detail="Current local session" status="running" />
        <MetricCard label="Cache Hit Rate" value="0%" detail="Awaiting model calls" status="pending" />
      </section>
    </>
  );
}

function CreatePuzzlePage() {
  const api = useApiClient();
  const fieldId = useId();
  const [theme, setTheme] = useState("");
  const [notes, setNotes] = useState("");
  const [audience, setAudience] = useState("general");
  const [difficulty, setDifficulty] = useState("standard");
  const [clueStyle, setClueStyle] = useState("direct");
  const [routeId, setRouteId] = useState("baseline-local");
  const [budget, setBudget] = useState("0.50");
  const [includeConnectors, setIncludeConnectors] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RunDetailResponse | null>(null);

  const puzzleId = useMemo(() => {
    const slug = theme
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    return slug ? `puzzle_${slug.slice(0, 32)}` : "puzzle_new";
  }, [theme]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setResult(null);
    if (!theme.trim()) {
      setError("Theme is required.");
      return;
    }
    if (!notes.trim()) {
      setError("Notes are required.");
      return;
    }
    if (Number.isNaN(Number(budget)) || Number(budget) < 0) {
      setError("Budget must be zero or greater.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await api.generatePuzzle({
        theme: theme.trim(),
        notes: notes.trim(),
        route_id: routeId,
        puzzle_id: puzzleId,
        grid_size: 5,
        clue_styles: [clueStyle],
        candidate_limit: includeConnectors ? 40 : 25
      });
      setResult(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Generation request failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <PageHeader eyebrow="Creator" title="Create Puzzle">
        Theme, source, route, and budget controls for a new generation run.
      </PageHeader>
      <form className="create-form" aria-label="Create puzzle workflow" onSubmit={handleSubmit}>
        <div className="form-grid">
          <label className="field">
            <span>Theme</span>
            <input
              name="theme"
              value={theme}
              onChange={(event) => setTheme(event.target.value)}
              placeholder="Miles Davis"
              autoComplete="off"
            />
          </label>
          <label className="field">
            <span>Audience</span>
            <select name="audience" value={audience} onChange={(event) => setAudience(event.target.value)}>
              <option value="general">General</option>
              <option value="classroom">Classroom</option>
              <option value="fans">Fan community</option>
              <option value="expert">Expert solvers</option>
            </select>
          </label>
          <label className="field">
            <span>Difficulty</span>
            <select name="difficulty" value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
              <option value="easy">Easy</option>
              <option value="standard">Standard</option>
              <option value="expert">Expert</option>
            </select>
          </label>
          <label className="field">
            <span>Model route</span>
            <select name="route" value={routeId} onChange={(event) => setRouteId(event.target.value)}>
              <option value="baseline-local">Baseline local</option>
              <option value="cheap_first_cascade">Cheap-first cascade</option>
              <option value="jury_review">Jury review</option>
              <option value="shadow_mode">Shadow mode</option>
            </select>
          </label>
          <label className="field">
            <span>Budget guardrail</span>
            <input
              name="budget"
              type="number"
              min="0"
              step="0.01"
              value={budget}
              onChange={(event) => setBudget(event.target.value)}
            />
          </label>
        </div>
        <label className="field field-wide">
          <span>Source notes</span>
          <textarea
            name="notes"
            rows={7}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Add source-supported notes, facts, quotes metadata, discography details, or topic context."
          />
        </label>
        <fieldset className="segmented-field">
          <legend>Clue style</legend>
          <div className="segmented-control">
            {["direct", "trivia", "classroom", "expert"].map((style) => (
              <label key={style}>
                <input
                  type="radio"
                  name="clue-style"
                  value={style}
                  checked={clueStyle === style}
                  onChange={(event) => setClueStyle(event.target.value)}
                />
                <span>{style}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <label className="checkbox-row" htmlFor={`${fieldId}-connectors`}>
          <input
            id={`${fieldId}-connectors`}
            type="checkbox"
            checked={includeConnectors}
            onChange={(event) => setIncludeConnectors(event.target.checked)}
          />
          <span>Prefer broader source coverage for candidate generation</span>
        </label>
        {error ? (
          <div className="form-alert" role="alert">
            {error}
          </div>
        ) : null}
        <div className="form-actions">
          <button className="primary-button" type="submit" disabled={submitting}>
            <Puzzle aria-hidden="true" size={18} />
            <span>{submitting ? "Starting..." : "Start Generation"}</span>
          </button>
        </div>
      </form>
      {result ? <GenerationStarted result={result} /> : null}
    </>
  );
}

function GenerationStarted({ result }: { result: RunDetailResponse }) {
  return (
    <section className="success-panel" aria-label="Generation started">
      <ShieldCheck aria-hidden="true" size={22} />
      <div>
        <strong>Run started</strong>
        <p>
          Status: <span>{result.run.status}</span>
        </p>
        <div className="inline-actions">
          <Link to={`/runs/${result.run.run_id}`}>Open run</Link>
          {result.run.puzzle_id ? <Link to={`/puzzles/${result.run.puzzle_id}`}>Open puzzle</Link> : null}
        </div>
      </div>
    </section>
  );
}

function RunsPage() {
  return (
    <>
      <PageHeader eyebrow="Runs" title="Generation Runs">
        Source packs, grids, clues, QA, exports, and publish decisions.
      </PageHeader>
      <ListPanel items={["Run timeline", "Source review", "Clue QA", "Publish review"]} />
    </>
  );
}

function RunDetailPage() {
  const { runId } = useParams();
  return (
    <>
      <PageHeader eyebrow="Run Detail" title={`Run ${runId ?? "unknown"}`}>
        Stage timeline, artifacts, QA scorecard, and links to puzzle exports.
      </PageHeader>
      <ListPanel items={["source_pack", "grid", "clues", "publish"]} />
    </>
  );
}

function SourceReviewPage() {
  const { sourcePackId } = useParams();
  return (
    <>
      <PageHeader eyebrow="Source Review" title={`Source Pack ${sourcePackId ?? "unknown"}`}>
        Taxonomy, evidence previews, rights status, vector notes, and graph summary.
      </PageHeader>
      <ListPanel items={["Taxonomy", "Evidence", "Rights", "Vectors", "Graph"]} />
    </>
  );
}

function PuzzlePlayerPage() {
  const { puzzleId } = useParams();
  return (
    <>
      <PageHeader eyebrow="Player" title="Puzzle Player">
        Puzzle `{puzzleId ?? "unknown"}` will render in the light player surface.
      </PageHeader>
      <section className="player-preview" aria-label="Puzzle board preview">
        <BarChart3 aria-hidden="true" size={26} />
        <strong>Board route ready</strong>
      </section>
    </>
  );
}

function ReportsPage() {
  return (
    <>
      <PageHeader eyebrow="Reports" title="Inspection Reports">
        Source coverage, clue lineage, model contribution, and export manifests.
      </PageHeader>
      <ListPanel items={["Inspection bundle", "Clue lineage", "Source coverage", "Model contribution"]} />
    </>
  );
}

function ReportDetailPage() {
  const { runId } = useParams();
  return (
    <>
      <PageHeader eyebrow="Report" title={`Report ${runId ?? "unknown"}`}>
        Enterprise inspection bundle and export-safe review material.
      </PageHeader>
      <ListPanel items={["QA scorecard", "Artifacts", "Checksums", "Lineage"]} />
    </>
  );
}

function BatchesPage() {
  return (
    <>
      <PageHeader eyebrow="Batch Lab" title="Batches">
        Multi-theme, multi-route generation status and checkpoints.
      </PageHeader>
      <ListPanel items={["Queued", "Running", "Succeeded", "Quarantined"]} />
    </>
  );
}

function ExperimentsPage() {
  return (
    <>
      <PageHeader eyebrow="Evaluation" title="Experiments">
        Route, model, prompt, retrieval, judge, and repair comparison matrices.
      </PageHeader>
      <ListPanel items={["Routes", "Models", "Prompts", "Retrieval", "Judges", "Repairs"]} />
    </>
  );
}

function RegistriesPage() {
  return (
    <>
      <PageHeader eyebrow="Control Plane" title="Registries">
        Active versions for models, prompts, routes, policies, connectors, and schemas.
      </PageHeader>
      <ListPanel items={["Models", "Prompts", "Routes", "Policies", "Connectors", "Schemas"]} />
    </>
  );
}

function AdminReadinessPage() {
  return (
    <>
      <PageHeader eyebrow="Admin" title="Production Readiness">
        Secrets, environments, egress, storage, backups, disaster recovery, and audit posture.
      </PageHeader>
      <ListPanel items={["Secrets", "RBAC", "Egress", "Backups", "Artifact signing"]} />
    </>
  );
}

function NotFoundPage() {
  return (
    <PageHeader eyebrow="404" title="Page Not Found">
      The requested route is not part of the local web app.
    </PageHeader>
  );
}

function MetricCard({
  label,
  value,
  detail,
  status
}: {
  label: string;
  value: string;
  detail: string;
  status: "succeeded" | "running" | "quarantined" | "pending";
}) {
  return (
    <article className="status-card">
      <span className={`status-dot status-${status}`} aria-hidden="true" />
      <span className="status-label">{label}</span>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  );
}

function ListPanel({ items }: { items: string[] }) {
  return (
    <section className="surface-panel" aria-label="Route sections">
      <ul className="route-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
