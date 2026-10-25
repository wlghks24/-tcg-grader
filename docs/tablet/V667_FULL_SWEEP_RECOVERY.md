# V667 full-sweep recovery

Deep CI executed all seven China catalog cases successfully, but a parent regression still expected exactly five. It now requires at least the original five and equality between discovered and executed case counts; no test is dropped.

Source-preflight caches are scoped only to immutable Git base/candidate scope and object digests, keyed by checkout, full ref and path. Current proof JSON, HEAD ancestry, descendant differences, dirty state and source bytes are always rechecked. Existing tamper regressions remain active.

Query fingerprint sanitation now preserves up to 64 characters so a malformed 17+ character fingerprint cannot be truncated into a valid 16-character proof. Invalid observations remain stored but excluded from training. This generation uses exact predecessor/source pins and retains every relocated manual deletion test. No device or full-model training claim follows from these checks.
