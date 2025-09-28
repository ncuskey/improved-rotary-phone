"""ISBN lot optimisation toolkit."""


def main(*args, **kwargs):
    """Proxy to :func:`isbn_lot_optimizer.app.main` without importing it eagerly."""
    from .app import main as _main

    return _main(*args, **kwargs)


__all__ = ["main"]
