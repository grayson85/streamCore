# StreamCore Changelog

## [2.0.0] - 2025-12-09

### Added
- **Database-level merge**: Auto-merge duplicates during collection
- **Source tracking**: `sc_merge_log` table tracks which sources are merged
- **New fields**: `vod_en` (English name), `vod_time_hits`
- **Smart deduplication**: Zero-downtime merge in temp DB before swap
- **Merge script**: `merge_dedupe.py` for manual merge operations
- **Standardized CLI**: Consistent `--mode` flag for all collection modes

### Changed
- **API performance**: 100x faster queries (no runtime deduplication)
- **CLI format**: Standardized to `--mode full|incremental|details-only`
- **README**: Updated with current features and architecture
- **Operation guide**: Updated with new CLI format

### Removed
- **API-level deduplication**: Replaced with database-level merge
- **Test scripts**: Cleaned up development test files
- **Outdated docs**: Removed planning and redundant documentation

### Fixed
- **MacCMS format**: Corrected `vod_play_url` separator ($$$ between sources)
- **Source names**: Populate empty `vod_play_from` with meaningful names
- **ID queries**: Intelligent duplicate finding for consistent results

---

## [1.0.0] - 2025-12-07

### Initial Release
- MacCMS V10 compatible API
- Multi-source data collection
- Category mapping system
- Read-write isolation architecture
- Full-text search support
- Incremental collection mode
- Operation modes (add_update, add, update)
