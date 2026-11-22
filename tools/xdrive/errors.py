"""Exceptions raised by the xdrive package."""


class XdriveError(Exception):
    """Base of every exception the package raises."""


class LinkError(XdriveError):
    """The transport failed: no board found, or a transfer failed."""


class LinkTimeout(LinkError):
    """The board did not reply in time."""


class LinkLost(LinkError):
    """The board went away, for example because it rebooted."""


class Refused(XdriveError):
    """The board replied but refused the request (unknown endpoint, wrong kind, failed handler)."""


class InterfaceMismatch(XdriveError):
    """A name or type in xdrive.props that the board's firmware build lacks or types differently."""
