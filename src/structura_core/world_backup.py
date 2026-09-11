import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from uuid import uuid4


COMPLETE_PHASES = {"complete", "rolled_back", "preparing"}
MAX_MANIFEST_BYTES = 32 * 1024 * 1024


def digest(path):
    path = Path(path)
    if not path.exists():
        return None
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def sync_directory(path):
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def create_directory(path):
    path = Path(path)
    missing, ancestor = [], path
    while not ancestor.exists():
        missing.append(ancestor)
        ancestor = ancestor.parent
    path.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        sync_directory(created.parent)


def checked_path(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("Invalid path in backup manifest")
    path = Path(relative)
    if not isinstance(relative, str) or not relative or path.is_absolute() or any(p in (".", "..") for p in relative.split("/")):
        raise ValueError("Invalid path in backup manifest")
    if "\\" in relative or ":" in relative or path.parts[0] == ".structura":
        raise ValueError("Invalid path in backup manifest")
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Backup path escapes its directory")
    return target


def read_manifest(backup):
    record = Path(backup) / "manifest.json"
    if record.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("Backup manifest exceeds the size limit")
    manifest = json.loads(record.read_text())
    if not isinstance(manifest, dict) or manifest.get("schema_version", 1) not in (1, 2):
        raise ValueError("Unsupported backup manifest")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files or len(files) > 100_000:
        raise ValueError("Backup manifest must list 1 to 100,000 files")
    for relative, stamp in files.items():
        checked_path(Path(backup), relative)
        if stamp is not None and (not isinstance(stamp, str) or len(stamp) != 64 or any(c not in "0123456789abcdef" for c in stamp)):
            raise ValueError("Invalid hash in backup manifest")
    if manifest.get("schema_version") == 2:
        after = manifest.get("after")
        if not isinstance(after, dict) or after.keys() != files.keys():
            raise ValueError("Backup manifest is missing destination hashes")
        for stamp in after.values():
            if stamp is not None and (not isinstance(stamp, str) or len(stamp) != 64 or any(c not in "0123456789abcdef" for c in stamp)):
                raise ValueError("Invalid destination hash in backup manifest")
    installed = manifest.get("installed", [])
    if not isinstance(installed, list) or any(path not in files for path in installed):
        raise ValueError("Invalid installed files in backup manifest")
    manifest.setdefault("phase", "complete" if len(installed) == len(files) else "interrupted")
    return manifest


def write_manifest(backup, manifest):
    temporary = None
    try:
        with NamedTemporaryFile(dir=backup, prefix=".manifest-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(manifest, indent=2).encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, backup / "manifest.json")
        sync_directory(backup)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def list_backups(world):
    root = Path(world) / ".structura" / "backups"
    if not root.is_dir():
        return []
    result = []
    for backup in sorted(root.iterdir(), reverse=True):
        if not backup.is_dir():
            continue
        try:
            manifest = read_manifest(backup)
            result.append({"name": backup.name, "path": str(backup), "files": manifest["files"],
                           "installed": len(manifest.get("installed", [])), "phase": manifest["phase"]})
        except (OSError, ValueError, TypeError) as error:
            result.append({"name": backup.name, "path": str(backup), "files": {}, "installed": 0,
                           "phase": "invalid", "error": str(error)})
    return result


def pending_backups(world):
    return [item for item in list_backups(world) if item["phase"] not in COMPLETE_PHASES]


def require_complete_save(world):
    pending = pending_backups(world)
    if pending:
        raise ValueError(f"World has an unfinished save; open Restore backup before saving again: {pending[0]['name']}")


def verify_backup(backup, progress=None):
    root = Path(backup)
    files = read_manifest(root)["files"]
    for index, (relative, stamp) in enumerate(sorted(files.items()), 1):
        if digest(checked_path(root, relative)) != stamp:
            return False
        if progress:
            progress("Verify backup", index, len(files))
    return True


def replace_file(source, target, expected):
    temporary = None
    create_directory(target.parent)
    try:
        if source is not None:
            with NamedTemporaryFile(dir=target.parent, prefix=".structura-", delete=False) as stream:
                temporary = Path(stream.name)
                with source.open("rb") as incoming:
                    shutil.copyfileobj(incoming, stream)
                stream.flush()
                os.fsync(stream.fileno())
        if digest(target) != expected:
            raise ValueError(f"World changed while saving {target.name}")
        if temporary is None:
            target.unlink(missing_ok=True)
        else:
            os.replace(temporary, target)
        sync_directory(target.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install_staged(world, temporary, originals, changed, *, kind="save", progress=None):
    world, temporary = Path(world), Path(temporary)
    if not changed:
        return None
    if kind == "save":
        require_complete_save(world)
    files = {str(path): originals[path] for path in sorted(changed)}
    after = {relative: digest(checked_path(temporary / "after", relative)) for relative in files}
    for relative, stamp in files.items():
        if digest(checked_path(world, relative)) != stamp or digest(checked_path(temporary / "before", relative)) != stamp:
            raise ValueError(f"World changed while saving {relative}")
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ-") + kind + "-" + uuid4().hex[:8]
    backup = world / ".structura" / "backups" / name
    backup.mkdir(parents=True)
    manifest = {"schema_version": 2, "world": str(world.resolve()), "kind": kind,
                "phase": "preparing", "files": files, "after": after, "installed": []}
    try:
        write_manifest(backup, manifest)
        for directory in (backup.parent, backup.parent.parent, world):
            sync_directory(directory)
        for relative, stamp in files.items():
            if stamp is not None:
                target = checked_path(backup, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(checked_path(temporary / "before", relative), target)
                with target.open("rb") as stream:
                    os.fsync(stream.fileno())
                if digest(target) != stamp:
                    raise OSError(f"Backup verification failed: {relative}")
                sync_directory(target.parent)
        for directory in sorted((p for p in backup.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            sync_directory(directory)
        manifest["phase"] = "prepared"
        write_manifest(backup, manifest)
        sync_directory(backup.parent)
        manifest["phase"] = "installing"
        write_manifest(backup, manifest)
        ordered = sorted(files, key=lambda path: (2 if after[path] is None else 1 if Path(path).suffix == ".mca" else 0, path))
        for index, relative in enumerate(ordered, 1):
            source = checked_path(temporary / "after", relative) if after[relative] is not None else None
            if source is not None and digest(source) != after[relative]:
                raise ValueError(f"Prepared file changed: {relative}")
            replace_file(source, checked_path(world, relative), files[relative])
            manifest["installed"].append(relative)
            write_manifest(backup, manifest)
            if progress:
                progress("Restore backup" if kind == "restore" else "Save world", index, len(files))
        manifest["phase"] = "complete"
        write_manifest(backup, manifest)
    except Exception as error:
        if not (backup / "manifest.json").exists():
            shutil.rmtree(backup)
        raise OSError(f"World {kind} interrupted; pending edits retained. Backup: {backup}. {error}") from error
    return backup


def inspect_restore(world, backup, progress=None):
    root, source = Path(world), Path(backup)
    record = read_manifest(source)
    current = {name: digest(checked_path(root, name)) for name in record["files"]}
    conflicts = [name for name, stamp in current.items() if stamp not in (record["files"][name], record.get("after", {}).get(name))]
    return {"verified": verify_backup(source, progress), "current": current, "conflicts": conflicts}


def restore_backup(world, backup, progress=None, *, expected=None):
    from portalocker import Lock

    work = Path(world) / ".structura"
    work.mkdir(exist_ok=True)
    with Lock(str(work / "write.lock"), mode="a+b", timeout=0):
        return _restore_backup(world, backup, progress, expected=expected)


def _restore_backup(world, backup, progress=None, *, expected=None):
    root, source = Path(world), Path(backup)
    manifest = read_manifest(source)
    if not source.resolve().is_relative_to((root / ".structura" / "backups").resolve()):
        raise ValueError("Choose a backup belonging to this world")
    if manifest.get("world", str(root.resolve())) != str(root.resolve()):
        raise ValueError("Backup belongs to a different world")
    if not verify_backup(source, progress):
        raise ValueError("Backup files no longer match their manifest hashes")
    if expected is not None:
        actual = {name: digest(checked_path(root, name)) for name in manifest["files"]}
        if actual != expected:
            raise ValueError("World changed after the restore review; verify the backup again")
    with TemporaryDirectory(prefix="structura-restore-") as directory:
        temporary = Path(directory)
        originals = {}
        for relative, stamp in manifest["files"].items():
            target = checked_path(root, relative)
            key = Path(relative)
            originals[key] = digest(target)
            if originals[key] is not None:
                before = checked_path(temporary / "before", relative)
                before.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, before)
            if stamp is not None:
                after = checked_path(temporary / "after", relative)
                after.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(checked_path(source, relative), after)
                if digest(after) != stamp:
                    raise ValueError(f"Backup changed during restore: {relative}")
        safety = install_staged(root, temporary, originals, set(originals), kind="restore", progress=progress)
    for pending in pending_backups(root):
        if pending["phase"] == "invalid":
            continue
        record = Path(pending["path"])
        old = read_manifest(record)
        actual = {relative: digest(checked_path(root, relative)) for relative in old["files"]}
        if actual == old["files"] or actual == old.get("after"):
            old["phase"] = "rolled_back" if actual == old["files"] else "complete"
            write_manifest(record, old)
    return {"restored": len(manifest["files"]), "safety": str(safety)}
