from input_algorithms.dictobj import dictobj

class Image(dictobj):
	fields = ["commands", "links", "context", "lxc_conf", "volumes", "env", "ports", "other_options", "network", "privileged"]

class Command(dictobj):
	fields = ["command"]

class Link(dictobj):
	fields = ["link"]

class Context(dictobj):
	fields = ["include", "exclude", "enabled", "parent_dir", "use_gitignore", "use_git_timestamps"]

class Volumes(dictobj):
	fields = ["mount", "share_with"]

class Mount(dictobj):
	fields = ["mount"]

class Environment(dictobj):
	fields = ["environment"]

class Port(dictobj):
	fields = ["port"]

class Network(dictobj):
	fields = ["dns", "mode", "hostname", "disabled", "dns_search", "publish_all_ports"]
