#!/usr/bin/env bash
# release.sh — tag and push a GitHub release for AgentAuth
#
# Usage:
#   chmod +x release.sh
#   ./release.sh
#
# This creates an annotated git tag v0.8.0 and pushes it to origin.
# GitHub will then show it under Releases — add release notes there manually.

set -e

VERSION="v0.8.0"
RELEASE_TITLE="AgentAuth v0.8.0 — Gemma offline backend + Java SDK"

echo "→ Tagging $VERSION"
git tag -a "$VERSION" -m "$RELEASE_TITLE

What's new:
- Offline policy evaluation via Gemma (HuggingFace Transformers)
- BaseEngine abstraction — Gemini and Gemma share the same interface
- Java SDK with 27 tests (MockWebServer, no live server required)
- 12 regulatory compliance templates (NBE Ethiopia, CBN Nigeria, 179 rules)
- Multi-tenant org isolation with SHA-256 hashed API keys
- HMAC-signed webhook delivery with exponential backoff retry
- 100+ tests across Python and Java

See CHANGELOG.md for the full history."

echo "→ Pushing tag to origin"
git push origin "$VERSION"

echo "✓ Done. Visit https://github.com/Kalkidan-Dagnu/agentauth/releases to add release notes."
