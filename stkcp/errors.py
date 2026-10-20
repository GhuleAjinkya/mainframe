class InfrastructureError(Exception):
    """A batch cannot safely complete (return code 12)."""


class AuditError(Exception):
    """An audit or report cannot be trusted (return code 8)."""

