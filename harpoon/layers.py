from harpoon.errors import ImageDepCycle

class Layers(object):
    """
    Used to order the creation of many images.

    Usage::

        layers = Layers({"image1": image1, "image2": "image2, "image3": image3, "image4": image4})
        layers.add_to_layers("image3")
        for layer in layers.layered:
            # might get something like
            # [("image3", image4), ("image2", image2)]
            # [("image3", image3)]

    When we create the layers, it will do a depth first addition of all dependencies
    and only add a image to a layer that occurs after all it's dependencies.

    Cyclic dependencies will be complained about.
    """
    def __init__(self, images, all_images=None):
        self.images = images
        self.all_images = all_images
        if self.all_images is None:
            self.all_images = images

        self.accounted = {}
        self._layered = []

    def reset(self):
        """Make a clean slate (initialize layered and accounted on the instance)"""
        self.accounted = {}
        self._layered = []

    @property
    def layered(self):
        """Yield list of [[(name, image), ...], [(name, image), ...], ...]"""
        result = []
        for layer in self._layered:
            nxt = []
            for name in layer:
                nxt.append((name, self.all_images[name]))
            result.append(nxt)
        return result

    def add_all_to_layers(self):
        """Add all the images to layered"""
        for image in sorted(self.images):
            self.add_to_layers(image)

    def add_to_layers(self, name, chain=None):
        layered = self._layered

        if name not in self.accounted:
            self.accounted[name] = True
        else:
            return

        if chain is None:
            chain = []
        chain = chain + [name]

        for dependency in sorted(self.all_images[name].dependencies(self.all_images)):
            dep_chain = list(chain)
            if dependency in chain:
                dep_chain.append(dependency)
                raise ImageDepCycle(chain=dep_chain)
            self.add_to_layers(dependency, dep_chain)

        layer = 0
        for dependency in self.all_images[name].dependencies(self.all_images):
            for index, deps in enumerate(layered):
                if dependency in deps:
                    if layer <= index:
                        layer = index + 1
                    continue

        if len(layered) == layer:
            layered.append([])
        layered[layer].append(name)

