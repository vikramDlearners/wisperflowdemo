"""Domain errors. The API layer maps these to HTTP status codes in main.py."""


class NotFound(Exception):
    """The requested object does not exist inside the caller's family scope."""


class AuthError(Exception):
    """Sign-in link or session token is missing, invalid, expired or used."""


class LinkGone(Exception):
    """A genuine share link that was revoked or has expired."""
