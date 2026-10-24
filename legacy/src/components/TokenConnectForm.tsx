import { useState, type FormEvent, type ReactNode } from "react";

export interface TokenField {
  name: string;
  label: string;
  placeholder: string;
  /** The secret field is a password input and is cleared on submit. */
  secret?: boolean;
  required?: boolean;
  type?: "text" | "email";
}

interface Props {
  label: string;
  fields: TokenField[];
  hint: ReactNode;
  busy: boolean;
  /** Empty optional fields are sent as `null`. */
  onSubmit: (values: Record<string, string | null>) => void;
  onCancel: () => void;
}

/**
 * Collects a server address and a token for services that sign in with a
 * user-owned token (Jira, GitHub). The token goes straight to the backend,
 * which checks it and keeps it in the OS keychain; it is cleared from the
 * form on submit.
 */
export function TokenConnectForm({ label, fields, hint, busy, onSubmit, onCancel }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});

  function submit(e: FormEvent) {
    e.preventDefault();
    if (fields.some((f) => f.required && !values[f.name]?.trim())) return;
    const out: Record<string, string | null> = {};
    for (const f of fields) {
      const v = values[f.name] ?? "";
      out[f.name] = f.secret || v.trim() ? v : null;
    }
    onSubmit(out);
    setValues((prev) => {
      const next = { ...prev };
      for (const f of fields) if (f.secret) next[f.name] = "";
      return next;
    });
  }

  return (
    <form className="token-form" onSubmit={submit} aria-label={label}>
      {fields.map((f, i) => (
        <label key={f.name} className="field">
          <span className="field__label">{f.label}</span>
          <input
            type={f.secret ? "password" : (f.type ?? "text")}
            value={values[f.name] ?? ""}
            onChange={(e) => setValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
            placeholder={f.placeholder}
            autoComplete="off"
            spellCheck={false}
            autoFocus={i === 0}
            required={f.required}
          />
        </label>
      ))}
      <p className="token-form__hint">{hint}</p>
      <div className="token-form__actions">
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

/** The sign-in form for each service that takes a token. */
export const TOKEN_FORMS = {
  jira: {
    label: "Connect Jira",
    fields: [
      { name: "site", label: "Site", placeholder: "acme.atlassian.net", required: true },
      {
        name: "email",
        label: "Email",
        placeholder: "Jira Cloud only; leave empty for Data Center",
        type: "email",
      },
      {
        name: "token",
        label: "API token",
        placeholder: "Read-only scoped token recommended",
        secret: true,
        required: true,
      },
    ],
    hint: (
      <>
        Stored in your system keychain. See <code>docs/setup/jira.md</code> to create a
        read-only token.
      </>
    ),
  },
  github: {
    label: "Connect GitHub",
    fields: [
      {
        name: "server",
        label: "Server",
        placeholder: "Leave empty for github.com; or github.acme.com",
      },
      {
        name: "token",
        label: "Token",
        placeholder: "Fine-grained, read-only token recommended",
        secret: true,
        required: true,
      },
    ],
    hint: (
      <>
        Stored in your system keychain. See <code>docs/setup/github.md</code> to create a
        read-only token.
      </>
    ),
  },
} satisfies Record<string, { label: string; fields: TokenField[]; hint: ReactNode }>;

export type TokenService = keyof typeof TOKEN_FORMS;
