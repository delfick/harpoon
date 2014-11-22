from input_algorithms.errors import BadSpecValue
from input_algorithms.spec_base import (
      NotSpecified, Spec
    , string_spec, formatted
    )

class many_item_formatted_spec(Spec):
    """
    A spec for something that is many items
    Either a list or a string split by ":"

    If it's a string it will split by ':'
    Otherwise if it's a list, then it will use as is
    and will complain if it has two many values

    It will use determine_<num> on any value that is still NotSpecified after
    splitting the val.

    And will use alter_<num> on all values after they have been formatted.

    Where <num> is 1 indexed index of the value in the spec specifications.

    Finally, create_result is called at the end to create the final result from
    the determined/formatted/altered values.
    """
    specs = []
    value_name = None
    optional_specs = []

    def setup(self, *args, **kwargs):
        if not self.value_name:
            self.value_name = self.__class__.__name__

    def normalise(self, meta, val):
        original_val = val
        second = NotSpecified
        if isinstance(val, (list, tuple)):
            vals = val

        elif isinstance(val, basestring):
            vals = []
            while val and ':' in val:
                nxt, val = val.split(':', 1)
                vals.append(nxt)

            if ':' in val:
                first, second = val
            else:
                first = val
        else:
            raise BadSpecValue("Value must be a list or a string", got=type(val)
                , looking_at=self.value_name
                )

        if len(self.specs) < len(vals) or len(vals) > len(self.specs) + len(self.optional_specs):
            raise BadSpecValue("The value is a list with the wrong number of items"
                , got=val
                , got_length=len(val)
                , min_length=len(self.specs)
                , max_length=len(self.specs) + len(self.optional_specs)
                , looking_at = self.value_name
                )

        formatted_vals = []
        for index, spec in enumerate(self.specs + self.optional_specs):
            index += 1
            expected_type = NotSpecified
            if isinstance(spec, (list, tuple)):
                spec, expected_type = spec

            if len(vals) < index:
                val = getattr(self, "determine_{0}".format(index), lambda *args: val)(*list(vals) + [meta, val])
            else:
                val = vals[index]

            if val is not NotSpecified and (expected_type is NotSpecified or not isinstance(val, expected_type)):
                val = formatted(string_spec(), formatter=self.formatter).normalise(meta, val)

            func = getattr(self, "alter_{0}".format(index), lambda *args: val)
            formatted_vals.append(func(*(formatted_vals[:index] + [meta, original_val])))

        return self.create_result(*list(formatted_vals) + [meta, original_val])

