from hiveprep.dups import sha256_file, group_duplicates

def test_identical_files_group(tmp_path):
    a = tmp_path/"a.pdf"; b = tmp_path/"sub"/"b.pdf"; b.parent.mkdir()
    a.write_bytes(b"SAME BYTES"); b.write_bytes(b"SAME BYTES")
    c = tmp_path/"c.pdf"; c.write_bytes(b"different")
    groups = group_duplicates([a, b, c])
    assert len(groups) == 1
    (sha, paths), = groups.items()
    assert sorted(paths) == sorted([str(a), str(b)])
    assert sha == sha256_file(a)

def test_no_dupes_empty(tmp_path):
    a = tmp_path/"a"; a.write_bytes(b"x"); b = tmp_path/"b"; b.write_bytes(b"y")
    assert group_duplicates([a, b]) == {}
