"""Route modules for the Weight Streaming API.

These modules contain the FastAPI route handlers that used to live
inside ``api_server.create_app()`` as closures. Each module exposes a
``register(app, ctx)`` factory; ``create_app`` wires them in. Splitting
the 1,700-line factory into focused modules makes the route surface
readable and keeps the middleware/lifespan wiring in one place.

Route paths and response shapes are unchanged — this is a pure
organizational refactor (behavior preserved; the full API test suite
covers every group).
"""
