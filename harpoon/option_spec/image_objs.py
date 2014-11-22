from input_algorithms.dictobj import dictobj

class Image(dictobj):
    fields = [
          "commands", "links", "context"
        , "lxc_conf", "volumes", "env", "ports"
        , "other_options", "network", "privileged"
        , "image_name", "dependency_options"
        , "container_name", "name", "key_name"
        ]

    def dependencies(self, images):
        """Yield just the dependency images"""
        for image, _ in self.dependency_images(images):
            yield image

    @property
    def parent_image(self):
        return self.commands[0].value

    def dependency_images(self, images, ignore_parent=False):
        """
        What images does this one require

        Taking into account parent image, and those in link and volumes.share_with options
        """
        candidates = []
        detach = dict((candidate, not options.attached) for candidate, options in self.dependency_options.items())

        if not ignore_parent:
            for image, instance in images.items():
                if self.parent_image == instance.image_name:
                    candidates.append(image.key_name)
                    break

        for link in self.links:
            if link.container_name in managed_containers:
                candidates.append(managed_containers[link.container])

        for container in self.volumes.share_with:
            if container_name in managed_containers:
                candidates.append(managed_containers[container_name])

        done = set()
        for candidate in candidates:
            if candidate not in done:
                done.add(candidate)
                yield candidate, detach.get(candidate, True)

class Command(dictobj):
    fields = ["action", "value"]

class Link(dictobj):
    fields = ["container_name", "link_name"]

class Context(dictobj):
    fields = ["include", "exclude", "enabled", "parent_dir", "use_gitignore", "use_git_timestamps"]

class Volumes(dictobj):
    fields = ["mount", "share_with"]

class Mount(dictobj):
    fields = ["mount"]

class Environment(dictobj):
    fields = ["env_name", "default_val"]

class Port(dictobj):
    fields = ["port"]

class Network(dictobj):
    fields = ["dns", "mode", "hostname", "disabled", "dns_search", "publish_all_ports"]

class DependencyOptions(dictobj):
    fields = [("attached", False)]

