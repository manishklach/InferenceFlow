"use client";
import { useState, useEffect, useCallback } from "react";
type Job = {
  id: string;
  status: string;
  total: number;
  completed: number;
  captured_micro_usd: number;
  usage: { input_tokens: number; output_tokens: number };
};
type ApiKey = { id: string; name: string; prefix: string; revoked: boolean };
export default function Dashboard() {
  const [dev, setDev] = useState(true);
  const [email, setEmail] = useState("developer@example.local");
  const [csrf, setCsrf] = useState("");
  const [mode, setMode] = useState("");
  const [error, setError] = useState("");
  const [wallet, setWallet] = useState({
    available_micro_usd: 0,
    reserved_micro_usd: 0,
  });
  const [jobs, setJobs] = useState<Job[]>([]);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [ledger, setLedger] = useState<unknown[]>([]);
  const [newKey, setNewKey] = useState("");
  const [prompt, setPrompt] = useState(
    "Summarize: Asynchronous inference makes batch text processing simple.",
  );
  const [output, setOutput] = useState("");
  const [busy, setBusy] = useState(false);
  const api = useCallback(
    async (path: string, method = "GET", body?: unknown) => {
      const r = await fetch("/api" + path, {
        method,
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error?.message || "Request failed");
      return data;
    },
    [csrf],
  );
  const refresh = useCallback(async () => {
    try {
      const [w, j, k, l] = await Promise.all([
        api("/v1/wallet"),
        api("/v1/jobs"),
        api("/v1/keys"),
        api("/v1/wallet/transactions"),
      ]);
      setWallet(w);
      setJobs(j.items);
      setKeys(k.items);
      setLedger(l.items);
    } catch (e) {
      setError(String(e));
    }
  }, [api]);
  useEffect(() => {
    fetch("/api/auth/config")
      .then((r) => r.json())
      .then((d) => setDev(d.development));
    fetch("/api/auth/session", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          setCsrf(d.csrf_token);
          setMode(d.mode);
        }
      });
  }, []);
  useEffect(() => {
    if (!csrf) return;
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [csrf, refresh]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function login() {
    await action(async () => {
      const d = await api("/auth/login", "POST", { email });
      setCsrf(d.csrf_token);
      setMode(d.mode);
    });
  }
  async function submit() {
    await action(async () => {
      const r = await fetch("/api/v1/jobs", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          requests: [
            {
              custom_id: "sample",
              messages: [{ role: "user", content: prompt }],
              max_output_tokens: 128,
            },
          ],
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error?.message);
      await refresh();
    });
  }
  const money = (v: number) => "$" + (v / 1000000).toFixed(6);
  return (
    <main>
      <header>
        <div className="brand">IF</div>
        <div>
          <h1>InferenceFlow</h1>
          <p>Submit work. Track execution. Pay for completed tokens.</p>
        </div>
        <span className="badge">
          {mode ? mode.toUpperCase() + " EXECUTION" : "PREPAID INFERENCE"}
        </span>
      </header>
      {error && <aside role="alert">{error}</aside>}
      {!csrf ? (
        <section className="login">
          <h2>Sign in to your workspace</h2>
          <p>
            Local development accepts an email. Production uses your managed
            identity provider.
          </p>
          <label>
            Email
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
            />
          </label>
          <button
            disabled={busy}
            onClick={
              dev ? login : () => window.location.assign("/api/auth/oidc/start")
            }
          >
            {dev ? "Sign in locally" : "Sign in with identity provider"}
          </button>
        </section>
      ) : (
        <>
          {mode === "mock" && (
            <aside>
              Local mock mode uses deterministic output and test-only rates.
              Seed credits with the development CLI.
            </aside>
          )}
          <div className="stats">
            <section>
              <small>Available credits</small>
              <strong>{money(wallet.available_micro_usd)}</strong>
            </section>
            <section>
              <small>Reserved for active work</small>
              <strong>{money(wallet.reserved_micro_usd)}</strong>
            </section>
            <section>
              <small>Jobs in this workspace</small>
              <strong>{jobs.length}</strong>
            </section>
          </div>
          <div className="grid">
            <section>
              <h2>Submit inference</h2>
              <p>Qwen3 4B · standard tier · best effort 30 minute target</p>
              <label>
                Prompt
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  rows={6}
                />
              </label>
              <button disabled={busy} onClick={submit}>
                Queue sample job
              </button>
              <p className="muted">
                Running requests may complete and be billed after cancellation.
              </p>
            </section>
            <section>
              <h2>API access</h2>
              <button
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    const k = await api("/v1/keys", "POST", {
                      name: "Dashboard key",
                    });
                    setNewKey(k.key);
                    await refresh();
                  })
                }
              >
                Create API key
              </button>
              {newKey && (
                <div>
                  <p>Copy now. This key is displayed once.</p>
                  <code>{newKey}</code>
                  <button onClick={() => setNewKey("")}>Hide</button>
                </div>
              )}
              {keys.map((k) => (
                <p key={k.id}>
                  <code>{k.prefix}…</code>{" "}
                  {k.revoked ? (
                    "revoked"
                  ) : (
                    <button
                      onClick={() =>
                        action(async () => {
                          await api("/v1/keys/" + k.id, "DELETE");
                          await refresh();
                        })
                      }
                    >
                      Revoke
                    </button>
                  )}
                </p>
              ))}
              <h3>Test credit top-up</h3>
              {[10, 25, 100].map((amount) => (
                <button
                  key={amount}
                  onClick={() =>
                    action(async () => {
                      const d = await api(
                        "/v1/billing/checkout-session",
                        "POST",
                        { amount_usd: amount },
                      );
                      window.location.assign(d.url);
                    })
                  }
                >
                  ${amount}
                </button>
              ))}
              <p className="muted">
                Stripe test mode requires configuration and the beta gate.
              </p>
            </section>
          </div>
          <section>
            <h2>Inference jobs</h2>
            <div className="scroll">
              <table>
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Status</th>
                    <th>Completed</th>
                    <th>Tokens in / out</th>
                    <th>Charge</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => (
                    <tr key={j.id}>
                      <td>
                        <code>{j.id.slice(0, 16)}…</code>
                      </td>
                      <td>{j.status}</td>
                      <td>
                        {j.completed}/{j.total}
                      </td>
                      <td>
                        {j.usage.input_tokens} / {j.usage.output_tokens}
                      </td>
                      <td>{money(j.captured_micro_usd)}</td>
                      <td>
                        <button
                          onClick={() =>
                            action(async () =>
                              setOutput(
                                JSON.stringify(
                                  await api("/v1/jobs/" + j.id + "/results"),
                                  null,
                                  2,
                                ),
                              ),
                            )
                          }
                        >
                          Results
                        </button>{" "}
                        <a href={"/api/v1/jobs/" + j.id + "/results.jsonl"}>
                          JSONL
                        </a>{" "}
                        <button
                          onClick={() =>
                            action(async () => {
                              await api("/v1/jobs/" + j.id + "/cancel", "POST");
                              await refresh();
                            })
                          }
                        >
                          Cancel
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {jobs.length === 0 && <p>No jobs yet. Submit a sample to begin.</p>}
          </section>
          {output && (
            <section>
              <h2>Results</h2>
              <pre>{output}</pre>
            </section>
          )}
          <details>
            <summary>Credit and usage ledger</summary>
            <pre>{JSON.stringify(ledger, null, 2)}</pre>
          </details>
          <button
            onClick={() =>
              action(async () => {
                await api("/auth/logout", "POST");
                setCsrf("");
                setNewKey("");
              })
            }
          >
            Sign out
          </button>
        </>
      )}
      <footer>
        InferenceFlow · API documentation at{" "}
        <a href="http://localhost:8080/docs">localhost:8080/docs</a> ·
        completion targets are best effort
      </footer>
    </main>
  );
}
