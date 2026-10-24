# SilentDesk — Core Principles

Status: draft · Last updated: 2026-10-23

These principles override everything else. A feature that conflicts with any of them is not built, or is redesigned until it no longer conflicts.

---

## Trust

### 1. Secure first
All information stored locally is encrypted at rest. Security is the default and cannot be switched off.

### 2. Corporate friendly
SilentDesk must meet the security, compliance and IT requirements that most companies apply to desktop software.

### 3. Open source and auditable
- MIT licensed, so it is free for commercial use.
- The full codebase is public and auditable. There are no closed components and no hidden behaviour.

---

## Data

### 4. Minimal local storage
SilentDesk is a client, not a system of record. Work data stays in the company's own systems (Gmail, Slack, Jira, and others) and is read from and written to them. Local storage is kept to the minimum the app needs to work.

### 5. Personal notes are the only exception
The user can keep personal notes on their machine. These notes:
- are never synced to any external system;
- are never logged;
- are encrypted like all other local data (see principle 1).

---

## Experience

### 6. Pull, not push
- **Minimal UI.** Only what is absolutely needed is on screen.
- **Queues.** Tasks and messages are shown as queues that the user works through when they choose to.
- **Notifications only in extreme cases.** They are kept for real urgency, such as "my boss is calling" or "a system is down". Nothing else interrupts the user.

---

## AI

### 7. Neutral voice
Any AI built into SilentDesk speaks in a neutral, operational and concise way.

### 8. Disclose AI-written messages
Every outgoing message written with AI carries a notice saying that AI was used, and naming SilentDesk.

### 9. Hand-typed messages stay unmarked
- A message the user typed by hand carries no AI notice.
- **Grammar correction does not count as AI-written.** If AI corrects grammar, it must keep the user's style and intent and change only what is needed to make the text correct.

---

## Open questions

- **Encryption keys (1, 5):** where do they live (OS keychain, a passphrase, hardware-backed storage), and what happens if the user loses access?
- **"Corporate friendly" (2):** which concrete requirements do we target first? For example SSO/SAML, MDM deployment, proxy support, audit logs, data residency, SOC 2-style controls.
- **Local cache (4):** may copies of Gmail, Slack or Jira data be cached locally to work offline or start faster? If so, how long are they kept, and are they encrypted under principle 1?
- **What "urgent" means (6):** is it user-defined rules, a fixed set of senders and systems, or both?
- **Disclosure wording (8):** what exact text goes in the notice, where does it go (footer or header), and does it differ between email, Slack and Jira?
- **Editing a draft (8, 9):** if the user rewrites an AI draft heavily, is it still "AI-written"? Where is the line?
