"use client";

import { useEffect, useState } from "react";
import RepoCard from "@/components/RepoCard";
import KnowledgeBasePanel from "@/components/KnowledgeBasePanel";
import { Repo } from "@/types";

export default function ReposPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [owner, setOwner] = useState("");
  const [name, setName] = useState("");
  const [spaceId, setSpaceId] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/repos")
      .then((r) => r.json())
      .then(setRepos);
  }, []);

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const res = await fetch("/api/repos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner, name, gitbookSpaceId: spaceId }),
    });
    const repo = await res.json();
    setRepos((prev) => [...prev, repo]);
    setOwner("");
    setName("");
    setSpaceId("");
    setLoading(false);
  }

  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">Repositories</h1>

      <form
        onSubmit={handleConnect}
        className="border border-border rounded-lg bg-surface p-5 space-y-4"
      >
        <p className="text-sm font-medium">Connect a new repository</p>
        <div className="grid grid-cols-2 gap-4">
          <input
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="Owner (e.g. octocat)"
            required
            className="border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-soft"
          />
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Repo name"
            required
            className="border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-soft"
          />
        </div>
        <input
          value={spaceId}
          onChange={(e) => setSpaceId(e.target.value)}
          placeholder="GitBook space ID"
          className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-soft"
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-accent text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-[#8f4d20] transition-colors disabled:opacity-50"
        >
          {loading ? "Connecting..." : "Connect repository"}
        </button>
      </form>

      <div className="space-y-3">
        {repos.map((r) => (
          <RepoCard key={r.id} repo={r} />
        ))}
      </div>

      {/* Divider */}
      <hr className="border-border" />

      {/* Knowledge Base — shows repos with real Pinecone embeddings */}
      <KnowledgeBasePanel />
    </div>
  );
}
