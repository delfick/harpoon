from input_algorithms.many_item_spec import many_item_formatted_spec
from harpoon.option_spec.harpoon_specs import HarpoonSpec

from input_algorithms import spec_base as sb
from docutils.statemachine import ViewList
from sphinx.util.compat import Directive
from textwrap import dedent
from docutils import nodes
import six

class ShowSpecsDirective(Directive):
    """Directive for outputting all the specs found in harpoon.option_spec.harpoon_spec"""
    has_content = True

    def run(self):
        """For each file in noseOfYeti/specs, output nodes to represent each spec file"""
        tokens = []
        for name, spec in (("Harpoon", HarpoonSpec().harpoon_spec), ("Image", HarpoonSpec().image_spec)):
            section = nodes.section()
            section['names'].append(name)
            section['ids'].append(name)

            header = nodes.title()
            header += nodes.Text(name)
            section.append(header)

            section.extend(self.nodes_for_spec(spec))
            tokens.append(section)

        return tokens

    def nodes_for_signature(self, spec, para):
        tokens = []
        if isinstance(spec, sb.create_spec):
            para += nodes.Text(" <options> ")
        elif isinstance(spec, sb.optional_spec):
            colord = nodes.inline(classes=['blue-text'])
            emphasis = nodes.emphasis()
            emphasis += nodes.Text(" (optional) ")
            colord += emphasis
            para += colord
            self.nodes_for_signature(spec.spec, para)
        elif isinstance(spec, sb.defaulted):
            colord = nodes.inline(classes=['green-text'])
            emphasis = nodes.emphasis()
            dflt = spec.default(None)
            if isinstance(dflt, six.string_types):
                dflt = '"{0}"'.format(dflt)
            emphasis += nodes.Text(" (default={0}) ".format(dflt))
            colord += emphasis
            para += colord
            self.nodes_for_signature(spec.spec, para)
        elif isinstance(spec, sb.required):
            colord = nodes.inline(classes=['red-text'])
            strong = nodes.strong()
            strong += nodes.Text(" (required) ")
            colord += strong
            para += colord
            self.nodes_for_signature(spec.spec, para)
        elif isinstance(spec, sb.listof):
            para += nodes.Text(" [ ")
            self.nodes_for_signature(spec.spec, para)
            para += nodes.Text(", ... ] ")
        elif isinstance(spec, sb.dictof):
            para += nodes.Text(" { ")
            self.nodes_for_signature(spec.name_spec, para)
            para += nodes.Text(" : ")
            self.nodes_for_signature(spec.value_spec, para)
            para += nodes.Text(" } ")
        elif isinstance(spec, many_item_formatted_spec):
            para += nodes.Text(" [")
            for i, s in enumerate(spec.specs):
                self.nodes_for_signature(s, para)
                if i < len(spec.specs)-1 or spec.optional_specs:
                    para += nodes.Text(', ')
            if spec.optional_specs:
                para += nodes.Text(" (")
                for i, s in enumerate(spec.optional_specs):
                    self.nodes_for_signature(s, para)
                    if i < len(spec.specs)-1:
                        para += nodes.Text(', ')
                para += nodes.Text(" )")
            para += nodes.Text("] ")

        elif isinstance(spec, (sb.container_spec, sb.formatted)):
            self.nodes_for_signature(spec.spec, para)
        elif isinstance(spec, sb.overridden):
            para += nodes.Text('"{0}"'.format(spec.value))
        else:
            spec_name = spec.__class__.__name__
            if spec_name.endswith("_spec"):
                spec_name = spec_name[:-5]
            para += nodes.Text(spec_name)

        return tokens

    def nodes_for_spec(self, spec):
        """
            Determine nodes for an input_algorithms spec
            Taking into account nested specs
        """
        tokens = []
        if isinstance(spec, sb.create_spec):
            container = nodes.container(classes=["option_spec_option shortline blue-back"])
            creates = spec.kls
            for name, option in sorted(spec.kwargs.items(), key=lambda x: len(x[0])):
                para = nodes.paragraph(classes=["option monospaced"])
                para += nodes.Text("{0} = ".format(name))
                self.nodes_for_signature(option, para)

                fields = {}
                if creates and hasattr(creates, 'fields') and isinstance(creates.fields, dict):
                    for key, val in creates.fields.items():
                        if isinstance(key, tuple):
                            fields[key[0]] = val
                        else:
                            fields[key] = val

                txt = fields.get(name) or "No description"
                viewlist = ViewList()
                for line in dedent(txt).split('\n'):
                    viewlist.append(line, name)
                desc = nodes.section(classes=["description monospaced"])
                self.state.nested_parse(viewlist, self.content_offset, desc)

                container += para
                container += desc
                container.extend(self.nodes_for_spec(option))
            tokens.append(container)
        elif isinstance(spec, sb.optional_spec):
            tokens.extend(self.nodes_for_spec(spec.spec))
        elif isinstance(spec, sb.container_spec):
            tokens.extend(self.nodes_for_spec(spec.spec))
        elif isinstance(spec, sb.dictof):
            tokens.extend(self.nodes_for_spec(spec.value_spec))

        return tokens

def setup(app):
    """Setup the show_specs directive"""
    app.add_directive('show_specs', ShowSpecsDirective)

