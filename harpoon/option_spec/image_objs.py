from namedlist import namedlist

class Image(namedlist("Image", ["commands", "links", "context", "lxc_conf", "volumes", "env", "ports", "other_options", "network", "privileged"])): pass
class Command(namedlist("Command", ["command"])): pass
class Link(namedlist("Link", ["link"])): pass
class Context(namedlist("Context", ["include", "exclude", "enabled", "parent_dir", "use_gitignore", "use_git_timestamps"])): pass
class Volumes(namedlist("Volumes", ["mount", "share_with"])): pass
class Mount(namedlist("Mount", ["mount"])): pass
class Environment(namedlist("Environment", ["environment"])): pass
class Port(namedlist("Port", ["port"])): pass
class Network(namedlist("Network", ["dns", "mode", "hostname", "disabled", "dns_search", "publish_all_ports"])): pass

