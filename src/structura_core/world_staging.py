import os as os
import shutil

from amulet_nbt import NamedTag

from .world_backup import digest as digest, install_staged
from .world_backup import list_backups as list_backups, restore_backup as restore_backup, verify_backup as verify_backup


class StagedWorld:
    def __init__(self, world, temporary):
        self.world = world
        self.temporary = temporary
        self.originals = {}
        self.changed = set()
        self.regions = {}

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
        if path not in self.regions:
            self.regions[path] = AnvilRegionInterface(str(path), mcc=True)
        interface = self.regions[path]
        interface.write_data(cx % 32, cz % 32, NamedTag(root))
        if interface.get_data(cx % 32, cz % 32).compound != root:
            raise OSError(f"Staged chunk verification failed at {cx}, {cz}")
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
        for interface in self.regions.values():
            interface.unload()
        self.regions.clear()
        self._check()
        return install_staged(self.world, self.temporary, self.originals, self.changed)
