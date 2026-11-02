"use client";

import { useEffect, useState } from "react";
import { apiRequest, readError } from "@/lib/api";

type Proposal = { id: string; workflow_id: string; agent_id: string; target_field: string; unified_diff: string; reviewer_comment: string; status: string };

export function SelfHealingQueue({ token }: { token: string }) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState("");
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    void apiRequest<Proposal[]>("/api/v1/self-healing/proposals", token).then((rows) => { if (!cancelled) setProposals(rows); }).catch((reason: unknown) => { if (!cancelled) setError(readError(reason)); });
    return () => { cancelled = true; };
  }, [token]);
  const apply = async (proposal: Proposal) => {
    setBusyId(proposal.id); setError(""); setMessage("");
    try {
      await apiRequest(`/api/v1/self-healing/proposals/${proposal.id}/apply`, token, { method: "POST" });
      setProposals((current) => current.filter((item) => item.id !== proposal.id));
      setMessage("Prompt patch applied as a new workflow version.");
    } catch (reason) { setError(readError(reason)); }
    finally { setBusyId(""); }
  };
  return <section className="panel-card self-healing-queue" data-ui>
    <div className="section-heading"><div><h2>Prompt patch proposals</h2><p>Human corrections ready for review and application.</p></div><span className="queue-count">{proposals.length}</span></div>
    {message && <p className="capability-message" role="status">{message}</p>}{error && <p className="inline-error" role="alert">{error}</p>}
    {!token ? <div className="capability-empty capability-empty--compact"><p>Connect a workspace to load prompt proposals.</p></div> : proposals.length === 0 && !error ? <div className="capability-empty capability-empty--compact"><h3>No pending prompt patches</h3><p>Corrected approval outputs will appear here when the workspace generates a proposal.</p></div> : <div className="healing-proposals">{proposals.map((proposal) => <article key={proposal.id} className="healing-proposal"><div className="healing-proposal__meta"><strong>{proposal.target_field.replaceAll("_", " ")}</strong><span>{proposal.agent_id}</span><code>{proposal.workflow_id.slice(0, 8)}</code></div><p>{proposal.reviewer_comment || "Prompt change suggested from a human correction."}</p><pre>{proposal.unified_diff}</pre><button className="button button-quiet" disabled={busyId === proposal.id} onClick={() => void apply(proposal)}>{busyId === proposal.id ? "Applying…" : "Apply as new version"}</button></article>)}</div>}
  </section>;
}
