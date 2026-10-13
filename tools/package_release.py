import hashlib
import sys
import zipfile
from importlib.metadata import distribution
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist"
EXECUTABLE = OUTPUT / "MSFS-SimRate-Monitor.exe"
ARCHIVE = OUTPUT / "MSFS-SimRate-Monitor-windows-x64.zip"


def main():
    if not EXECUTABLE.is_file():
        raise SystemExit("Run build.bat before packaging.")

    with zipfile.ZipFile(ARCHIVE, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in (EXECUTABLE, ROOT / "README.md", ROOT / "LICENSE"):
            archive.write(file, file.name)
        for file in (ROOT / "docs" / "images").glob("*.png"):
            archive.write(file, file.relative_to(ROOT).as_posix())
        for name in ("loguru", "pystray", "Pillow", "six", "colorama", "win32-setctime", "pyinstaller"):
            package = distribution(name)
            for file in package.files or []:
                if file.name.lower().startswith(("license", "copying")):
                    archive.write(package.locate_file(file), f"licenses/{name}/{file.name}")

        # Include the unmodified LGPL dependency source with the executable.
        package = distribution("pystray")
        for file in package.files or []:
            if file.parts[0] == "pystray" and file.suffix == ".py":
                archive.write(package.locate_file(file), f"third-party/{file.as_posix()}")
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        if python_license.is_file():
            archive.write(python_license, "licenses/Python/LICENSE.txt")

    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Release archive is corrupt.")
    checksums = []
    for file in (EXECUTABLE, ARCHIVE):
        with file.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        checksums.append(f"{checksum}  {file.name}\n")
    (OUTPUT / "SHA256SUMS.txt").write_text("".join(checksums), encoding="ascii")
    print(ARCHIVE.name)


if __name__ == "__main__":
    main()
