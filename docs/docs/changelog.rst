Changelog
=========

0.13.0 - TBD
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
    No Changelog was maintained
