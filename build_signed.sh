#!/bin/bash
# Build and sign Covalent locally with Apple code signing + notarization.
# 
# Required environment variables (set these or export before running):
#   APPLE_SIGNING_IDENTITY - e.g. "Developer ID Application: Your Name (TEAMID)"
#   APPLE_ID              - Your Apple ID email
#   APPLE_PASSWORD        - App-specific password (generate at appleid.apple.com > Sign-In and Security > App-Specific Passwords)
#   APPLE_TEAM_ID         - Your 10-character team ID
#
# To find your signing identity, run:
#   security find-identity -v -p codesigning
#
# Usage:
#   export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (ABC123XYZ)"
#   export APPLE_ID="you@example.com"
#   export APPLE_PASSWORD="xxxx-xxxx-xxxx-xxxx"
#   export APPLE_TEAM_ID="ABC123XYZ"
#   ./build_signed.sh

set -e

# Load from .env file if it exists
if [ -f .env ]; then
  echo "Loading variables from .env..."
  grep -E '^APPLE_' .env > /tmp/apple_env_vars.sh
  set -a
  source /tmp/apple_env_vars.sh
  set +a
  rm /tmp/apple_env_vars.sh
fi

# Check required environment variables
if [ -z "$APPLE_SIGNING_IDENTITY" ]; then
  echo "Error: APPLE_SIGNING_IDENTITY is not set"
  echo "Run: security find-identity -v -p codesigning"
  exit 1
fi

if [ -z "$APPLE_ID" ]; then
  echo "Error: APPLE_ID is not set (your Apple ID email)"
  exit 1
fi

if [ -z "$APPLE_PASSWORD" ]; then
  echo "Error: APPLE_PASSWORD is not set (app-specific password from appleid.apple.com)"
  exit 1
fi

if [ -z "$APPLE_TEAM_ID" ]; then
  echo "Error: APPLE_TEAM_ID is not set (your 10-char team ID)"
  exit 1
fi

echo "=== Configuration ==="
echo "Signing Identity: $APPLE_SIGNING_IDENTITY"
echo "Apple ID: $APPLE_ID"
echo "Team ID: $APPLE_TEAM_ID"
echo ""

# Step 1: Build server binaries
echo "=== Step 1: Building server binaries ==="
bash build_servers.sh

# Step 2: Fix Python.framework for notarization (same as GitHub workflow)
echo ""
echo "=== Step 2: Fixing Python.framework for notarization ==="
find dist-servers -type d -name "Python.framework" | while read -r framework; do
  echo "Processing framework: $framework"
  
  # Remove _CodeSignature directories
  find "$framework" -name "_CodeSignature" -type d -exec rm -rf {} + 2>/dev/null || true
  
  # Find the actual Python binary
  actual_binary=""
  for vdir in "$framework/Versions"/*/; do
    if [ -f "${vdir}Python" ] && [ ! -L "${vdir}Python" ]; then
      actual_binary="${vdir}Python"
      break
    fi
  done
  
  if [ -z "$actual_binary" ]; then
    echo "  Warning: Could not find actual Python binary, skipping"
    continue
  fi
  echo "  Found actual binary: $actual_binary"
  
  # Strip existing signature
  codesign --remove-signature "$actual_binary" 2>/dev/null || true
  
  # Replace Versions/Current with real directory + binary
  rm -rf "$framework/Versions/Current" 2>/dev/null || true
  mkdir -p "$framework/Versions/Current"
  cp "$actual_binary" "$framework/Versions/Current/Python"
  
  # Replace top-level Python with real binary
  rm -f "$framework/Python" 2>/dev/null || true
  rm -rf "$framework/Python" 2>/dev/null || true
  cp "$actual_binary" "$framework/Python"
  
  # Strip signatures from copies
  codesign --remove-signature "$framework/Versions/Current/Python" 2>/dev/null || true
  codesign --remove-signature "$framework/Python" 2>/dev/null || true
  
  echo "  Framework fixed"
done

# Remove all remaining _CodeSignature directories
find dist-servers -name "_CodeSignature" -type d -exec rm -rf {} + 2>/dev/null || true

# Strip signatures from ALL Mach-O binaries
echo "Stripping all existing signatures..."
find dist-servers -type f | while read -r file; do
  if file "$file" | grep -q "Mach-O"; then
    codesign --remove-signature "$file" 2>/dev/null || true
  fi
done

# Step 3: Sign all server binaries
echo ""
echo "=== Step 3: Signing server binaries ==="
find dist-servers -type f | while read -r file; do
  if file "$file" | grep -q "Mach-O"; then
    echo "Signing: $file"
    codesign --force --timestamp --options runtime --sign "$APPLE_SIGNING_IDENTITY" "$file" || {
      echo "Warning: Failed to sign $file"
    }
  fi
done

# Re-sign main executable last
echo ""
echo "Re-signing main executable..."
codesign --force --timestamp --options runtime --sign "$APPLE_SIGNING_IDENTITY" dist-servers/flask-server/flask-server

# Verify signature
echo ""
echo "=== Verifying signature ==="
codesign --verify --verbose dist-servers/flask-server/flask-server

signed_count=$(find dist-servers -type f -exec sh -c 'file "$1" | grep -q "Mach-O" && echo "$1"' _ {} \; | wc -l)
echo "Total signed binaries: $signed_count"

# Step 4: Build Tauri app with signing and notarization
echo ""
echo "=== Step 4: Building Tauri app with signing + notarization ==="
npm run tauri build

# Step 5: Notarize and staple the DMG (Tauri only notarizes the .app, not the DMG)
echo ""
echo "=== Step 5: Notarizing the DMG ==="
DMG_FILE=$(find src-tauri/target/release/bundle/dmg -name "*.dmg" | head -1)

if [ -n "$DMG_FILE" ]; then
  echo "Found DMG: $DMG_FILE"
  echo "Submitting for notarization (this may take a few minutes)..."
  
  xcrun notarytool submit "$DMG_FILE" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait
  
  echo ""
  echo "Stapling notarization ticket to DMG..."
  xcrun stapler staple "$DMG_FILE"
  
  echo ""
  echo "Verifying notarization..."
  spctl --assess --verbose=4 --type open --context context:primary-signature "$DMG_FILE"
else
  echo "Warning: No DMG file found in src-tauri/target/release/bundle/dmg/"
fi

echo ""
echo "=== Build complete ==="
echo "Output: src-tauri/target/release/bundle/"
