"""
Jinja template utilties
"""

from hyde.fs import File, Folder
from hyde.template import Template
from jinja2 import contextfunction, Environment, FileSystemLoader
from jinja2 import environmentfilter, Markup, Undefined, nodes
from jinja2.ext import Extension
from jinja2.exceptions import TemplateError


class SilentUndefined(Undefined):
    def __getattr__(self, name):
        return self

    __getitem__ = __getattr__

    def __call__(self, *args, **kwargs):
        return self


@contextfunction
def media_url(context, path):
    site = context['site']
    return Folder(site.config.media_url).child(path)


@contextfunction
def content_url(context, path):
    site = context['site']
    return Folder(site.config.base_url).child(path)

@environmentfilter
def markdown(env, value):
    try:
        import markdown
    except ImportError:
        raise TemplateError("Cannot load the markdown library")
    output = value
    d = {}
    if hasattr(env.config, 'markdown'):
        d['extensions'] = getattr(env.config.markdown, 'extensions', [])
        d['extension_configs'] = getattr(env.config.markdown, 'extension_configs', {})
    md = markdown.Markdown(**d)
    return md.convert(output)

class Markdown(Extension):
    tags = set(['markdown'])

    def parse(self, parser):
        lineno = parser.stream.next().lineno
        body = parser.parse_statements(['name:endmarkdown'], drop_needle=True)

        return nodes.CallBlock(
                    self.call_method('_render_markdown', [], [], None, None),
                    [], [], body
                ).set_lineno(lineno)

    def _render_markdown(self, caller=None):
        if not caller:
            return ''
        output = caller().strip()
        return markdown(self.environment, output)

# pylint: disable-msg=W0104,E0602,W0613,R0201
class Jinja2Template(Template):
    """
    The Jinja2 Template implementation
    """

    def __init__(self, sitepath):
        super(Jinja2Template, self).__init__(sitepath)

    def configure(self, config):
        """
        Uses the config object to initialize the jinja environment.
        """
        if config:
            loader = FileSystemLoader([
                            str(config.content_root_path),
                            str(config.layout_root_path),
                        ])
        else:
            loader = FileSystemLoader(str(self.sitepath))
        self.env = Environment(loader=loader,
                                undefined=SilentUndefined,
                                trim_blocks=True,
                                extensions=[Markdown,
                                            'jinja2.ext.do',
                                            'jinja2.ext.loopcontrols',
                                            'jinja2.ext.with_'])
        self.env.globals['media_url'] = media_url
        self.env.globals['content_url'] = content_url
        self.env.extend(config=config)
        self.env.filters['markdown'] = markdown

        try:
            from typogrify.templatetags import jinja2_filters
        except ImportError:
            jinja2_filters = False

        if jinja2_filters:
            jinja2_filters.register(self.env)


    @property
    def exception_class(self):
        return TemplateError

    def render(self, text, context):
        """
        Renders the given resource using the context
        """
        template = self.env.from_string(text)
        return template.render(context)
