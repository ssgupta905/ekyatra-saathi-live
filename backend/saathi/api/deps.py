"""FastAPI dependencies.

Routes receive the container through `Depends(get_container)` rather than
reaching into `request.app.state` themselves, so a test can swap it with
`app.dependency_overrides` and nothing else in a router has to change.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..bootstrap.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


#: Annotate a handler parameter with this to receive the container.
ContainerDep = Annotated[Container, Depends(get_container)]
