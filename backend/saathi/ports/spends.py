"""Where a family's spends are kept. Read by the family and by Saathi, nobody else."""

from __future__ import annotations

from typing import Protocol

from ..domain.spends import SpendEntry, SpendSource, StatedLimit


class SpendStore(Protocol):
    def save(self, entry: SpendEntry) -> SpendEntry: ...

    def get(self, patient_id: str, entry_id: str) -> SpendEntry | None: ...

    def by_id(self, entry_id: str) -> SpendEntry | None:
        """For a gateway's webhook, which names the entry and not the family."""
        ...

    def entries(self, patient_id: str) -> tuple[SpendEntry, ...]: ...

    def by_source(self, source: SpendSource, source_ref: str) -> SpendEntry | None:
        """The entry a provider's reference made; a repeat delivery is not a second spend."""
        ...

    def patients(self) -> tuple[str, ...]:
        """Families with anything recorded."""
        ...

    def save_limit(self, limit: StatedLimit) -> None: ...

    def limit(self, patient_id: str) -> StatedLimit | None: ...

    def clear(self, patient_id: str) -> None:
        """Forget one family's spends. Only a demo reset does this."""
        ...
