# V13.4: reviewed OSS/REA investigation and guarded patching

## Research
- Consult official TCG product catalogs, public open-source projects (e.g. TCGdex for Pokémon card data) and published API documentation for patterns; verify licenses and source coverage.
- REA (morluto/rea) is **optional**, only for owned/authorized APKs and sites. Do not use it to bypass access controls, download protected IP, or reuse third-party proprietary code. No REA analysis of commercial binary is claimed.

## Patching
- Image identity is (edition, exact catalog name), not bare Korean display name. KR, JP, US, CN-S and CN-T are distinct keys. Unsupported/contradictory image metadata fails closed.
- Every six hours a free GitHub Actions workflow checks the existing reviewed manifest and runs regression tests. It only proposes an **index.html image-field patch** as a draft PR when the validated manifest and catalog differ; otherwise no patch is created.
- No arbitrary learned code execution, third-party image scraping, dynamic patch creation, direct main writes or unreviewed auto-merge. Protected branch and existing release/tests remain mandatory.
- Dependabot already checks Python/Actions weekly and an existing autonomy job audits every four hours. This workflow does not duplicate or change those jobs.
- When a PR is reviewed, tested and merged, Android Termux obtains it using the repository's existing `bash ANDROID_UPDATE_AND_START.sh`. Actual installation requires device-side health/log evidence.
- GitHub project settings may forbid creating Actions-token PRs. Such a failure will be visible in the workflow log; it does not authorize bypassing protections.

## Data evidence
- Marketplace offer, confirmed sold, and official catalog references have different trust levels. A direct image URL is not proved by a listing URL.
- V13.3 experimental sidecar is not silently installed as part of this minimal main-repository patch.
