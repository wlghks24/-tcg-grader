"""Include the exact menu descendant and tamper proofs in existing root CI."""
import unittest


def load_tests(loader, tests, pattern):
    return loader.loadTestsFromName(
        "execution.tests.test_menu_resize_successor_20261122"
    )


if __name__ == "__main__":
    unittest.main()
