"""Unpacking an archive with the real bsdtar (a tar reads exactly like HLTV's RAR5)."""

import io
import tarfile

from app.services import archive


def test_demos_kept_in_a_folder_land_in_the_destination(tmp_path):
    path = tmp_path / "2397117-chinggis-warriors-vs-nexvoid.rar"
    with tarfile.open(path, "w") as bundle:
        folder = tarfile.TarInfo("Demos")
        folder.type = tarfile.DIRTYPE
        bundle.addfile(folder)
        for name in ("m1-nuke", "m2-anubis"):
            data = b"not really a demo"
            member = tarfile.TarInfo(f"Demos/chinggis-warriors-vs-nexvoid-{name}.dem")
            member.size = len(data)
            bundle.addfile(member, io.BytesIO(data))

    entries = archive.list_demos(path)
    assert [(e.map, e.map_number) for e in entries] == [("nuke", 1), ("anubis", 2)]

    dest = tmp_path / "out"
    written = archive.extract(path, dest, entries)
    assert written == [
        dest / "chinggis-warriors-vs-nexvoid-m1-nuke.dem",
        dest / "chinggis-warriors-vs-nexvoid-m2-anubis.dem",
    ]
    assert all(p.read_bytes() == b"not really a demo" for p in written)
    assert not (dest / "Demos").exists()
