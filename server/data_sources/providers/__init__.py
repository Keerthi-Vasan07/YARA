"""Online data-provider implementations.

Providers are deliberately isolated from the local scientific-reader registry.
Both sides produce a two-dimensional, north-up geographic grid for the shared
renderer, but neither depends on the other's transport or storage details.
"""

from .base import DatasetDefinition, DatasetProvider, NormalizedGrid, ProviderError
from .opendap import OPeNDAPProvider

__all__ = ["DatasetDefinition", "DatasetProvider", "NormalizedGrid", "ProviderError", "OPeNDAPProvider"]
