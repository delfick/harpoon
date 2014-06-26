from contextlib import contextmanager
import tempfile
import shutil
import os

class FilesAssertionsMixin:

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

    def touch_files(self, root, files_list):
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

            if filename:
                with open(location, 'w') as fle:
                    if contents:
                        fle.write(contents)
                    else:
                        fle.write("")

        for file_spec in files_list:
            if isinstance(file_spec, basestring):
                create(os.path.join(root, file_spec), None)

            else:
                file_location, file_contents = file_spec
                create(os.path.join(root, file_location), file_contents)

