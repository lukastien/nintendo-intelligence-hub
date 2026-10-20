"""Project errors. They subclass ValueError so model validators can raise them."""


class NihError(ValueError):
    """Base error for configuration, grain, and provenance failures."""


class ConfigurationError(NihError):
    """Raised when the warehouse target or local settings cannot be used."""


class GrainError(NihError):
    """Raised when a measure's period span does not match its dates or metric."""


class ProvenanceError(NihError):
    """Raised when a source class crosses into the wrong schema or mart."""
