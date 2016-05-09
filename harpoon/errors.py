from input_algorithms.errors import BadSpec, BadSpecValue
from delfick_error import DelfickError, ProgrammerError

class HarpoonError(DelfickError): pass

# Explicitly make these errors in this context
BadSpec = BadSpec
BadSpecValue = BadSpecValue
ProgrammerError = ProgrammerError

class BadConfiguration(HarpoonError):
    desc = "Bad configuration"

class BadOptionFormat(HarpoonError):
    desc = "Bad option format"

class BadTask(HarpoonError):
    desc = "Bad task"

class BadOption(HarpoonError):
    desc = "Bad Option"

class NoSuchKey(HarpoonError):
    desc = "Couldn't find key"

class NoSuchImage(HarpoonError):
    desc = "Couldn't find image"

class BadCommand(HarpoonError):
    desc = "Bad command"

class BadImage(HarpoonError):
    desc = "Bad image"

class CouldntKill(HarpoonError):
    desc = "Couldn't kill a process"

class FailedImage(HarpoonError):
    desc = "Something about an image failed"

class BadYaml(HarpoonError):
    desc = "Invalid yaml file"

class BadResult(HarpoonError):
    desc = "A bad result"

class UserQuit(HarpoonError):
    desc = "User quit the program"

class BadDockerConnection(HarpoonError):
    desc = "Failed to connect to docker"

class ImageDepCycle(HarpoonError):
    desc = "Image dependency cycle"

class BadDirectory(BadSpecValue):
    desc = "Expected a path to a directory"

class BadFilename(BadSpecValue):
    desc = "Expected a path to a filename"

class DeprecatedFeature(BadSpecValue):
    desc = "Feature is deprecated"

class BadEnvironment(HarpoonError):
    desc = "Something bad in the environment"

class BadAmazon(HarpoonError):
    desc = "Something wrong with amazon"

class AlreadyBoundPorts(HarpoonError):
    desc = "Ports are already bound by something else"

