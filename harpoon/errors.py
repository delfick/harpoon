class HarpoonError(Exception):
    """Helpful class for creating custom exceptions"""
    desc = ""

    def __init__(self, message="", **kwargs):
        self.kwargs = kwargs
        self.errors = kwargs.get("_errors", [])
        if "_errors" in kwargs:
            del kwargs["_errors"]
        self.message = message
        super(HarpoonError, self).__init__(message)

    def __str__(self):
        message = self.oneline()
        if self.errors:
            message = "{0}\nerrors:\n\t{1}".format(message, "\n\t".join(str(error) for error in self.errors))
        return message

    def oneline(self):
        """Get back the error as a oneliner"""
        desc = self.desc
        message = self.message

        info = ["{0}={1}".format(k, v) for k, v in sorted(self.kwargs.items())]
        info = '\t'.join(info)
        if info and (message or desc):
            info = "\t{0}".format(info)

        if desc:
            if message:
                message = ". {0}".format(message)
            return '"{0}{1}"{2}'.format(desc, message, info)
        else:
            if message:
                return '"{0}"{1}'.format(message, info)
            else:
                return "{0}".format(info)

    def __eq__(self, error):
        """Say whether this error is like the other error"""
        return error.__class__ == self.__class__ and error.message == self.message and error.kwargs == error.kwargs

class ProgrammerError(Exception):
    """For when the programmer should have prevented something happening"""

class BadConfiguration(HarpoonError):
    desc = "Bad configuration"

class BadOptionFormat(HarpoonError):
    desc = "Bad option format"

class BadTask(HarpoonError):
    desc = "Bad task"

class NoSuchTask(HarpoonError):
    desc = "This task doesn't exist"

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

