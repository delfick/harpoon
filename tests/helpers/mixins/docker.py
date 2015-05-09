from harpoon.executor import docker_context

info = {}

class DockerAssertionsMixin:
	@property
	def docker_client(self):
		if "docker_client" not in info:
			info["docker_client"] = docker_context()
		return info["docker_client"]

	def refresh_context(self):
		if "docker_client" in info:
			del info["docker_client"]

