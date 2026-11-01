"""Root-discovered V884 exact recovery and tamper checks; no device approval."""
import unittest
from execution.tests.test_sync_chain_recovery_v884 import SyncChainRecoveryV884Tests
from execution.tests.test_v881_cached_lineage_bridge import V881CachedBridgeTests

if __name__ == "__main__":
    unittest.main()
