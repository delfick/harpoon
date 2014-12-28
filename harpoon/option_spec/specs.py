"""
We define a custom spec type here for interpreting list specifications.
"""

from input_algorithms import spec_base as sb

from input_algorithms.spec_base import NotSpecified, Spec, formatted
from input_algorithms.errors import BadSpecValue
import six

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
    seperators = ":"
    optional_specs = []

    def setup(self, *args, **kwargs):
        if not self.value_name:
            self.value_name = self.__class__.__name__

    def normalise(self, meta, val):
        original_val = val
        if isinstance(val, (list, tuple)):
            vals = val
            dividers = [':']

        elif isinstance(val, six.string_types):
            vals = []
            dividers = []
            while val and any(seperator in val for seperator in self.seperators):
                for seperator in self.seperators:
                    if seperator in val:
                        nxt, val = val.split(seperator, 1)
                        vals.append(nxt)
                        dividers.append(seperator)
                        break
            vals.append(val)

            if not vals:
                vals = [val]
                dividers=[None]

        elif isinstance(val, dict):
            if len(val) > 1:
                raise BadSpecValue("Value as a dict must only be one item", got=val, meta=meta)
            vals = val.items()[0]
            dividers = [':']

        else:
            raise BadSpecValue("Value must be a list or a string", got=type(val)
                , looking_at=self.value_name
                )

        if len(vals) < len(self.specs) > len(self.specs) + len(self.optional_specs):
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

            val = NotSpecified
            if index <= len(vals):
                val = vals[index-1]

            if len(vals) < index:
                vals.append(val)
            val = getattr(self, "determine_{0}".format(index), lambda *args: val)(*list(vals) + [meta, val])
            spec = getattr(self, "spec_wrapper_{0}".format(index), lambda spec, *args: spec)(spec, *list(vals) + [meta, val, dividers])

            if (index-1 < len(self.specs) or val is not NotSpecified) and (expected_type is NotSpecified or not isinstance(val, expected_type)):
                if getattr(self, "formatter", None):
                    val = formatted(spec, formatter=self.formatter).normalise(meta, val)
                else:
                    val = spec.normalise(meta, val)

            func = getattr(self, "alter_{0}".format(index), lambda *args: val)
            altered = func(*(formatted_vals[:index] + [val, meta, original_val]))
            if index <= len(vals):
                vals[index-1] = altered
            formatted_vals.append(altered)

        return self.create_result(*list(formatted_vals) + [meta, original_val, dividers])

