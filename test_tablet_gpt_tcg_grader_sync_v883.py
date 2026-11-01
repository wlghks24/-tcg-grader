"""Root-discovered V883 sync entrypoint; delegated tests retain strict review gates."""
import unittest
from execution.tests.test_tablet_sync_successor_v883 import StackedCardUISyncV883Tests

if __name__ == "__main__":
    unittest.main()
