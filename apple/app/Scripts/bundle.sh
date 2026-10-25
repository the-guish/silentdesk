#!/usr/bin/env bash
# Builds SilentDesk.app: a universal release build of the SilentDesk
# product, wrapped in an app bundle with Bundle/Info.plist and signed ad hoc.
#
#   Scripts/bundle.sh [OUTPUT]     # default: .build/SilentDesk.app
#
# VERSION and BUILD_NUMBER set the bundle's version, 0.1.0 and 1 by default.
set -euo pipefail

cd "$(dirname "$0")/.."
version="${VERSION:-0.1.0}"
build="${BUILD_NUMBER:-1}"
app="${1:-.build/SilentDesk.app}"
archs=(--arch arm64 --arch x86_64)

swift build -c release --product SilentDesk "${archs[@]}"
bin="$(swift build -c release --product SilentDesk "${archs[@]}" --show-bin-path)"

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Frameworks"
cp "$bin/SilentDesk" "$app/Contents/MacOS/SilentDesk"
sed -e "s/@VERSION@/$version/" -e "s/@BUILD@/$build/" Bundle/Info.plist > "$app/Contents/Info.plist"

# Dynamic frameworks the build linked, such as SQLCipher's, go in
# Contents/Frameworks, where the executable then looks for them.
for framework in "$bin"/*.framework; do
    [ -e "$framework" ] || continue
    ditto "$framework" "$app/Contents/Frameworks/$(basename "$framework")"
    codesign --force --sign - --timestamp=none "$app/Contents/Frameworks/$(basename "$framework")"
done
if ! otool -l "$app/Contents/MacOS/SilentDesk" | grep -q '@executable_path/../Frameworks'; then
    install_name_tool -add_rpath @executable_path/../Frameworks "$app/Contents/MacOS/SilentDesk"
fi
rmdir "$app/Contents/Frameworks" 2>/dev/null || true

codesign --force --sign - --timestamp=none "$app"
codesign --verify --strict --verbose=2 "$app"
lipo -info "$app/Contents/MacOS/SilentDesk"
echo "$app"
