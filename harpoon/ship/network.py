from docker.errors import APIError as DockerAPIError
import logging
import uuid

log = logging.getLogger("harpoon.ship.network")

class NetworkManager(object):
    def __init__(self, docker_api):
        self.networks = {}
        self.docker_api = docker_api

    def register(self, conf, container_name):
        if not conf.links:
            return

        network = self.docker_api.create_network(str(uuid.uuid1()))["Id"]
        inside = self.networks[network] = set()
        log.info("Created network %s\tlinks=%s", network, [l.pair for l in conf.links])
        for link in conf.links:
            dep_container_name, link_name = link.pair
            inside.add(dep_container_name)
            conf.harpoon.docker_api.connect_container_to_network(dep_container_name, network
                , aliases = [link_name]
                )

        conf.harpoon.docker_api.connect_container_to_network(container_name, network)
        inside.add(container_name)

    def removed(self, container_name):
        for network, containers in list(self.networks.items()):
            if network not in self.networks:
                continue

            if container_name in containers:
                containers.remove(container_name)

            if not containers:
                try:
                    log.info("Removing network %s", network)
                    self.docker_api.remove_network(network)
                except DockerAPIError as error:
                    log.warning("Failed to remove network %s\terror=%s", network, error)
                finally:
                    del self.networks[network]
