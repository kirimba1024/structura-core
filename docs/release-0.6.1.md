# Core 0.6.1 release verification

Prepared on 2026-09-08. This release is verified with render 0.8.1, which requires
core >=0.6.1,<0.7. Publish core first, then render. Geo 0.1.0 is prepared
separately and uses the same minimum core version.

## Final core/render integration

- Source and installed-wheel suites: 598 passed, with two external-validator
  tests run separately; both passed with the Khronos glTF Validator.
- A fresh base installation of both wheels: 290 passed, 51 optional translation
  tests skipped. SciPy, geo, Amulet Core and all graphics backends are absent.
- Edit session, formats, selection, spatial, sections and preview tests: 52 passed.
- Both installed public APIs: Pyright reports zero errors and warnings.
- Both wheel/sdist builds, Twine metadata, Ruff and whitespace checks passed.

Render diagnostics no longer require SciPy and now cover SVG, VOX and the USD
encodings. Render CI checks the SciPy-free base integration and matches runtime
versions against distribution metadata. The format and geometry regression
suites exercise shared source data, transparent surfaces, missing textures,
entity placement and failure-safe output writes.

The checks below record the earlier core/geo preparation, before this final
integration pass. They do not claim that geo is published with this release.

## Changes

Core owns data, format I/O and conversion. Geometry and analysis have moved to
geo. The [migration guide](migration-0.6.1.md) lists the changed imports and
legacy placement defaults. Core retains its Structure/format API and works
within the current render/edit dependency constraints. Geo's minimum core
version is now 0.6.1; an incompatible 0.6.0 cannot satisfy it.

Formatted legacy sign text is no longer double-encoded as literal JSON. Existing
translated content is preserved, including lists, nested components and
translation keys. Malformed existing JSON no longer aborts conversion. Tests
include an actual Amulet conversion with formatted and plain sign lines.

## Checks

Python 3.9.6, NumPy 1.26.4, SciPy 1.13.1 and amulet-nbt 2.1.8 were used locally.

| Check | Result |
|---|---|
| Core source and installed wheel | 246 passed in each run |
| Geo source and installed wheel, legacy extra available | 47 passed in each run |
| Render compatibility suite | 351 passed, 2 skipped |
| Edit data API: session, formats, selection and spatial operations | 35 passed |
| Fresh base core installation, no geo/SciPy/Amulet Core | 189 passed, 50 skipped for optional translation |
| Fresh geo installation without legacy extra | 46 passed, 1 skipped |
| Public API Pyright against the installed core wheel | 0 errors, 0 warnings |
| Ruff and diff whitespace checks | Passed |
| Wheel and sdist build, Twine metadata checks | Passed for both packages |
| Dependency consistency in fresh environments | pip check passed |

Upgrading the previous core 0.6.0 build by installing the geo wheel selected
core 0.6.1 automatically. Analysis and diagnostic commands survived the transfer
between distributions. The installed analysis CLI returned valid JSON without
stderr. Runtime and distribution versions match.

The core base CI job runs every applicable test instead of maintaining a partial
file list, and asserts that geo, SciPy and Amulet Core are absent. The wheel CI
job checks the runtime version against installed package metadata.

Render and edit sources were not modified. GUI behavior is outside this release
verification; only edit's data API was exercised. Local testing does not replace
the repository's configured cross-platform checks before publication.
