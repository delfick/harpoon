Changelog
=========

0.10.0 - TBD
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

Pre 0.10.0
    No Changelog was maintained
