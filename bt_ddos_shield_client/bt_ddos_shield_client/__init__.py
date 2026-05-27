__all__ = [
    'ShieldMetagraph',
    'ShieldTestRig',
]


def __getattr__(name: str):
    if name == 'ShieldMetagraph':
        from .shield_metagraph import ShieldMetagraph

        return ShieldMetagraph
    if name == 'ShieldTestRig':
        from .testing import ShieldTestRig

        return ShieldTestRig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
