"""Gmail: the subject of every Inbox email as a topic of its own, with
trash and reply. See docs/specs/integrations/gmail.md.

`oauth` holds Google sign-in, shared with Google Tasks."""

from .service import GmailSource

__all__ = ["GmailSource"]
