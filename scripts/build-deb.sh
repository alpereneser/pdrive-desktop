#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$project_root/dist"
project_version=$(python3 -c 'import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["project"]["version"])' "$project_root/pyproject.toml")
SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:-1787356800}
export SOURCE_DATE_EPOCH
stage_dir=$(mktemp -d -t pdrive-deb.XXXXXX)
trap 'rm -rf -- "$stage_dir"' EXIT HUP INT TERM
chmod 0755 "$stage_dir"

install -d -m 0755 "$stage_dir/DEBIAN"
install -m 0644 "$project_root/packaging/debian/control" "$stage_dir/DEBIAN/control"
sed -i "s/^Version: .*/Version: $project_version/" "$stage_dir/DEBIAN/control"
install -d -m 0755 "$stage_dir/usr/share/doc/pdrive-desktop"
install -m 0644 "$project_root/packaging/debian/copyright" \
  "$stage_dir/usr/share/doc/pdrive-desktop/copyright"

python_dir="$stage_dir/usr/lib/python3/dist-packages/pdrive_desktop"
install -d -m 0755 "$python_dir"
cp -R "$project_root/src/pdrive_desktop/." "$python_dir/"
find "$python_dir" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$python_dir" -type d -exec chmod 0755 {} +
find "$python_dir" -type f -exec chmod 0644 {} +

dist_info="$stage_dir/usr/lib/python3/dist-packages/pdrive_desktop-${project_version}.dist-info"
install -d -m 0755 "$dist_info"
cat > "$dist_info/METADATA" <<EOF
Metadata-Version: 2.1
Name: pdrive-desktop
Version: $project_version
Summary: Security-first Proton Drive desktop client for Linux
EOF
install -m 0644 /dev/null "$dist_info/INSTALLER"
printf '%s\n' 'pdrive-deb' > "$dist_info/INSTALLER"

install -d -m 0755 "$stage_dir/usr/bin"
install -m 0755 "$project_root/packaging/pdrive-desktop" "$stage_dir/usr/bin/pdrive-desktop"

install -d -m 0755 "$stage_dir/usr/share/applications"
install -m 0644 "$project_root/packaging/io.github.pdrive.Desktop.desktop" \
  "$stage_dir/usr/share/applications/io.github.pdrive.Desktop.desktop"
install -d -m 0755 "$stage_dir/usr/share/metainfo"
install -m 0644 "$project_root/packaging/io.github.pdrive.Desktop.metainfo.xml" \
  "$stage_dir/usr/share/metainfo/io.github.pdrive.Desktop.metainfo.xml"
install -d -m 0755 "$stage_dir/usr/share/icons/hicolor/scalable/apps"
install -m 0644 "$project_root/packaging/io.github.pdrive.Desktop.svg" \
  "$stage_dir/usr/share/icons/hicolor/scalable/apps/io.github.pdrive.Desktop.svg"
install -m 0644 "$project_root/packaging/io.github.pdrive.Desktop.svg" \
  "$stage_dir/usr/share/icons/hicolor/scalable/apps/pdrive-desktop.svg"
install -d -m 0755 "$stage_dir/usr/share/pixmaps"
install -m 0644 "$project_root/packaging/io.github.pdrive.Desktop.svg" \
  "$stage_dir/usr/share/pixmaps/pdrive-desktop.svg"

install -d -m 0755 "$output_dir"
find "$stage_dir" -exec touch -d "@$SOURCE_DATE_EPOCH" {} +
dpkg-deb --root-owner-group --build \
  "$stage_dir" "$output_dir/pdrive-desktop_${project_version}_amd64.deb"
