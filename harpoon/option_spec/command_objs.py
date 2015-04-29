from input_algorithms.spec_base import NotSpecified
from input_algorithms.dictobj import dictobj
import six

class Command(dictobj):
    """Holds a single command"""
    fields = ['instruction', ('extra_context', lambda: NotSpecified)]

    def __repr__(self):
        return "<Command({0})>".format(self.instruction)

    @property
    def action(self):
        return self._action

    @property
    def instruction(self):
        return self._instruction

    @instruction.setter
    def instruction(self, val):
        """Set the action and command from an instruction"""
        self._instruction = val
        if isinstance(val, tuple):
            self._action, self.command = val
        else:
            self._action, self.command = val.split(" ", 1)

    @property
    def as_string(self):
        """Return the command as a single string for the docker file"""
        if self.action == "FROM" and not isinstance(self.command, six.string_types):
            return "{0} {1}".format(self.action, self.command.from_name)
        else:
            return "{0} {1}".format(self.action, self.command)

class Commands(dictobj):
    """This holds the list of commands that make up the docker file for this image"""
    fields = ['orig_commands']

    @property
    def commands(self):
        """Memoize and return the flattened list of commands"""
        if not getattr(self, "_commands", None):
            self._commands = []
            for command in self.orig_commands:
                if isinstance(command, Command):
                    command = [command]
                for instruction in command:
                    self._commands.append(instruction)
        return self._commands

    @property
    def parent_image(self):
        """Determine the parent_image from the FROM command"""
        for command in self.commands:
            if command.action == "FROM":
                return command.command

    @property
    def parent_image_name(self):
        """Return the image name of the parent"""
        parent = self.parent_image
        if isinstance(parent, six.string_types):
            return parent
        else:
            return parent.image_name

    @property
    def docker_lines(self):
        """Return the commands as a newline seperated list of strings"""
        return '\n'.join(self.docker_lines_list)

    @property
    def docker_lines_list(self):
        """Return the commands as a list of strings"""
        return [command.as_string for command in self.commands]

    @property
    def extra_context(self):
        for command in self.commands:
            if command.extra_context is not NotSpecified:
                yield command.extra_context

