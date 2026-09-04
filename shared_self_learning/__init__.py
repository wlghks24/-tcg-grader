"""Shared SELFREFINE algorithms and contracts only.

Both Main and Instagram TCG may import this package. It must remain stateless:
no domain collectors, renderers, runtime services, credentials, provider/retry
state, ledgers, or persisted learning data.
"""

SHARED_SELF_LEARNING_CONTRACT_VERSION = 2
