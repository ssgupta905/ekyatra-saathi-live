"""Ports: what the application needs from the outside world.

Protocols only. They import the domain and nothing else, so an adapter — memory,
SQL, a cloud service — can be swapped in by configuration without the code that
uses the port noticing.
"""
