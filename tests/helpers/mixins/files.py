from __future__ import print_function

from contextlib import contextmanager

import tempfile
import tarfile
import shutil
import uuid
import sys
import six
import os

class FilesAssertionsMixin:

    def unique_val(self):
        """Return a uuid1 value"""
        return str(uuid.uuid1())

    def make_temp_file(self, content=None):
        """
        Make a temp file.
        Record it so it can be cleaned up later
        """
        if not hasattr(self, "_temp_files"):
            self._temp_files = []

        tmp = tempfile.NamedTemporaryFile(delete=False)
        if content:
            with open(tmp.name, 'w') as fle:
                fle.write(content)
        self._temp_files.append(tmp.name)
        return tmp

    def make_temp_dir(self):
        """
        Make a temp directory.
        Record it so it can be cleaned up later
        """
        if not hasattr(self, "_temp_dirs"):
            self._temp_dirs = []

        tmp = tempfile.mkdtemp()
        self._temp_dirs.append(tmp)
        return tmp

    def cleanup_temp_things(self):
        """
        Clean up any temporary things that were made during this test
        """
        for key in ("_temp_dirs", "_temp_files"):
            for tmp in getattr(self, key, []):
                if os.path.isdir(tmp):
                    shutil.rmtree(tmp)
                else:
                    os.remove(tmp)
    cleanup_temp_things._harpoon_case_teardown = True

    @contextmanager
    def a_temp_file(self, body=None, removed=False):
        """
        Yield a temporary file and ensure it's deleted
        """
        filename = None
        try:
            filename = tempfile.NamedTemporaryFile(delete=False).name
            if body:
                with open(filename, 'w') as fle:
                    fle.write(body)
            if removed:
                os.remove(filename)
            yield filename
        finally:
            if filename and os.path.exists(filename):
                os.remove(filename)

    @contextmanager
    def a_temp_dir(self, removed=False):
        """
        Yield a temporary directory and ensure it is deleted
        """
        directory = None
        try:
            directory = tempfile.mkdtemp()
            if removed:
                shutil.rmtree(directory)
            yield directory
        finally:
            if directory and os.path.exists(directory):
                shutil.rmtree(directory)

    def touch_files(self, root, files_list, record=None):
        """
        Given a list of of [<file_spec>, ...] create the specified files under specified root.

        Where <file_spec> may be

            a string
                If it ends with a slash, it creates an empty directory at this location,
                otherwise it touches a file at this place

                In either case, it creates all directories leading up to it

            (a string, a string)
                It creates a file at the location of the first string and writes the
                second string to this location.
        """

        def create(location, contents=None):
            """Create this location with specified contents"""
            dirname, filename = os.path.split(location)
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            nxt = record
            if nxt is not None and dirname != nxt['/folder/']:
                for part in os.path.relpath(dirname, nxt['/folder/']).split(os.path.sep):
                    if part in nxt:
                        nxt = nxt[part]
                    else:
                        nxt = nxt[part] = {"/folder/": os.path.join(nxt['/folder/'], part)}

            if filename:
                with open(location, 'w') as fle:
                    if contents:
                        fle.write(contents)
                    else:
                        fle.write("")

                    if nxt:
                        nxt[filename] = {'/file/': os.path.join(nxt['/folder/'], filename)}

        for file_spec in files_list:
            if isinstance(file_spec, six.string_types):
                create(os.path.join(root, file_spec), None)

            else:
                file_location, file_contents = file_spec
                create(os.path.join(root, file_location), file_contents)

    @contextmanager
    def fake_std_streams(self):
        with self.a_temp_file() as fake_stdout:
            fake_stdout = open(fake_stdout, "w")
            with self.a_temp_file() as fake_stderr:
                fake_stderr = open(fake_stderr, "w")
                sys.stdout, old_stdout = fake_stdout, sys.stdout
                sys.stderr, old_stderr = fake_stderr, sys.stderr
                try:
                    yield fake_stdout, fake_stderr
                except SystemExit:
                    print(open(fake_stdout.name).read(), file=old_stdout)
                    print(open(fake_stderr.name).read(), file=old_stderr)
                    sys.stdout, sys.stderr = old_stdout, old_stderr
                    raise
                finally:
                    sys.stdout, sys.stderr = old_stdout, old_stderr

    def setup_directory(self, heirarchy, root=None, record=None):
        """
            Setup hierarchy of folders in a temp directory
            So if heirarchy is
            { 'one' : {'two':{"six": ''}, 'three':'', 'four':'contents'}
            , 'five' : {'etc':''}
            }
            Then under a temp directory you'll get
            one/two, one/three, one/four, five/etc

            And this function would return a tuple of (root, record)
            where root is the base directory
            And record would be like:
            {'one':{'/folder/':'/path/to/one', 'two':{'/folder/':'/path/to/one/two', 'six': '/path/to/one/six'}, 'four':{'/file/':'/path/to/one/four'}, ... etc
        """
        if root is None:
            root = self.make_temp_dir()

        if record is None:
            record = {'/folder/': root}

        if type(heirarchy) in (list, tuple):
            heirarchy = dict((k, None) for k in heirarchy)

        for key, val in heirarchy.items():
            path = os.path.join(root, key)
            if isinstance(val, (six.string_types + (list, tuple))) and not key.endswith('/'):
                if isinstance(val, six.string_types):
                    val = [(key, val)]
                elif isinstance(val, tuple):
                    val = [val]
                self.touch_files(root, val, record=record)
            else:
                record[key] = {'/folder/' : path}
                os.makedirs(path)
                if val:
                    self.setup_directory(val, path, record[key])

        if '/folder/' not in record:
            record['/folder/'] = root

        return root, record

    ########################
    ###   TAR FILES
    ########################

    def assertTarFileContent(self, location, expected):
        """Make sure content of a tarfile matches what we expect"""
        found = set()
        for identity, data, tarinfo in self.extract_tar(location):
            if six.PY2 and sys.version_info[1] == 6:
                identity = "./{0}".format(identity)
            found.add(identity)
            contents = expected[identity]
            if data is not None or contents is not None:
                self.assertEqual(data.decode('utf-8'), contents)
        self.assertEqual(found, set(expected.keys()))

    def extract_tar(self, location):
        """Yield (identity, data, tarinfo) for everything in archive at provided location"""
        assert os.path.exists(location)
        trf = None
        try:
            trf = tarfile.open(location)
            for tarinfo in trf:
                data = None
                if tarinfo.isfile():
                    data = trf.extractfile(tarinfo.name).read()

                yield tarinfo.name, data, tarinfo
        finally:
            if trf:
                trf.close()

