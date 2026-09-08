import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from uuid import uuid4

from amulet_nbt import NamedTag


def digest(path):
    if not path.exists():
        return None
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


class StagedWorld:
    def __init__(self, world, temporary):
        self.world = world
        self.temporary = temporary
        self.originals = {}
        self.changed = set()

    def _copy(self, path):
        relative = path.relative_to(self.world)
        if relative in self.originals:
            return
        before = self.temporary / "before" / relative
        staged = self.temporary / "after" / relative
        before.parent.mkdir(parents=True, exist_ok=True)
        staged.parent.mkdir(parents=True, exist_ok=True)
        stamp = digest(path)
        if stamp is not None:
            shutil.copy2(path, before)
            if digest(before) != stamp or digest(path) != stamp:
                raise ValueError(f"World changed while preparing {relative}; retry Save")
            shutil.copy2(before, staged)
        self.originals[relative] = stamp

    def file(self, path):
        self._copy(path)
        return self.temporary / "after" / path.relative_to(self.world)

    def write_file(self, path, root):
        from .nbt_io import load_root, write_root

        staged = self.file(path)
        write_root(root, staged)
        if load_root(staged) != root:
            raise OSError(f"Staged NBT verification failed: {path.name}")
        self.changed.add(path.relative_to(self.world))

    def region(self, directory, cx, cz):
        self._copy(directory / f"r.{cx // 32}.{cz // 32}.mca")
        self._copy(directory / f"c.{cx}.{cz}.mcc")
        return self.temporary / "after" / directory.relative_to(self.world)

    def write(self, directory, cx, cz, root):
        from amulet.level.formats.anvil_world.region import AnvilRegionInterface

        path = directory / f"r.{cx // 32}.{cz // 32}.mca"
        interface = AnvilRegionInterface(str(path), mcc=True)
        interface.write_data(cx % 32, cz % 32, NamedTag(root))
        if interface.get_data(cx % 32, cz % 32).compound != root:
            raise OSError(f"Staged chunk verification failed at {cx}, {cz}")
        interface.unload()
        relative = path.relative_to(self.temporary / "after")
        self.changed.add(relative)
        external = relative.parent / f"c.{cx}.{cz}.mcc"
        if (self.temporary / "after" / external).exists() or self.originals[external] is not None:
            self.changed.add(external)

    def _check(self):
        for relative, stamp in self.originals.items():
            if digest(self.world / relative) != stamp:
                raise ValueError(f"World changed while saving {relative}; retry Save")

    def install(self):
        if not self.changed:
            return None
        self._check()
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]
        backup = self.world / ".structura" / "backups" / name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.temporary / "before"), backup)
        manifest = {"files": {str(path): self.originals[path] for path in sorted(self.changed)}, "installed": []}
        record = backup / "manifest.json"
        record.write_text(json.dumps(manifest, indent=2))
        try:
            self._check()
            ordered = sorted(self.changed, key=lambda path: (
                2 if not (self.temporary / "after" / path).exists() else 1 if path.suffix == ".mca" else 0, str(path)))
            for relative in ordered:
                source = self.temporary / "after" / relative
                target = self.world / relative
                if digest(target) != self.originals[relative]:
                    raise ValueError(f"World changed while saving {relative}")
                if source.exists():
                    with source.open("rb") as stream:
                        os.fsync(stream.fileno())
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, target)
                else:
                    target.unlink(missing_ok=True)
                manifest["installed"].append(str(relative))
                record.write_text(json.dumps(manifest, indent=2))
        except Exception as error:
            raise OSError(f"World save interrupted; pending edits retained. Backup: {backup}. {error}") from error
        return backup
