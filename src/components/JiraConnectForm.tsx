import { useState, type FormEvent } from "react";
import type { JiraConnectArgs } from "../types";

interface Props {
  busy: boolean;
  onSubmit: (args: JiraConnectArgs) => void;
  onCancel: () => void;
}

/**
 * Collects a Jira site and token. The token goes straight to the backend,
 * which checks it and keeps it in the OS keychain; it is cleared from the
 * form on submit.
 */
export function JiraConnectForm({ busy, onSubmit, onCancel }: Props) {
  const [site, setSite] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!site.trim() || !token.trim()) return;
    onSubmit({ site, email: email.trim() || null, token });
    setToken("");
  }

  return (
    <form className="jira-form" onSubmit={submit} aria-label="Connect Jira">
      <label className="field">
        <span className="field__label">Site</span>
        <input
          type="text"
          value={site}
          onChange={(e) => setSite(e.target.value)}
          placeholder="acme.atlassian.net"
          autoComplete="off"
          spellCheck={false}
          autoFocus
          required
        />
      </label>
      <label className="field">
        <span className="field__label">Email</span>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Jira Cloud only; leave empty for Data Center"
          autoComplete="off"
          spellCheck={false}
        />
      </label>
      <label className="field">
        <span className="field__label">API token</span>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Read-only scoped token recommended"
          autoComplete="off"
          required
        />
      </label>
      <p className="jira-form__hint">
        Stored in your system keychain. See <code>docs/setup/jira.md</code> to create a
        read-only token.
      </p>
      <div className="jira-form__actions">
        <button type="button" className="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button type="submit" className="button button--primary" disabled={busy}>
          {busy ? "Connecting…" : "Connect"}
        </button>
      </div>
    </form>
  );
}
