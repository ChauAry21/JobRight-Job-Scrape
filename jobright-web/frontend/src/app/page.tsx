"use client";

import { useEffect, useState, useCallback } from "react";
import styles from "./page.module.css";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Recruiter = {
  fullName: string | null;
  jobTitle: string | null;
  companyName: string | null;
  linkedinUrl: string | null;
};

type Job = {
  jobId: string | null;
  title: string | null;
  company: string | null;
  location: string | null;
  jobright_url: string | null;
  apply_url: string | null;
  linkedin_recruiters: Recruiter[];
  keywords: string[];
};

type ApiResponse = {
  jobs: Job[];
  fetched_at: string | null;
  count: number;
};

type Status = "idle" | "loading" | "refreshing" | "error";

function formatTs(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function JobCard({ job, index }: { job: Job; index: number }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article
      className={styles.card}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      <div className={styles.cardHeader}>
        <div className={styles.cardIndex}>{String(index + 1).padStart(2, "0")}</div>
        <div className={styles.cardMeta}>
          <h2 className={styles.cardTitle}>{job.title ?? "Untitled"}</h2>
          <div className={styles.cardSub}>
            <span className={styles.company}>{job.company ?? "Unknown"}</span>
            {job.location && (
              <>
                <span className={styles.dot}>·</span>
                <span className={styles.location}>{job.location}</span>
              </>
            )}
          </div>
        </div>
        <div className={styles.cardActions}>
          {job.apply_url && (
            <a
              href={job.apply_url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.applyBtn}
            >
              APPLY
            </a>
          )}
          {job.jobright_url && (
            <a
              href={job.jobright_url}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.viewBtn}
            >
              VIEW
            </a>
          )}
        </div>
      </div>

      {job.keywords.length > 0 && (
        <div className={styles.keywords}>
          {job.keywords.slice(0, 8).map((kw) => (
            <span key={kw} className={styles.tag}>
              {kw}
            </span>
          ))}
          {job.keywords.length > 8 && (
            <span className={styles.tagMore}>+{job.keywords.length - 8}</span>
          )}
        </div>
      )}

      {job.linkedin_recruiters.length > 0 && (
        <div className={styles.recruitersRow}>
          <button
            className={styles.toggleBtn}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "▾" : "▸"} {job.linkedin_recruiters.length} recruiter
            {job.linkedin_recruiters.length > 1 ? "s" : ""}
          </button>
          {expanded && (
            <div className={styles.recruiters}>
              {job.linkedin_recruiters.map((r, i) => (
                <div key={i} className={styles.recruiter}>
                  <span className={styles.recruiterName}>
                    {r.fullName ?? "Unknown"}
                  </span>
                  {r.jobTitle && (
                    <span className={styles.recruiterTitle}>{r.jobTitle}</span>
                  )}
                  {r.linkedinUrl && (
                    <a
                      href={r.linkedinUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.linkedinLink}
                    >
                      linkedin ↗
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function Home() {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const fetchCached = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const res = await fetch(`${API}/jobs`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: ApiResponse = await res.json();
      setData(json);
      setStatus("idle");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
      setStatus("error");
    }
  }, []);

  const triggerRefresh = useCallback(async () => {
    setStatus("refreshing");
    setError(null);
    try {
      const res = await fetch(`${API}/jobs/refresh`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const json: ApiResponse = await res.json();
      setData(json);
      setStatus("idle");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Refresh failed");
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    fetchCached();
  }, [fetchCached]);

  const filtered = data?.jobs.filter((j) => {
    if (!filter.trim()) return true;
    const q = filter.toLowerCase();
    return (
      j.title?.toLowerCase().includes(q) ||
      j.company?.toLowerCase().includes(q) ||
      j.location?.toLowerCase().includes(q) ||
      j.keywords.some((k) => k.toLowerCase().includes(q))
    );
  }) ?? [];

  return (
    <main className={styles.main}>
      <header className={styles.header}>
        <div className={styles.headerTop}>
          <div className={styles.titleBlock}>
            <div className={styles.cursor}>█</div>
            <h1 className={styles.title}>JOBRIGHT_FEED</h1>
          </div>
          <div className={styles.headerRight}>
            <div className={styles.tsLine}>
              last scraped: <span className={styles.tsValue}>{formatTs(data?.fetched_at ?? null)}</span>
            </div>
            <button
              className={styles.refreshBtn}
              onClick={triggerRefresh}
              disabled={status === "refreshing" || status === "loading"}
            >
              {status === "refreshing" ? "SCRAPING..." : "[ REFRESH ]"}
            </button>
          </div>
        </div>
        <div className={styles.statsBar}>
          <span className={styles.stat}>
            {status === "loading" ? "LOADING..." : `${data?.count ?? 0} JOBS`}
          </span>
          {filter && (
            <span className={styles.stat}>
              {filtered.length} MATCHED
            </span>
          )}
          <input
            className={styles.filterInput}
            placeholder="filter by title / company / keyword..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </header>

      {error && (
        <div className={styles.errorBanner}>
          <span className={styles.errorPrefix}>ERR &gt;</span> {error}
        </div>
      )}

      {status === "loading" && (
        <div className={styles.loadingBlock}>
          <span className={styles.loadingDot}>▋</span> fetching cached results...
        </div>
      )}

      {status === "refreshing" && (
        <div className={styles.loadingBlock}>
          <span className={styles.loadingDot}>▋</span> running playwright scrape, this takes ~30s...
        </div>
      )}

      {status !== "loading" && filtered.length > 0 && (
        <div className={styles.grid}>
          {filtered.map((job, i) => (
            <JobCard key={job.jobId ?? i} job={job} index={i} />
          ))}
        </div>
      )}

      {status === "idle" && data && filtered.length === 0 && (
        <div className={styles.empty}>no results{filter ? ` for "${filter}"` : ""}</div>
      )}
    </main>
  );
}
