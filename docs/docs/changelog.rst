Changelog
=========

0.19.0 - 15 June 2024
   * Updated python docker dependency

0.18.0 - 26 November 2023
   * Updated dev tooling
   * Changed to hatchling
   * Now python 3.8+
   * Changed ``ruamel.yaml`` to ``ruyaml`` fork

0.17.0 - 26 July 2023
   * Updated python docker dependency to latest

0.16.1 - 25 February 2020
   * Added a ``get_docker_context`` CLI action for getting the tar file that
     would be sent to the Docker daemon if we made that image.

0.16.0 - 5 November 2019
   * Converted tests to pytest
   * Implemented a container_manager web server functionality, see
     :ref:`container_manager`.
   * Made harpoon.yml optional
   * Added --docker-output argument for specifying a file to print docker output
     to
   * Upgraded delfick_project, which also means harpoon is no longer supported
     on python3.4 or python3.5.

0.15.1 - 2 October 2019
   * No-op update of delfick_project

0.15.0 - 18 September 2019
   * Migrated to `delfick_project <https://delfick-project.readthedocs.io/en/latest/index.html>`_
   * Harpoon is now python3.4+ only

0.14.4 - 15 September 2019
   * Made boto an optional dependency. Features that require boto will still
     work, you just need to make sure boto3 is installed in your environment.

0.14.3 - 4 September 2019
   * Reformatted the code with black
   * Fixed some lint warnings

0.14.2 - 4 August 2019
   * Update delfick_app dependency

0.14.1 - 27 May 2019
   * Fix printing out logs when a container fails during a wait condition

0.14.0 - 23 January 2019
   * Started using ruamel.yaml instead of PyYaml to load configuration

0.13.0 - 5 January 2019
   * Removing all traces of file modified time options. Since docker 1.8 the
     mtime of files is not taken into account when determining if the docker
     layer cache has been invalidated. Since that has been out since August
     2015 I feel it's been out long enough that people don't use such an old
     version anymore.
   * Removing persistence and squash features, I marked them as deprecated in
     version 0.10.0

0.12.1 - 7 November 2018
   * Fixed a bug when running git commands that meant lines were being split
     where there wasn't a newline and causing exceptions to be raised

0.12.0 - 29 October 2018
   * Harpoon will now cleanup intermediate images from multi stage builds by
     default. If you want to keep intermediate images then specify the
     ``cleanup_intermediate_images`` as ``False`` for your image.

0.11.2 - 23 September 2018
   * Fixed bug where commands specified as strings aren't put into the
     Dockerfile correctly

0.11.1 - 23 September 2018
   * retrieve now doesn't build the image you specify if you have set NO_BUILD=1
     in your environment. It also pays attention to the --tag you provide

0.11.0 - 23 September 2018
   * Make staged builds in docker files a first class citizen to make it easier
     to reference images in your configuration
   * The pull_all_external command will now also pull external parents from images
     that don't define an image_index option

0.10.0 - 18 September 2018
   * ``harpoon make`` will now pay attention to --artifact or --tag to determine
     what tag to build the image with
   * Images now have a ``cache_from`` options. This can either be a boolean where
     True means use this image name as --cache-from. Or it can be a single string
     or list of strings that represent the images to use with --cache-from. Thse
     strings are formatted so you can refer to other images by saying
     ``{images.other_image_name}`` or if the image isn't defined in this harpoon.yml
     then say ``gcr.io/company/image_name``.
   * Updated default [git] install group to use gitmit==0.5.0
   * Deprecated persistence and squash functionality. They will be removed from
     a future version of harpoon. Note that the cache_from and tagging
     functionality hasn't been tested well with these features
   * Added an ``untag`` action for cleaning up tags

Pre 0.10.0
   * No Changelog was maintained
